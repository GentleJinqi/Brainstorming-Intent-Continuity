#!/usr/bin/env python3
"""Deterministic mechanics for controller-authored BIC records."""

import argparse
import copy
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path


SCHEMA_VERSION = 2
WRITER_VERSION = "1.0.1"
STATE_DIRECTORY = ".brainstorming-intent"
PART_ID_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")
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
            r"\.brainstorming-intent/(?:records/BIC-[0-9]{4}/(?:slots/[ab]/)?(?:current|history)\.md|parts/BIC-[0-9]{4}/[a-f0-9]{64}\.md)", path
        ) for path in retired
    ) or len(set(retired)) != len(retired):
        raise BicError("invalid_manifest", "retired_paths must contain unique managed body paths")


    versions = manifest.get("versions", {})
    if not isinstance(versions, dict) or set(versions) - set(manifest["records"]):
        raise BicError("invalid_manifest", "versions must belong to registered records")
    for record_id, entries in versions.items():
        if not isinstance(entries, dict):
            raise BicError("invalid_manifest", "saved versions must be an object")
        for revision_text, view in entries.items():
            if (not isinstance(revision_text, str) or not re.fullmatch(r"[1-9][0-9]*", revision_text)
                or not isinstance(view, dict) or type(view.get("revision")) is not int
                or str(view["revision"]) != revision_text or view["revision"] > manifest["records"][record_id]["revision"]
                or view.get("record_id") != record_id or view.get("source_kind") != "saved"):
                raise BicError("invalid_manifest", "saved version identity is invalid")
            base = f"{STATE_DIRECTORY}/versions/{record_id}/r{revision_text}"
            for field, name in (("current_path", "current.md"), ("history_path", "history.md"), ("descriptor_path", "version.json")):
                if view.get(field) != f"{base}/{name}":
                    raise BicError("invalid_manifest", "saved version path does not match its identity")
            if not isinstance(view.get("round"), dict) or view["round"].get("state") not in (
                "open", "paused", "cancelled", "replaced", "completed", "unknown"
            ):
                raise BicError("invalid_manifest", "saved round is invalid")
            for field in ("part_ids", "event_ids"):
                values = view.get(field)
                if (not isinstance(values, list) or any(not isinstance(value, str) or not value for value in values)
                    or len(set(values)) != len(values)):
                    raise BicError("invalid_manifest", f"saved {field} are invalid")
            dependencies = view.get("dependencies")
            if not isinstance(dependencies, dict) or not {view["current_path"], view["history_path"]} <= set(dependencies):
                raise BicError("invalid_manifest", "saved version is missing dependency identities")
            for path, digest in dependencies.items():
                if (path not in (view["current_path"], view["history_path"])
                    and not re.fullmatch(r"\.brainstorming-intent/parts/" + record_id + r"/[a-f0-9]{64}\.md", path)):
                    raise BicError("invalid_manifest", "saved dependency must be an immutable same-record path")
                if not isinstance(digest, str) or not re.fullmatch(r"[a-f0-9]{64}", digest):
                    raise BicError("invalid_manifest", "saved dependency digest must be SHA-256")

    _validate_registered_material(manifest)


def _validate_part_reference(part, record_id, part_id):
    if (not _valid_entry_id(part_id) or not isinstance(part, dict)
        or set(part) != {"id", "kind", "path", "digest"} or part.get("id") != part_id
        or part.get("kind") not in ("history", "topic")
        or not isinstance(part.get("digest"), str) or not re.fullmatch(r"[a-f0-9]{64}", part["digest"])
        or part.get("path") != f"{STATE_DIRECTORY}/parts/{record_id}/{part.get('digest')}.md"):
        raise BicError("invalid_manifest", "registered part identity is invalid")


