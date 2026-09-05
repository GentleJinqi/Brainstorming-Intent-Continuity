#!/usr/bin/env python3
"""Deterministic mechanics for controller-authored BIC records."""

import argparse
import copy
from contextlib import contextmanager
import fcntl
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path


SCHEMA_VERSION = 2
WRITER_VERSION = "1.0.1"
STATE_DIRECTORY = ".brainstorming-intent"
RECORD_ID_PATTERN = re.compile(r"^BIC-[0-9]{4}$")

CURRENT_SECTIONS = (
    "## Goal and non-goals",
    "## Approved decisions",
    "## Explicit prohibitions",
    "## Rationale and consequences",
    "## Observable proof",
    "## Examples and edge cases",
    "## Open questions",
    "## Current Intent Map",
)
HISTORY_SECTIONS = (
    "## Rejected or superseded directions",
    "## Key turning points",
    "## Material counterexamples",
    "## Evolution Map",
)


class BicError(Exception):
    def __init__(self, state, message, **details):
        super().__init__(message)
        self.state = state
        self.details = details


def emit(payload):
    print(json.dumps(payload, sort_keys=True))


def project_path(raw_path):
    path = Path(raw_path).resolve()
    if not path.is_dir():
        raise BicError("invalid_project", f"project directory does not exist: {path}")
    return path


def project_file(project, relative_path, *, state="invalid_record"):
    """Resolve a managed location without permitting an escape from its project."""
    path = project / relative_path
    try:
        resolved = path.resolve()
    except (OSError, RuntimeError, ValueError) as error:
        raise BicError(state, f"cannot resolve project path: {error}")
    if not is_within(resolved, project):
        raise BicError(state, f"path must remain inside the project: {path}")
    if resolved != path:
        raise BicError(state, f"managed path must be canonical, without aliases: {path}")
    return resolved


def manifest_path(project):
    return project_file(project, f"{STATE_DIRECTORY}/manifest.json", state="invalid_project")