def _validate_registered_material(manifest):
    events_by_record = manifest.get("events", {})
    if not isinstance(events_by_record, dict) or set(events_by_record) - set(manifest["records"]):
        raise BicError("invalid_manifest", "events must belong to registered records")
    for record_id, metadata in manifest["records"].items():
        events = events_by_record.get(record_id, {})
        if not isinstance(events, dict) or set(events) != set(metadata["event_ids"]):
            raise BicError("invalid_manifest", "event registrations must match record event_ids")
        views = [metadata] + list(manifest.get("versions", {}).get(record_id, {}).values())
        for view in views:
            refs = view.get("part_refs", {})
            if not isinstance(refs, dict) or set(refs) != set(view["part_ids"]):
                raise BicError("invalid_manifest", "part registrations must match view part_ids")
            for part_id, part in refs.items():
                _validate_part_reference(part, record_id, part_id)
            if set(view["event_ids"]) - set(events):
                raise BicError("invalid_manifest", "view refers to unknown events")
            for event_id in view["event_ids"]:
                item = events[event_id]
                if (not _valid_entry_id(event_id) or not isinstance(item, dict)
                    or set(item) != {"id", "part_id", "anchor", "title", "conditions", "revision"}
                    or item.get("id") != event_id or not _valid_entry_id(item.get("part_id"))
                    or item["part_id"] not in refs or refs[item["part_id"]]["kind"] != "history"
                    or type(item.get("revision")) is not int or not 1 <= item["revision"] <= view["revision"]
                    or any(not isinstance(item.get(field), str) or not item[field].strip() for field in ("anchor", "title", "conditions"))):
                    raise BicError("invalid_manifest", "event identity or target is invalid")
            if view.get("source_kind") == "saved":
                expected = {view["current_path"], view["history_path"]} | {part["path"] for part in refs.values()}
                if set(view["dependencies"]) != expected or any(view["dependencies"][part["path"]] != part["digest"] for part in refs.values()):
                    raise BicError("invalid_manifest", "saved dependencies must exactly match the saved view")
    corrections = manifest.get("corrections", [])
    if not isinstance(corrections, list):
        raise BicError("invalid_manifest", "corrections must be an array")
    seen = set()
    for item in corrections:
        if (not isinstance(item, dict) or set(item) != {"record_id", "target_event", "part_id", "kind", "revision", "part"}
            or not isinstance(item.get("record_id"), str) or item["record_id"] not in manifest["records"]
            or not _valid_entry_id(item.get("target_event"))
            or item["target_event"] not in events_by_record.get(item["record_id"], {})
            or item.get("kind") not in ("superseded", "recording_error")
            or type(item.get("revision")) is not int
            or not events_by_record[item["record_id"]][item["target_event"]]["revision"] <= item["revision"] <= manifest["records"][item["record_id"]]["revision"]):
            raise BicError("invalid_manifest", "correction registration is invalid")
        _validate_part_reference(item["part"], item["record_id"], item["part_id"])
        key = (item["record_id"], item["target_event"], item["part_id"], item["kind"])
        if key in seen:
            raise BicError("invalid_manifest", "duplicate correction registration")
        seen.add(key)


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
        "part_refs": copy.deepcopy(metadata.get("part_refs", {})),
    }


def _resolve_record_view_locked(manifest, record_id, revision=None):
    if manifest is None:
        raise BicError("not_enrolled", "project has no BIC manifest")
    metadata = manifest["records"].get(record_id)
    if metadata is None:
        raise BicError("record_not_found", f"unknown record: {record_id}")
    if revision is not None and (type(revision) is not int or revision < 1):
        raise BicError("invalid_revision", "revision must be a positive integer")
    saved = manifest.get("versions", {}).get(record_id, {}).get(str(revision))
    if revision is not None and saved is not None:
        return copy.deepcopy(saved)
    if revision is not None and revision != metadata["revision"]:
        raise BicError("version_unavailable", f"{record_id} revision {revision} was not saved")
    return _view_from_metadata(record_id, metadata, manifest["schema_version"])


def resolve_record_view(project, record_id, revision=None):
    """Resolve a view while the caller holds the project lock."""
    return _resolve_record_view_locked(load_manifest(project), record_id, revision)


def collect_registered_dependencies(manifest, view):
    """Return project-relative content paths registered for this view."""
    paths = {view["current_path"], view["history_path"]}
    paths.update(part["path"] for part in view.get("part_refs", {}).values())
    paths.update(view.get("dependencies", {}))
    if "descriptor_path" in view:
        paths.add(view["descriptor_path"])
    return paths


def _registered_paths(manifest):
    paths = set()
    for record_id, metadata in manifest["records"].items():
        paths.update(collect_registered_dependencies(
            manifest, _view_from_metadata(record_id, metadata, manifest["schema_version"])
        ))
    for correction in manifest.get("corrections", []):
        paths.add(correction["part"]["path"])
    for versions in manifest.get("versions", {}).values():
        for view in versions.values():
            paths.update(collect_registered_dependencies(manifest, view))
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