@contextmanager
def project_lock(project, *, exclusive):
    """Lock the existing project directory, without enrolling a read-only caller."""
    root_fd = os.open(str(project), os.O_RDONLY)
    try:
        fcntl.flock(root_fd, fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
        yield
    finally:
        os.close(root_fd)


def load_manifest(project):
    path = manifest_path(project)
    if not path.exists():
        return None
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise BicError("invalid_manifest", f"cannot read manifest: {error}")
    if not isinstance(manifest, dict):
        raise BicError("invalid_manifest", "manifest must be an object")
    if "schema_version" not in manifest or type(manifest["schema_version"]) is not int:
        raise BicError("invalid_manifest", "manifest schema_version must be an integer")
    schema_version = manifest.get("schema_version")
    if schema_version not in (1, SCHEMA_VERSION):
        raise BicError(
            "compatibility_hold",
            f"unsupported schema_version {schema_version!r}; supported versions are 1 and 2",
            schema_version=schema_version,
        )
    if schema_version == 1:
        validate_schema_v1_manifest(manifest)
    else:
        validate_schema_v2_manifest(manifest)
    return manifest


def _validate_manifest_metadata(manifest, schema_version):
    if not isinstance(manifest.get("writer_version"), str) or not manifest[
        "writer_version"
    ]:
        raise BicError("invalid_manifest", "manifest writer_version must be non-empty")
    if manifest.get("compatibility_state") != "compatible":
        raise BicError(
            "invalid_manifest", "manifest compatibility_state must be 'compatible'"
        )
    if manifest.get("project_state") != "active":
        raise BicError("invalid_manifest", "manifest project_state must be 'active'")
    if type(manifest.get("commit_pending")) is not bool:
        raise BicError("invalid_manifest", "manifest commit_pending must be a boolean")
    next_record_number = manifest.get("next_record_number")
    if type(next_record_number) is not int or not 1 <= next_record_number <= 10000:
        raise BicError(
            "invalid_manifest",
            "manifest next_record_number must be an integer from 1 through 10000",
        )
    records = manifest.get("records")
    if not isinstance(records, dict):
        raise BicError("invalid_manifest", "manifest records must be an object")

    highest_record_number = 0
    pending_records = False
    for record_id, metadata in records.items():
        if not isinstance(record_id, str) or not RECORD_ID_PATTERN.fullmatch(record_id):
            raise BicError("invalid_manifest", f"invalid manifest record ID: {record_id!r}")
        record_number = int(record_id.removeprefix("BIC-"))
        if record_number < 1:
            raise BicError("invalid_manifest", f"invalid manifest record ID: {record_id!r}")
        highest_record_number = max(highest_record_number, record_number)
        if not isinstance(metadata, dict):
            raise BicError(
                "invalid_manifest", f"metadata for {record_id} must be an object"
            )
        revision = metadata.get("revision")
        if type(revision) is not int or revision < 1:
            raise BicError(
                "invalid_manifest", f"revision for {record_id} must be a positive integer"
            )
        if type(metadata.get("commit_pending")) is not bool:
            raise BicError(
                "invalid_manifest", f"commit_pending for {record_id} must be a boolean"
            )
        base = f"records/{record_id}"
        if schema_version == 2:
            active_slot = metadata.get("active_slot")
            if active_slot not in ("a", "b"):
                raise BicError("invalid_manifest", f"invalid active_slot for {record_id}")
            base += f"/slots/{active_slot}"
            round_metadata = metadata.get("round")
            if not isinstance(round_metadata, dict) or round_metadata.get("state") not in (
                "open", "paused", "cancelled", "replaced", "completed", "unknown"
            ):
                raise BicError("invalid_manifest", f"invalid round for {record_id}")
            for field in ("part_ids", "event_ids"):
                values = metadata.get(field)
                if (not isinstance(values, list)
                    or any(not isinstance(value, str) or not value for value in values)
                    or len(set(values)) != len(values)):
                    raise BicError("invalid_manifest", f"invalid {field} for {record_id}")
        expected_paths = {
            "current_path": f"{base}/current.md",
            "history_path": f"{base}/history.md",
        }
        for field, expected_path in expected_paths.items():
            if metadata.get(field) != expected_path:
                raise BicError(
                    "invalid_manifest",
                    f"{field} for {record_id} must be {expected_path!r}",
                )
        pending_records = pending_records or metadata["commit_pending"]

    if next_record_number <= highest_record_number:
        raise BicError(
            "invalid_manifest",
            "manifest next_record_number must exceed every registered record ID",
        )
    if manifest["commit_pending"] != pending_records:
        raise BicError(
            "invalid_manifest",
            "manifest commit_pending must match the registered record states",
        )


def validate_schema_v1_manifest(manifest):
    _validate_manifest_metadata(manifest, 1)


def validate_schema_v2_manifest(manifest):
    _validate_manifest_metadata(manifest, 2)
    retired = manifest.get("retired_paths")
    if not isinstance(retired, list) or any(
        not isinstance(path, str) or not re.fullmatch(
            r"\.brainstorming-intent/records/BIC-[0-9]{4}/(?:slots/[ab]/)?(?:current|history)\.md", path
        ) for path in retired
    ) or len(set(retired)) != len(retired):
        raise BicError("invalid_manifest", "retired_paths must contain unique managed body paths")


def require_schema_v2(manifest):
    if manifest is not None and manifest["schema_version"] == 1:
        raise BicError("migration_required", "run migrate --expected-schema 1 before writing this project")


def _new_manifest():
    return {
        "schema_version": SCHEMA_VERSION,
        "writer_version": WRITER_VERSION,
        "compatibility_state": "compatible",
        "project_state": "active",
        "commit_pending": False,
        "next_record_number": 1,
        "records": {},
        "retired_paths": [],
    }


def atomic_write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_name = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=str(path.parent),
            prefix=f".{path.name}.",
            delete=False,
        ) as temporary_file:
            temporary_file.write(content)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
            temporary_name = temporary_file.name
        os.replace(temporary_name, path)
        directory_fd = os.open(str(path.parent), os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if temporary_name and os.path.exists(temporary_name):
            os.unlink(temporary_name)


def render_draft(path, record_id, revision):
    try:
        draft = Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise BicError("invalid_draft", f"cannot read draft {path}: {error}")
    if "{{RECORD_ID}}" not in draft or "{{REVISION}}" not in draft:
        raise BicError(
            "invalid_draft",
            "draft must contain {{RECORD_ID}} and {{REVISION}} placeholders",
        )
    return draft.replace("{{RECORD_ID}}", record_id).replace(
        "{{REVISION}}", str(revision)
    )


def validate_document(text, kind, record_id, revision):
    if kind == "current":
        expected_title = f"# {record_id} Current Intent"
        sections = CURRENT_SECTIONS
    else:
        expected_title = f"# {record_id} History"
        sections = HISTORY_SECTIONS

    lines = text.splitlines()
    if not lines or lines[0] != expected_title:
        raise BicError("invalid_draft", f"{kind}.md must start with {expected_title!r}")
    if f"Revision: {revision}" not in lines:
        raise BicError(
            "invalid_draft", f"{kind}.md must contain Revision: {revision}"
        )
    positions = []
    for section in sections:
        try:
            positions.append(lines.index(section))
        except ValueError:
            raise BicError("invalid_draft", f"{kind}.md is missing {section}")
    if positions != sorted(positions) or len(set(positions)) != len(positions):
        raise BicError("invalid_draft", f"{kind}.md required sections are out of order")
    map_heading = sections[-1]
    map_start = positions[-1] + 1
    map_end = len(lines)
    for index in range(map_start, len(lines)):
        if re.match(r"^#{1,2}\s", lines[index]):
            map_end = index
            break
    map_lines = lines[map_start:map_end]
    if "```mermaid" not in map_lines:
        raise BicError(
            "invalid_draft",
            f"{kind}.md {map_heading} is missing a Mermaid block",
        )
    mermaid_start = map_lines.index("```mermaid")
    if "```" not in map_lines[mermaid_start + 1 :]:
        raise BicError(
            "invalid_draft",
            f"{kind}.md {map_heading} has an unclosed Mermaid block",
        )
    if "{{RECORD_ID}}" in text or "{{REVISION}}" in text:
        raise BicError("invalid_draft", f"{kind}.md has unresolved placeholders")


def _view_from_metadata(record_id, metadata, schema_version):
    return {
        "record_id": record_id,
        "revision": metadata["revision"],
        "source_kind": "current",
        "round": copy.deepcopy(metadata.get("round", {"state": "unknown"})),
        "current_path": f"{STATE_DIRECTORY}/{metadata['current_path']}",
        "history_path": f"{STATE_DIRECTORY}/{metadata['history_path']}",
        "part_ids": list(metadata.get("part_ids", [])),
        "event_ids": list(metadata.get("event_ids", [])),
    }


def _resolve_record_view_locked(manifest, record_id, revision=None):
    if manifest is None:
        raise BicError("not_enrolled", "project has no BIC manifest")
    metadata = manifest["records"].get(record_id)
    if metadata is None:
        raise BicError("record_not_found", f"unknown record: {record_id}")
    if revision is not None and (type(revision) is not int or revision < 1):
        raise BicError("invalid_revision", "revision must be a positive integer")
    if revision is not None and revision != metadata["revision"]:
        raise BicError("version_unavailable", f"{record_id} revision {revision} was not saved")
    return _view_from_metadata(record_id, metadata, manifest["schema_version"])


def resolve_record_view(project, record_id, revision=None):
    """Resolve a view while the caller holds the project lock."""
    return _resolve_record_view_locked(load_manifest(project), record_id, revision)


def collect_registered_dependencies(manifest, view):
    """Return project-relative content paths registered for this view."""
    return {view["current_path"], view["history_path"]}


def _registered_paths(manifest):
    paths = set()
    for record_id, metadata in manifest["records"].items():
        paths.update(collect_registered_dependencies(
            manifest, _view_from_metadata(record_id, metadata, manifest["schema_version"])
        ))
    return paths


def _read_view_documents(project, view):
    documents = {}
    for kind in ("current", "history"):
        path = project_file(project, view[f"{kind}_path"])
        try:
            with path.open(encoding="utf-8", newline="") as source:
                text = source.read()
        except (OSError, UnicodeError) as error:
            raise BicError("invalid_record", f"cannot read {view['record_id']}: {error}")
        try:
            validate_document(text, kind, view["record_id"], view["revision"])
        except BicError as error:
            raise BicError("invalid_record", str(error))
        documents[kind] = {"path": str(path), "text": text}
    return documents


def validate_record(project, manifest, record_id):
    view = _resolve_record_view_locked(manifest, record_id)
    if manifest["schema_version"] == 1:
        record_directory = project_file(project, f"{STATE_DIRECTORY}/records/{record_id}")
        if not record_directory.is_dir():
            raise BicError("invalid_record", f"missing record directory for {record_id}")
        actual_names = {path.name for path in record_directory.iterdir() if path.is_file()}
        if actual_names != {"current.md", "history.md"}:
            raise BicError("invalid_record", f"{record_id} must contain exactly current.md and history.md")
    return _read_view_documents(project, view)


def read_record(project, record_id, revision=None, selectors=None):
    with project_lock(project, exclusive=False):
        manifest = load_manifest(project)
        view = _resolve_record_view_locked(manifest, record_id, revision)
        if selectors:
            raise BicError("event_not_found", "this record has no registered events")
        documents = validate_record(project, manifest, record_id)
        return {
            "ok": True, "state": "read", "project": str(project),
            "record_id": record_id, "revision": view["revision"],
            "source_kind": view["source_kind"], "round": view["round"],
            **documents, "parts": [], "corrections": [],
        }


def _cleanup_retired(project, manifest):
    # No directory scanning: only explicitly retired, no-longer-registered bodies.
    for relative_path in set(manifest.get("retired_paths", [])) - _registered_paths(manifest):
        try:
            path = project_file(project, relative_path)
            path.unlink()
        except (BicError, OSError):
            # A published view remains authoritative if retirement is interrupted.
            # Keep the path registered for a later normal write/snapshot retry.
            pass


def _publish_manifest(project, manifest):
    validate_schema_v2_manifest(manifest)
    atomic_write(manifest_path(project), json.dumps(manifest, indent=2, sort_keys=True) + "\n")


def _select_apply_target(manifest, record_id, expected_revision):
    require_schema_v2(manifest)
    if record_id:
        if not RECORD_ID_PATTERN.fullmatch(record_id):
            raise BicError("invalid_record_id", f"invalid record ID: {record_id}")
        metadata = manifest["records"].get(record_id)
        if metadata is None:
            raise BicError("record_not_found", f"unknown record: {record_id}")
        actual_revision = metadata["revision"]
    else:
        number = manifest["next_record_number"]
        if number > 9999:
            raise BicError("record_id_exhausted", "four-digit BIC record IDs are exhausted at BIC-9999")
        record_id, actual_revision = f"BIC-{number:04d}", 0
    if type(expected_revision) is not int or expected_revision != actual_revision:
        raise BicError("revision_conflict", f"expected revision {expected_revision}, found {actual_revision}")
    return record_id, actual_revision


def publish_update(project, record_id, expected_revision, draft_set):
    with project_lock(project, exclusive=True):
        manifest = load_manifest(project)
        require_schema_v2(manifest)
        manifest = manifest if manifest is not None else _new_manifest()
        metadata = manifest["records"].get(record_id)
        if metadata is None:
            allocated, actual_revision = _select_apply_target(manifest, None, expected_revision)
            if record_id != allocated:
                raise BicError("revision_conflict", "record allocation changed before publication")
        else:
            _, actual_revision = _select_apply_target(manifest, record_id, expected_revision)
        revision = actual_revision + 1
        for kind in ("current", "history"):
            validate_document(draft_set[kind], kind, record_id, revision)
        update = draft_set.get("update", {})
        if not isinstance(update, dict) or update:
            raise BicError("invalid_update", "this storage update accepts no structured fields yet")
        active_slot = metadata["active_slot"] if metadata else None
        next_slot = "b" if active_slot == "a" else "a"
        base = f"records/{record_id}/slots/{next_slot}"
        destinations = {kind: project_file(project, f"{STATE_DIRECTORY}/{base}/{kind}.md")
                        for kind in ("current", "history")}
        for kind, destination in destinations.items():
            atomic_write(destination, draft_set[kind])
        next_manifest = copy.deepcopy(manifest)
        next_metadata = copy.deepcopy(metadata) if metadata else {
            "round": {"state": "open"}, "part_ids": [], "event_ids": [],
        }
        next_metadata.update({
            "revision": revision, "active_slot": next_slot, "commit_pending": True,
            "current_path": f"{base}/current.md", "history_path": f"{base}/history.md",
        })
        next_manifest["records"][record_id] = next_metadata
        if actual_revision == 0:
            next_manifest["next_record_number"] += 1
        next_manifest["writer_version"] = WRITER_VERSION
        next_manifest["commit_pending"] = True
        old_paths = set() if metadata is None else collect_registered_dependencies(
            manifest, _view_from_metadata(record_id, metadata, SCHEMA_VERSION)
        )
        next_manifest["retired_paths"] = sorted(
            (set(manifest["retired_paths"]) | old_paths) - _registered_paths(next_manifest)
        )
        _publish_manifest(project, next_manifest)
        _cleanup_retired(project, next_manifest)
        return {
            "ok": True, "state": "commit_pending", "record_id": record_id,
            "revision": revision, "current_path": str(destinations["current"]),
            "history_path": str(destinations["history"]),
        }


def migrate_project(project, expected_schema):
    with project_lock(project, exclusive=True):
        manifest = load_manifest(project)
        if manifest is None:
            raise BicError("not_enrolled", "project has no BIC manifest")
        if type(expected_schema) is not int or expected_schema != 1 or manifest["schema_version"] != expected_schema:
            raise BicError("schema_conflict", "migration requires expected schema 1 and an actual schema 1 project")
        for record_id in manifest["records"]:
            validate_record(project, manifest, record_id)
        next_manifest = copy.deepcopy(manifest)
        next_manifest.update({"schema_version": SCHEMA_VERSION, "writer_version": WRITER_VERSION})
        old_paths = _registered_paths(manifest)
        for record_id, metadata in next_manifest["records"].items():
            view = _view_from_metadata(record_id, manifest["records"][record_id], 1)
            documents = _read_view_documents(project, view)
            base = f"records/{record_id}/slots/a"
            destinations = {kind: project_file(project, f"{STATE_DIRECTORY}/{base}/{kind}.md")
                            for kind in ("current", "history")}
            for kind, destination in destinations.items():
                atomic_write(destination, documents[kind]["text"])
            metadata.update({
                "active_slot": "a", "current_path": f"{base}/current.md",
                "history_path": f"{base}/history.md", "round": {"state": "unknown"},
                "part_ids": [], "event_ids": [],
            })
        next_manifest["retired_paths"] = sorted(old_paths - _registered_paths(next_manifest))
        _publish_manifest(project, next_manifest)
        _cleanup_retired(project, next_manifest)
        return {"ok": True, "state": "migrated", "schema_version": SCHEMA_VERSION,
                "records": sorted(next_manifest["records"])}


def is_within(path, parent):
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def binding_file(plugin_data):
    return plugin_data / "session-bindings.json"


def load_bindings(plugin_data):
    path = binding_file(plugin_data)
    if not path.exists():
        return {"schema_version": 1, "sessions": {}}
    try:
        bindings = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise BicError("invalid_bindings", f"cannot read session bindings: {error}")
    if not isinstance(bindings, dict):
        raise BicError("invalid_bindings", "session bindings must be an object")
    if type(bindings.get("schema_version")) is not int or bindings.get(
        "schema_version"
    ) != 1:
        raise BicError("invalid_bindings", "unsupported session binding format")
    if not isinstance(bindings.get("sessions"), dict):
        raise BicError("invalid_bindings", "unsupported session binding format")
    return bindings


def validate_binding_entry(binding):
    for field in ("project", "record_id", "current_path", "history_path"):
        value = binding.get(field)
        if not isinstance(value, str) or not value:
            raise BicError(
                "invalid_bindings", f"session binding {field} must be a non-empty string"
            )
    if not RECORD_ID_PATTERN.fullmatch(binding["record_id"]):
        raise BicError("invalid_bindings", "session binding record_id is invalid")
    if type(binding.get("revision")) is not int or binding["revision"] < 1:
        raise BicError(
            "invalid_bindings", "session binding revision must be a positive integer"
        )


def resolve_binding_project(project_text):
    try:
        raw_project = Path(project_text)
        if not raw_project.is_absolute():
            raise BicError(
                "invalid_bindings",
                "session binding project must be an absolute canonical path",
            )
        project = raw_project.resolve()
        if project_text != str(project):
            raise BicError(
                "invalid_bindings",
                "session binding project must be an absolute canonical path",
            )
        return project, project.is_dir()
    except BicError:
        raise
    except (OSError, RuntimeError, UnicodeError, ValueError) as error:
        raise BicError("invalid_bindings", f"invalid session binding project: {error}")


def binding_payload(binding):
    return {
        "project": binding["project"],
        "record_id": binding["record_id"],
        "revision": binding["revision"],
        "current_path": binding["current_path"],
        "history_path": binding["history_path"],
    }


def registry_git_paths(manifest):
    paths = [f"{STATE_DIRECTORY}/manifest.json"]
    for record_id in sorted(manifest["records"]):
        metadata = manifest["records"][record_id]
        paths.extend(f"{STATE_DIRECTORY}/{metadata[field]}" for field in ("current_path", "history_path"))
    return paths


def run_git(project, arguments):
    return subprocess.run(
        ["git", *arguments],
        cwd=project,
        text=True,
        capture_output=True,
        check=False,
    )


def command_status(arguments):
    project = project_path(arguments.project)
    with project_lock(project, exclusive=False):
        manifest = load_manifest(project)
        if manifest is None:
            return {"ok": True, "state": "not_enrolled"}
        record_ids = sorted(manifest["records"])
        state = "commit_pending" if manifest.get("commit_pending") else "active"
        return {
            "ok": True, "state": state, "schema_version": manifest["schema_version"],
            "records": record_ids,
            "revisions": {record_id: manifest["records"][record_id]["revision"] for record_id in record_ids},
        }


def _draft_path(project, raw_path):
    path = Path(raw_path).resolve()
    if not is_within(path, project):
        raise BicError("invalid_draft", "draft must resolve inside its project")
    return path


def command_apply(arguments):
    project = project_path(arguments.project)
    # Rendering has no registry effects. Publication rechecks allocation/revision
    # under its own exclusive lock, rather than nesting locks on different fds.
    with project_lock(project, exclusive=False):
        manifest = load_manifest(project)
        manifest = manifest if manifest is not None else _new_manifest()
        record_id, actual_revision = _select_apply_target(manifest, arguments.record_id, arguments.expected_revision)
    draft_set = {kind: render_draft(_draft_path(project, getattr(arguments, f"{kind}_draft")),
                                   record_id, actual_revision + 1)
                 for kind in ("current", "history")}
    draft_set["update"] = {}
    if arguments.update_draft:
        path = _draft_path(project, arguments.update_draft)
        try:
            draft_set["update"] = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise BicError("invalid_update", f"cannot read update draft: {error}")
    return publish_update(project, record_id, arguments.expected_revision, draft_set)


def command_read(arguments):
    return read_record(project_path(arguments.project), arguments.record_id, arguments.revision)


def command_migrate(arguments):
    return migrate_project(project_path(arguments.project), arguments.expected_schema)


def command_validate(arguments):
    project = project_path(arguments.project)
    with project_lock(project, exclusive=False):
        manifest = load_manifest(project)
        if manifest is None:
            raise BicError("not_enrolled", "project has no BIC manifest")
        record_ids = [arguments.record_id] if arguments.record_id else sorted(manifest["records"])
        for record_id in record_ids:
            validate_record(project, manifest, record_id)
        payload = {"ok": True, "state": "valid", "records": record_ids}
        if arguments.record_id:
            view = _resolve_record_view_locked(manifest, arguments.record_id)
            payload.update({"record_id": arguments.record_id, "revision": view["revision"],
                            "current_path": str(project_file(project, view["current_path"])),
                            "history_path": str(project_file(project, view["history_path"]))})
        return payload


def command_bind(arguments):
    plugin_data = Path(arguments.plugin_data).resolve()
    if arguments.lookup:
        bindings = load_bindings(plugin_data)
        sessions = bindings["sessions"]
        if arguments.session_id not in sessions:
            raise BicError("unbound_session", "session has no BIC binding")
        binding = sessions[arguments.session_id]
        if not isinstance(binding, dict):
            raise BicError(
                "invalid_bindings", "session binding entry must be an object"
            )
        validate_binding_entry(binding)
        project, project_is_dir = resolve_binding_project(binding["project"])
        if is_within(plugin_data, project):
            raise BicError(
                "invalid_plugin_data", "plugin data must be outside the project"
            )
        if not project_is_dir:
            raise BicError("stale_binding", "bound project no longer exists")
        try:
            manifest = load_manifest(project)
        except BicError as error:
            if error.state == "compatibility_hold":
                raise
            raise BicError("stale_binding", str(error))
        if manifest is None:
            raise BicError("stale_binding", "bound project is no longer enrolled")
        record_id = binding.get("record_id")
        metadata = manifest["records"].get(record_id)
        if metadata is None or metadata.get("revision") != binding.get("revision"):
            raise BicError("stale_binding", "bound record revision is stale")
        expected_paths = {
            "current_path": str(project_file(project, f"{STATE_DIRECTORY}/{metadata['current_path']}")),
            "history_path": str(project_file(project, f"{STATE_DIRECTORY}/{metadata['history_path']}")),
        }
        if any(binding.get(field) != path for field, path in expected_paths.items()):
            raise BicError("stale_binding", "bound record paths are stale")
        validate_record(project, manifest, record_id)
        return {"ok": True, "state": "bound", **binding_payload(binding)}

    if not arguments.project:
        raise BicError("invalid_arguments", "--project is required when setting a binding")
    project = project_path(arguments.project)
    if is_within(plugin_data, project):
        raise BicError("invalid_plugin_data", "plugin data must be outside the project")
    manifest = load_manifest(project)
    if manifest is None:
        raise BicError("not_enrolled", "project has no BIC manifest")
    if not arguments.record_id:
        raise BicError("record_required", "--record-id is required; binding never guesses")
    metadata = manifest["records"].get(arguments.record_id)
    if metadata is None:
        raise BicError("record_not_found", f"unknown record: {arguments.record_id}")
    if arguments.expected_revision is None:
        raise BicError("invalid_arguments", "--expected-revision is required")
    if metadata.get("revision") != arguments.expected_revision:
        raise BicError(
            "revision_conflict",
            f"expected revision {arguments.expected_revision}, found {metadata.get('revision')}",
        )
    validate_record(project, manifest, arguments.record_id)
    binding = {
        "project": str(project),
        "record_id": arguments.record_id,
        "revision": arguments.expected_revision,
        "current_path": str(project_file(project, f"{STATE_DIRECTORY}/{metadata['current_path']}")),
        "history_path": str(project_file(project, f"{STATE_DIRECTORY}/{metadata['history_path']}")),
    }

    plugin_data.mkdir(parents=True, exist_ok=True)
    plugin_fd = os.open(str(plugin_data), os.O_RDONLY)
    try:
        fcntl.flock(plugin_fd, fcntl.LOCK_EX)
        bindings = load_bindings(plugin_data)
        bindings["sessions"][arguments.session_id] = binding
        atomic_write(
            binding_file(plugin_data),
            json.dumps(bindings, indent=2, sort_keys=True) + "\n",
        )
    finally:
        os.close(plugin_fd)
    return {"ok": True, "state": "bound", **binding_payload(binding)}


def command_commit_snapshot(arguments):
    project = project_path(arguments.project)
    top_level = run_git(project, ["rev-parse", "--show-toplevel"])
    if top_level.returncode != 0 or Path(top_level.stdout.strip()).resolve() != project:
        raise BicError("invalid_project", "--project must be the Git repository root")

    root_fd = os.open(str(project), os.O_RDONLY)
    try:
        fcntl.flock(root_fd, fcntl.LOCK_EX)
        manifest = load_manifest(project)
        if manifest is None:
            raise BicError("not_enrolled", "project has no BIC manifest")
        record_ids = sorted(manifest["records"])
        for record_id in record_ids:
            validate_record(project, manifest, record_id)
        snapshot_paths = registry_git_paths(manifest)
        staging_paths = list(snapshot_paths)
        retired = sorted(set(manifest.get("retired_paths", [])) - _registered_paths(manifest))
        if retired:
            _cleanup_retired(project, manifest)
            tracked = run_git(project, ["ls-files", "-z", "--", *retired])
            # A failed commit can leave retirements staged: absent from the index,
            # but still in HEAD. Keep those exact paths in the retry snapshot too.
            staged_deletions = run_git(
                project, ["diff", "--cached", "--name-only", "--diff-filter=D", "-z", "--", *retired]
            )
            if tracked.returncode != 0 or staged_deletions.returncode != 0:
                raise BicError("commit_pending", "cannot resolve tracked retired BIC paths")
            # HEAD-only deletions are already staged; git add cannot match them.
            staging_paths.extend(path for path in tracked.stdout.split("\0") if path)
            snapshot_paths.extend(sorted({
                path for result in (tracked, staged_deletions)
                for path in result.stdout.split("\0") if path
            }))
        original_pending = {
            record_id: manifest["records"][record_id]["commit_pending"]
            for record_id in record_ids
        }
        original_project_pending = manifest["commit_pending"]

        for metadata in manifest["records"].values():
            metadata["commit_pending"] = False
        manifest["commit_pending"] = False
        atomic_write(
            manifest_path(project),
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        )
        staged = run_git(project, ["add", "--", *staging_paths])
        if staged.returncode == 0:
            committed = run_git(
                project,
                ["commit", "--only", "--message", arguments.message, "--", *snapshot_paths],
            )
        else:
            committed = staged
        if committed.returncode != 0:
            for record_id, pending in original_pending.items():
                manifest["records"][record_id]["commit_pending"] = pending
            manifest["commit_pending"] = original_project_pending
            atomic_write(
                manifest_path(project),
                json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            )
            run_git(project, ["add", "--", f"{STATE_DIRECTORY}/manifest.json"])
            error_text = (committed.stderr or committed.stdout).strip()
            raise BicError(
                "commit_pending",
                f"Git commit failed; original BIC pending state was restored: {error_text}",
                bic_paths_clean=False,
            )
        revision_result = run_git(project, ["rev-parse", "HEAD"])
        path_status = run_git(project, ["status", "--porcelain", "--", *snapshot_paths])
        bic_paths_clean = path_status.returncode == 0 and not path_status.stdout.strip()
        if not bic_paths_clean:
            for metadata in manifest["records"].values():
                metadata["commit_pending"] = True
            manifest["commit_pending"] = bool(manifest["records"])
            atomic_write(
                manifest_path(project),
                json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            )
            run_git(project, ["add", "--", f"{STATE_DIRECTORY}/manifest.json"])
            raise BicError(
                "commit_pending",
                "Git commit completed but the BIC registry snapshot is dirty",
                bic_paths_clean=False,
                commit=revision_result.stdout.strip(),
            )
    finally:
        os.close(root_fd)

    return {
        "ok": True,
        "state": "committed",
        "commit": revision_result.stdout.strip(),
        "bic_paths_clean": bic_paths_clean,
    }


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    status_parser = subparsers.add_parser("status")
    status_parser.add_argument("--project", required=True)
    status_parser.set_defaults(handler=command_status)

    apply_parser = subparsers.add_parser("apply")
    apply_parser.add_argument("--project", required=True)
    apply_parser.add_argument("--record-id")
    apply_parser.add_argument("--current-draft", required=True)
    apply_parser.add_argument("--history-draft", required=True)
    apply_parser.add_argument("--update-draft")
    apply_parser.add_argument("--expected-revision", required=True, type=int)
    apply_parser.set_defaults(handler=command_apply)

    validate_parser = subparsers.add_parser("validate")
    validate_parser.add_argument("--project", required=True)
    validate_parser.add_argument("--record-id")
    validate_parser.set_defaults(handler=command_validate)

    read_parser = subparsers.add_parser("read")
    read_parser.add_argument("--project", required=True)
    read_parser.add_argument("--record-id", required=True)
    target = read_parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--current", action="store_true")
    target.add_argument("--revision", type=int)
    read_parser.set_defaults(handler=command_read)

    migrate_parser = subparsers.add_parser("migrate")
    migrate_parser.add_argument("--project", required=True)
    migrate_parser.add_argument("--expected-schema", required=True, type=int)
    migrate_parser.set_defaults(handler=command_migrate)

    bind_parser = subparsers.add_parser("bind")
    bind_parser.add_argument("--plugin-data", required=True)
    bind_parser.add_argument("--session-id", required=True)
    bind_parser.add_argument("--lookup", action="store_true")
    bind_parser.add_argument("--project")
    bind_parser.add_argument("--record-id")
    bind_parser.add_argument("--expected-revision", type=int)
    bind_parser.set_defaults(handler=command_bind)

    commit_parser = subparsers.add_parser("commit-snapshot")
    commit_parser.add_argument("--project", required=True)
    commit_parser.add_argument("--message", required=True)
    commit_parser.set_defaults(handler=command_commit_snapshot)

    return parser


def main():
    parser = build_parser()
    arguments = parser.parse_args()
    try:
        emit(arguments.handler(arguments))
        return 0
    except BicError as error:
        emit(
            {
                "ok": False,
                "state": error.state,
                "error": str(error),
                **error.details,
            }
        )
        return 2
    except OSError as error:
        emit({"ok": False, "state": "io_error", "error": str(error)})
        return 2


if __name__ == "__main__":
    sys.exit(main())