def validate_record(project, manifest, record_id, *, complete=True, current_only=False):
    view = _resolve_record_view_locked(manifest, record_id)
    if manifest["schema_version"] == 1:
        record_directory = project_file(project, f"{STATE_DIRECTORY}/records/{record_id}")
        if not record_directory.is_dir():
            raise BicError("invalid_record", f"missing record directory for {record_id}")
        actual_names = {path.name for path in record_directory.iterdir() if path.is_file()}
        if actual_names != {"current.md", "history.md"}:
            raise BicError("invalid_record", f"{record_id} must contain exactly current.md and history.md")
    documents = _read_view_documents(project, view)
    if complete:
        for part in view.get("part_refs", {}).values():
            _read_part(project, part)
        for saved in manifest.get("versions", {}).get(record_id, {}).values():
            if current_only and saved["revision"] != view["revision"]:
                continue
            _verify_saved_version(project, saved)
            _read_view_documents(project, saved)
        for correction in manifest.get("corrections", []):
            if correction["record_id"] == record_id:
                _read_part(project, correction["part"])
    return documents


def _read_part(project, part, *, saved=False):
    path = project_file(project, part["path"])
    try:
        content = path.read_bytes()
        text = content.decode("utf-8")
    except (OSError, UnicodeError) as error:
        raise BicError("version_unavailable" if saved else "invalid_record", f"registered part unavailable: {error}")
    if _digest_bytes(content) != part["digest"]:
        raise BicError("version_conflict" if saved else "invalid_record", f"registered part differs: {part['id']}")
    return {"path": str(path), "text": text}


def resolve_corrections(manifest, event_ids, *, record_id=None):
    """Resolve registered later facts, with explicit record scope for local IDs."""
    if record_id is None:
        owners = {rid for rid, events in manifest.get("events", {}).items() if set(events) & event_ids}
        if len(owners) > 1:
            raise BicError("invalid_arguments", "record_id is required for ambiguous event IDs")
        record_id = next(iter(owners), None)
    return [copy.deepcopy(item) for item in manifest.get("corrections", [])
            if item["record_id"] == record_id and item["target_event"] in event_ids]


def read_record(project, record_id, revision=None, selectors=None):
    with project_lock(project, exclusive=False):
        manifest = load_manifest(project)
        view = _resolve_record_view_locked(manifest, record_id, revision)
        selected = set(selectors or ())
        if selected - set(view["event_ids"]):
            raise BicError("event_not_found", "selected event is not registered in the requested view")
        saved = view["source_kind"] == "saved"
        if saved:
            # Ordinary reads do not expand every archive dependency.
            _verify_saved_version(project, view, complete=False)
            documents = _read_view_documents(project, view)
        else:
            documents = validate_record(project, manifest, record_id, complete=False)
        events = {event_id: copy.deepcopy(manifest.get("events", {}).get(record_id, {})[event_id])
                  for event_id in view["event_ids"]}
        refs = view.get("part_refs", {})
        included = {part_id for part_id, part in refs.items() if part["kind"] == "topic"}
        included.update(events[event_id]["part_id"] for event_id in selected)
        parts = {part_id: _read_part(project, refs[part_id], saved=saved) for part_id in sorted(included)}
        corrections = []
        for relation in resolve_corrections(manifest, selected, record_id=record_id):
            corrections.append({
                "target_event": relation["target_event"], "part_id": relation["part_id"],
                "kind": relation["kind"], "original_revision": events[relation["target_event"]]["revision"],
                "view_revision": view["revision"], "source_revision": relation["revision"],
                **_read_part(project, relation["part"]),
            })
        return {
            "ok": True, "state": "read", "project": str(project),
            "record_id": record_id, "revision": view["revision"],
            "source_kind": view["source_kind"], "round": view["round"],
            **documents, "parts": parts, "corrections": corrections, "events": events,
            "part_index": {part_id: {"kind": part["kind"], "relative_path": part["path"],
                                     "path": str(project_file(project, part["path"]))}
                           for part_id, part in refs.items()},
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


def _strict_fields(value, required, optional=(), *, state="invalid_update", label="update"):
    if not isinstance(value, dict) or set(value) - set(required) - set(optional) or set(required) - set(value):
        raise BicError(state, f"{label} requires {sorted(required)}; optional fields: {sorted(optional)}")


def _round_after_update(manifest, record_id, previous, update):
    _strict_fields(update, (), ("round", "parts", "events", "corrections"))
    request = update.get("round")
    state = previous["state"]
    if "round" not in update:
        if state in ("completed", "cancelled", "replaced"):
            raise BicError("round_closed", f"round is {state}; completed rounds require evidenced reopen")
        return copy.deepcopy(previous)
    _strict_fields(request, ("action",), ("evidence",), label="round")
    action = request["action"]
    transitions = {
        "continue": ({"open", "unknown"}, state),
        "pause": ({"open", "unknown"}, "paused"),
        "resume": ({"paused"}, "open"),
        "cancel": ({"open", "paused", "unknown"}, "cancelled"),
        "replace": ({"open", "paused", "unknown"}, "replaced"),
        "reopen": ({"completed"}, "open"),
        "end": ({"open", "paused", "unknown"}, "completed"),
    }
    if not isinstance(action, str) or action not in transitions:
        raise BicError("invalid_update", "unknown round action")
    required = {
        "end": ("asked", "answer", "source"),
        "reopen": ("original_promise", "defect", "scope", "source"),
        "replace": ("successor_record_id", "source"),
    }.get(action, ("source",))
    evidence = request.get("evidence", {})
    if action == "continue" and "evidence" not in request:
        evidence = None
    else:
        _strict_fields(evidence, required, label="round evidence")
        if any(not isinstance(value, str) or not value.strip() for value in evidence.values()):
            raise BicError("invalid_update", "round evidence fields must be non-empty strings")
    allowed, target = transitions[action]
    if state not in allowed:
        error = "round_closed" if state == "completed" and action == "continue" else "invalid_transition"
        raise BicError(error, f"cannot {action} a {state} round")
    if action == "replace":
        successor = evidence["successor_record_id"]
        if successor == record_id or successor not in manifest["records"]:
            raise BicError("invalid_update", "replacement requires a distinct registered successor_record_id")
    result = {"state": target, "action": action}
    if evidence is not None:
        result["evidence"] = copy.deepcopy(evidence)
    return result


def _valid_entry_id(value):
    return isinstance(value, str) and PART_ID_PATTERN.fullmatch(value) is not None


def _anchor_exists(text, anchor):
    if not isinstance(anchor, str) or not anchor:
        return False
    if re.search(r"<(?:a|span)\b[^>]*\bid=[\"']" + re.escape(anchor) + r"[\"']", text):
        return True
    for heading in re.findall(r"^#{1,6}\s+(.+?)\s*#*\s*$", text, re.MULTILINE):
        slug = re.sub(r"[^\w\- ]", "", heading.lower()).replace(" ", "-")
        if slug == anchor:
            return True
    return False


def prepare_parts(project, record_id, update, *, manifest=None, revision=None):
    """Prepare root-grouped immutable material while the caller owns the lock."""
    _strict_fields(update, (), ("round", "parts", "events", "corrections"))
    manifest = manifest if manifest is not None else (load_manifest(project) or _new_manifest())
    metadata = manifest["records"].get(record_id, {})
    revision = revision if revision is not None else metadata.get("revision", 0) + 1
    refs = copy.deepcopy(metadata.get("part_refs", {}))
    events = copy.deepcopy(manifest.get("events", {}).get(record_id, {}))
    relations = []
    drafts = {}
    for field in ("parts", "events", "corrections"):
        if not isinstance(update.get(field, []), list):
            raise BicError("invalid_update", f"{field} must be an array")
    for item in update.get("parts", []):
        _strict_fields(item, ("id", "kind", "draft"), label="part")
        part_id = item["id"]
        if not _valid_entry_id(part_id) or part_id in drafts or item["kind"] not in ("history", "topic"):
            raise BicError("invalid_update", "part IDs must be unique and safe; kind must be history or topic")
        if not isinstance(item["draft"], str) or not item["draft"]:
            raise BicError("invalid_update", "part draft must be a non-empty project path")
        try:
            text = _draft_path(project, item["draft"]).read_text(encoding="utf-8")
        except (OSError, UnicodeError) as error:
            raise BicError("invalid_draft", f"cannot read part draft: {error}")
        if not text.strip():
            raise BicError("invalid_update", "part text must not be empty")
        drafts[part_id] = {"kind": item["kind"], "text": text}
    for item in update.get("events", []):
        _strict_fields(item, ("id", "part_id", "anchor", "title", "conditions"), label="event")
        if (not _valid_entry_id(item["id"]) or item["id"] in events
            or not _valid_entry_id(item["part_id"])
            or any(not isinstance(item[field], str) or not item[field].strip() for field in ("anchor", "title", "conditions"))):
            raise BicError("invalid_update", "event IDs must be new and fields non-empty")
        # New event headers are prepared with their immutable history part.
        draft = drafts.get(item["part_id"])
        if draft is None or draft["kind"] != "history" or not _anchor_exists(draft["text"], item["anchor"]):
            raise BicError("invalid_update", "event must target an existing anchor in a submitted history part")
        events[item["id"]] = {**item, "revision": revision}
    seen_relations = set()
    for item in update.get("corrections", []):
        _strict_fields(item, ("target_event", "part_id", "kind"), label="correction")
        if (not _valid_entry_id(item["target_event"]) or item["target_event"] not in events
            or not _valid_entry_id(item["part_id"]) or item["part_id"] not in set(refs) | set(drafts)
            or item["kind"] not in ("superseded", "recording_error")):
            raise BicError("invalid_update", "correction requires a registered event, part, and supported kind")
        key = (item["target_event"], item["part_id"], item["kind"])
        if key in seen_relations or any(key == (old["target_event"], old["part_id"], old["kind"])
                                      for old in manifest.get("corrections", []) if old["record_id"] == record_id):
            raise BicError("invalid_update", "duplicate correction relation")
        seen_relations.add(key)
        relations.append({**item, "record_id": record_id, "revision": revision})
    content = {}
    for part_id, draft in drafts.items():
        header = f"# {record_id} Part {part_id} ({draft['kind']})\n\n"
        if draft["kind"] == "history":
            event_ids = sorted({event_id for event_id, item in events.items() if item["part_id"] == part_id}
                               | {item["target_event"] for item in relations if item["part_id"] == part_id})
            header += "Recorded event IDs: " + (", ".join(event_ids) or "none") + "\n\n"
            for event_id in event_ids:
                header += f"Current corrections: `bic.py read --project {shlex.quote(str(project))} --record-id {record_id} --current --event {event_id}`\n\n"
            header += "Without the current project, this file cannot reveal later corrections.\n\n"
        text = header + draft["text"]
        digest = _digest_bytes(text.encode("utf-8"))
        relative_path = f"{STATE_DIRECTORY}/parts/{record_id}/{digest}.md"
        old = refs.get(part_id)
        if old and (old["kind"] != "topic" or draft["kind"] != "topic") and old["path"] != relative_path:
            raise BicError("invalid_update", "historical part IDs are immutable; submit a new part ID")
        refs[part_id] = {"id": part_id, "kind": draft["kind"], "path": relative_path, "digest": digest}
        content[relative_path] = text
    for relation in relations:
        relation["part"] = copy.deepcopy(refs[relation["part_id"]])
    # Validate registered inputs before publishing a replacement pair.
    for part_id, part in refs.items():
        if part_id not in drafts:
            _read_part(project, part)
    for relative_path, text in content.items():
        _immutable_write(project, relative_path, text)
    return {"part_refs": refs, "events": events, "corrections": relations}


def _render_navigation(text, kind, project, record_id, refs, events, corrections):
    # Reserved mechanical blocks are replaced on read -> draft round trips.
    text = re.sub(r"\n*<!-- BIC-NAV:BEGIN -->.*?<!-- BIC-NAV:END -->\n*", "\n", text, flags=re.DOTALL).rstrip() + "\n"
    lines = []
    if kind == "current":
        for part_id, part in sorted(refs.items()):
            if part["kind"] == "topic":
                lines.append(f"- Effective topic {part_id}: `{part['path']}`")
    else:
        for event_id, event in sorted(events.items()):
            path = refs[event["part_id"]]["path"]
            lines.append(f"- Event {event_id}: {event['title']} ({event['conditions']}); `{path}#{event['anchor']}`")
            lines.append(f"  Current corrections: `bic.py read --project {shlex.quote(str(project))} --record-id {record_id} --current --event {event_id}`")
    if lines:
        title = "Registered effective topics" if kind == "current" else "Registered historical events and corrections"
        text += f"\n<!-- BIC-NAV:BEGIN -->\n## {title}\n\n" + "\n".join(lines) + "\n<!-- BIC-NAV:END -->\n"
    return text


def _digest_bytes(content):
    return hashlib.sha256(content).hexdigest()


def _immutable_write(project, relative_path, text):
    path = project_file(project, relative_path)
    if path.exists():
        if not path.is_file() or path.read_bytes() != text.encode("utf-8"):
            raise BicError("version_conflict", f"saved content differs: {relative_path}")
    else:
        atomic_write(path, text)


def _verify_saved_version(project, view, *, complete=True):
    try:
        descriptor_path = project_file(project, view["descriptor_path"])
        descriptor = json.loads(descriptor_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise BicError("version_unavailable", f"saved version descriptor unavailable: {error}")
    if descriptor != view:
        raise BicError("version_conflict", "saved version descriptor differs from its registration")
    paths = set(view["dependencies"]) if complete else {view["current_path"], view["history_path"]}
    for relative_path in paths:
        path = project_file(project, relative_path)
        try:
            actual = _digest_bytes(path.read_bytes())
        except OSError as error:
            raise BicError("version_unavailable", f"saved dependency unavailable: {error}")
        if actual != view["dependencies"][relative_path]:
            raise BicError("version_conflict", f"saved dependency differs: {relative_path}")


def _save_version_locked(project, manifest, view):
    """Prepare immutable saved input; the caller owns lock and manifest publication."""
    existing = manifest.get("versions", {}).get(view["record_id"], {}).get(str(view["revision"]))
    if existing is not None:
        _verify_saved_version(project, existing)
        return copy.deepcopy(existing)
    if view["source_kind"] == "saved":
        raise BicError("version_unavailable", "saved version is not registered")
    documents = _read_view_documents(project, view)
    for part in view.get("part_refs", {}).values():
        _read_part(project, part)
    saved = copy.deepcopy(view)
    base = f"{STATE_DIRECTORY}/versions/{view['record_id']}/r{view['revision']}"
    saved.update({"source_kind": "saved", "current_path": f"{base}/current.md",
                  "history_path": f"{base}/history.md", "descriptor_path": f"{base}/version.json"})
    dependencies = {}
    for relative_path in collect_registered_dependencies(manifest, view) - {view['current_path'], view['history_path']}:
        path = project_file(project, relative_path)
        try:
            dependencies[relative_path] = _digest_bytes(path.read_bytes())
        except OSError as error:
            raise BicError("invalid_record", f"cannot preserve dependency: {error}")
    for kind in ("current", "history"):
        dependencies[saved[f"{kind}_path"]] = _digest_bytes(documents[kind]["text"].encode("utf-8"))
    saved["dependencies"] = dependencies
    # Check all existing destinations before any new version file is written.
    content = {saved[f"{kind}_path"]: documents[kind]["text"] for kind in ("current", "history")}
    content[saved["descriptor_path"]] = json.dumps(saved, indent=2, sort_keys=True) + "\n"
    for relative_path, text in content.items():
        path = project_file(project, relative_path)
        if path.exists() and (not path.is_file() or path.read_bytes() != text.encode("utf-8")):
            raise BicError("version_conflict", f"saved content differs: {relative_path}")
    for relative_path, text in content.items():
        _immutable_write(project, relative_path, text)
    _verify_saved_version(project, saved)
    return saved


def _register_saved_version(manifest, saved):
    manifest.setdefault("versions", {}).setdefault(saved["record_id"], {})[str(saved["revision"])] = saved
    manifest["records"][saved["record_id"]]["commit_pending"] = True
    manifest["commit_pending"] = True


def save_version(project, record_id, revision):
    with project_lock(project, exclusive=True):
        manifest = load_manifest(project)
        require_schema_v2(manifest)
        view = _resolve_record_view_locked(manifest, record_id, revision)
        saved = _save_version_locked(project, manifest, view)
        if view["source_kind"] != "saved":
            _register_saved_version(manifest, saved)
            _publish_manifest(project, manifest)
        return {"ok": True, "state": "saved", "record_id": record_id, "revision": revision,
                "current_path": str(project_file(project, saved["current_path"])),
                "history_path": str(project_file(project, saved["history_path"]))}


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
        round_metadata = _round_after_update(manifest, record_id, metadata.get("round") if metadata else {"state": "open"}, update)
        prepared = prepare_parts(project, record_id, update, manifest=manifest, revision=revision)
        all_corrections = manifest.get("corrections", []) + prepared["corrections"]
        rendered = {kind: _render_navigation(draft_set[kind], kind, project, record_id,
                                             prepared["part_refs"], prepared["events"], all_corrections)
                    for kind in ("current", "history")}
        for kind in ("current", "history"):
            validate_document(rendered[kind], kind, record_id, revision)
        active_slot = metadata["active_slot"] if metadata else None
        next_slot = "b" if active_slot == "a" else "a"
        base = f"records/{record_id}/slots/{next_slot}"
        destinations = {kind: project_file(project, f"{STATE_DIRECTORY}/{base}/{kind}.md")
                        for kind in ("current", "history")}
        for kind, destination in destinations.items():
            atomic_write(destination, rendered[kind])
        next_manifest = copy.deepcopy(manifest)
        next_metadata = copy.deepcopy(metadata) if metadata else {
            "round": {"state": "open"}, "part_ids": [], "event_ids": [],
        }
        next_metadata.update({
            "round": round_metadata, "part_refs": prepared["part_refs"],
            "part_ids": sorted(prepared["part_refs"]), "event_ids": sorted(prepared["events"]),
            "revision": revision, "active_slot": next_slot, "commit_pending": True,
            "current_path": f"{base}/current.md", "history_path": f"{base}/history.md",
        })
        next_manifest["records"][record_id] = next_metadata
        if prepared["events"]:
            next_manifest.setdefault("events", {})[record_id] = prepared["events"]
        if all_corrections:
            next_manifest["corrections"] = all_corrections
        if actual_revision == 0:
            next_manifest["next_record_number"] += 1
        next_manifest["writer_version"] = WRITER_VERSION
        next_manifest["commit_pending"] = True
        if round_metadata.get("action") == "end":
            saved = _save_version_locked(project, next_manifest, _view_from_metadata(record_id, next_metadata, SCHEMA_VERSION))
            _register_saved_version(next_manifest, saved)
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


def binding_file(project):
    return project_file(project, f"{STATE_DIRECTORY}/session-bindings.json", state="invalid_bindings")


def load_bindings(project):
    path = binding_file(project)
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
    return sorted({f"{STATE_DIRECTORY}/manifest.json"} | _registered_paths(manifest))


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
    return read_record(project_path(arguments.project), arguments.record_id, arguments.revision, set(arguments.event or []))


def command_save_version(arguments):
    return save_version(project_path(arguments.project), arguments.record_id, arguments.revision)


def command_migrate(arguments):
    return migrate_project(project_path(arguments.project), arguments.expected_schema)


def command_validate(arguments):
    if arguments.current_only:
        if not arguments.record_id or arguments.expected_revision is None:
            raise BicError("invalid_arguments", "--current-only requires --record-id and --expected-revision")
    elif arguments.expected_revision is not None:
        raise BicError("invalid_arguments", "--expected-revision requires --current-only")
    project = project_path(arguments.project)
    with project_lock(project, exclusive=False):
        manifest = load_manifest(project)
        if manifest is None:
            raise BicError("not_enrolled", "project has no BIC manifest")
        if arguments.current_only:
            # Compare the live view under the same lock as its body validation;
            # resolving the requested revision could instead select an old save.
            view = _resolve_record_view_locked(manifest, arguments.record_id)
            if arguments.expected_revision != view["revision"]:
                raise BicError("revision_conflict",
                               f"expected revision {arguments.expected_revision}, found {view['revision']}")
        record_ids = [arguments.record_id] if arguments.record_id else sorted(manifest["records"])
        for record_id in record_ids:
            validate_record(project, manifest, record_id, current_only=arguments.current_only)
        payload = {"ok": True, "state": "valid", "records": record_ids}
        if arguments.current_only:
            payload["validation_scope"] = "current"
        if arguments.record_id:
            view = _resolve_record_view_locked(manifest, arguments.record_id)
            payload.update({"record_id": arguments.record_id, "revision": view["revision"],
                            "current_path": str(project_file(project, view["current_path"])),
                            "history_path": str(project_file(project, view["history_path"]))})
        return payload


def command_bind(arguments):
    if arguments.plugin_data is not None:
        raise BicError("binding_migration_required", "--plugin-data is no longer used; use bind --project PROJECT for project-local saved-input bindings. Existing external files are unchanged.")
    if not arguments.project:
        raise BicError("invalid_arguments", "--project is required for binding and lookup")
    if not arguments.session_id.strip():
        raise BicError("invalid_arguments", "--session-id must be non-empty")
    project = project_path(arguments.project)
    with project_lock(project, exclusive=not arguments.lookup):
        bindings = load_bindings(project)
        if arguments.lookup:
            if arguments.session_id not in bindings["sessions"]:
                raise BicError("unbound_session", "session has no BIC binding")
            binding = bindings["sessions"][arguments.session_id]
            if not isinstance(binding, dict):
                raise BicError("invalid_bindings", "session binding entry must be an object")
            validate_binding_entry(binding)
            bound_project, exists = resolve_binding_project(binding["project"])
            if bound_project != project:
                raise BicError("stale_binding", "binding belongs to a different project; it cannot be inferred or relocated")
            manifest = load_manifest(project)
            if manifest is None:
                raise BicError("stale_binding", "bound project is no longer enrolled")
            try:
                view = _resolve_record_view_locked(manifest, binding["record_id"], binding["revision"])
            except BicError as error:
                raise BicError("stale_binding", str(error))
            if view["source_kind"] != "saved":
                raise BicError("stale_binding", "binding does not refer to a registered saved input")
            expected = {f"{kind}_path": str(project_file(project, view[f"{kind}_path"])) for kind in ("current", "history")}
            if any(binding[field] != path for field, path in expected.items()):
                raise BicError("stale_binding", "bound record paths differ from the saved input")
            _verify_saved_version(project, view)
            _read_view_documents(project, view)
            return {"ok": True, "state": "bound", **binding_payload(binding)}
        manifest = load_manifest(project)
        require_schema_v2(manifest)
        if manifest is None:
            raise BicError("not_enrolled", "project has no BIC manifest")
        if not arguments.record_id:
            raise BicError("record_required", "--record-id is required; binding never guesses")
        if arguments.expected_revision is None:
            raise BicError("invalid_arguments", "--expected-revision is required")
        _select_apply_target(manifest, arguments.record_id, arguments.expected_revision)
        view = _resolve_record_view_locked(manifest, arguments.record_id, arguments.expected_revision)
        saved = _save_version_locked(project, manifest, view)
        if view["source_kind"] != "saved":
            _register_saved_version(manifest, saved)
            _publish_manifest(project, manifest)
        binding = {"project": str(project), "record_id": arguments.record_id,
                   "revision": arguments.expected_revision,
                   **{f"{kind}_path": str(project_file(project, saved[f"{kind}_path"])) for kind in ("current", "history")}}
        if bindings["sessions"].get(arguments.session_id) != binding:
            bindings["sessions"][arguments.session_id] = binding
            atomic_write(binding_file(project), json.dumps(bindings, indent=2, sort_keys=True) + "\n")
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
    validate_parser.add_argument("--current-only", action="store_true",
                                 help="validate only the exact current revision and its dependencies")
    validate_parser.add_argument("--expected-revision", type=int)
    validate_parser.set_defaults(handler=command_validate)

    read_parser = subparsers.add_parser("read")
    read_parser.add_argument("--project", required=True)
    read_parser.add_argument("--record-id", required=True)
    target = read_parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--current", action="store_true")
    target.add_argument("--revision", type=int)
    read_parser.add_argument("--event", action="append")
    read_parser.set_defaults(handler=command_read)

    save_parser = subparsers.add_parser("save-version")
    save_parser.add_argument("--project", required=True)
    save_parser.add_argument("--record-id", required=True)
    save_parser.add_argument("--revision", required=True, type=int)
    save_parser.set_defaults(handler=command_save_version)

    migrate_parser = subparsers.add_parser("migrate")
    migrate_parser.add_argument("--project", required=True)
    migrate_parser.add_argument("--expected-schema", required=True, type=int)
    migrate_parser.set_defaults(handler=command_migrate)

    bind_parser = subparsers.add_parser("bind")
    bind_parser.add_argument("--plugin-data", help="legacy parameter; returns project-local migration instructions")
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
