#!/usr/bin/env python3
"""Deterministic mechanics for controller-authored BIC records."""

import argparse
import fcntl
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path


SCHEMA_VERSION = 1
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


def manifest_path(project):
    return project / STATE_DIRECTORY / "manifest.json"


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
    if schema_version != SCHEMA_VERSION:
        raise BicError(
            "compatibility_hold",
            f"unsupported schema_version {schema_version!r}; supported version is 1",
            schema_version=schema_version,
        )
    validate_schema_v1_manifest(manifest)
    return manifest


def validate_schema_v1_manifest(manifest):
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
        expected_paths = {
            "current_path": f"records/{record_id}/current.md",
            "history_path": f"records/{record_id}/history.md",
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
    finally:
        if temporary_name and os.path.exists(temporary_name):
            os.unlink(temporary_name)


def render_draft(path, record_id, revision):
    try:
        draft = Path(path).read_text(encoding="utf-8")
    except OSError as error:
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


def validate_record(project, manifest, record_id):
    metadata = manifest["records"].get(record_id)
    if metadata is None:
        raise BicError("record_not_found", f"unknown record: {record_id}")
    revision = metadata.get("revision")
    if not isinstance(revision, int) or revision < 1:
        raise BicError("invalid_manifest", f"invalid revision for {record_id}")
    record_directory = project / STATE_DIRECTORY / "records" / record_id
    expected_names = {"current.md", "history.md"}
    if not record_directory.is_dir():
        raise BicError("invalid_record", f"missing record directory for {record_id}")
    actual_names = {path.name for path in record_directory.iterdir() if path.is_file()}
    if actual_names != expected_names:
        raise BicError(
            "invalid_record",
            f"{record_id} must contain exactly current.md and history.md",
        )
    try:
        current = (record_directory / "current.md").read_text(encoding="utf-8")
        history = (record_directory / "history.md").read_text(encoding="utf-8")
    except OSError as error:
        raise BicError("invalid_record", f"cannot read {record_id}: {error}")
    try:
        validate_document(current, "current", record_id, revision)
        validate_document(history, "history", record_id, revision)
    except BicError as error:
        raise BicError("invalid_record", str(error))


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
        base = f"{STATE_DIRECTORY}/records/{record_id}"
        paths.extend((f"{base}/current.md", f"{base}/history.md"))
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
    manifest = load_manifest(project)
    if manifest is None:
        return {"ok": True, "state": "not_enrolled"}
    record_ids = sorted(manifest["records"])
    state = "commit_pending" if manifest.get("commit_pending") else "active"
    return {
        "ok": True,
        "state": state,
        "schema_version": SCHEMA_VERSION,
        "records": record_ids,
        "revisions": {
            record_id: manifest["records"][record_id]["revision"]
            for record_id in record_ids
        },
    }


def command_apply(arguments):
    project = project_path(arguments.project)
    root_fd = os.open(str(project), os.O_RDONLY)
    try:
        fcntl.flock(root_fd, fcntl.LOCK_EX)
        manifest = load_manifest(project)
        if manifest is None:
            manifest = {
                "schema_version": SCHEMA_VERSION,
                "writer_version": WRITER_VERSION,
                "compatibility_state": "compatible",
                "project_state": "active",
                "commit_pending": False,
                "next_record_number": 1,
                "records": {},
            }

        if arguments.record_id:
            record_id = arguments.record_id
            if not RECORD_ID_PATTERN.fullmatch(record_id):
                raise BicError("invalid_record_id", f"invalid record ID: {record_id}")
            metadata = manifest["records"].get(record_id)
            if metadata is None:
                raise BicError("record_not_found", f"unknown record: {record_id}")
            actual_revision = metadata.get("revision")
        else:
            next_record_number = manifest["next_record_number"]
            if next_record_number > 9999:
                raise BicError(
                    "record_id_exhausted",
                    "four-digit BIC record IDs are exhausted at BIC-9999",
                )
            record_id = f"BIC-{next_record_number:04d}"
            actual_revision = 0

        if arguments.expected_revision != actual_revision:
            raise BicError(
                "revision_conflict",
                f"expected revision {arguments.expected_revision}, found {actual_revision}",
            )
        revision = actual_revision + 1
        current = render_draft(arguments.current_draft, record_id, revision)
        history = render_draft(arguments.history_draft, record_id, revision)
        validate_document(current, "current", record_id, revision)
        validate_document(history, "history", record_id, revision)

        record_directory = project / STATE_DIRECTORY / "records" / record_id
        atomic_write(record_directory / "current.md", current)
        atomic_write(record_directory / "history.md", history)
        manifest["records"][record_id] = {
            "revision": revision,
            "commit_pending": True,
            "current_path": f"records/{record_id}/current.md",
            "history_path": f"records/{record_id}/history.md",
        }
        if actual_revision == 0:
            manifest["next_record_number"] += 1
        manifest["commit_pending"] = True
        atomic_write(
            manifest_path(project),
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        )
    finally:
        os.close(root_fd)

    return {
        "ok": True,
        "state": "commit_pending",
        "record_id": record_id,
        "revision": revision,
        "current_path": str(record_directory / "current.md"),
        "history_path": str(record_directory / "history.md"),
    }


def command_validate(arguments):
    project = project_path(arguments.project)
    manifest = load_manifest(project)
    if manifest is None:
        raise BicError("not_enrolled", "project has no BIC manifest")
    record_ids = [arguments.record_id] if arguments.record_id else sorted(manifest["records"])
    for record_id in record_ids:
        validate_record(project, manifest, record_id)
    payload = {"ok": True, "state": "valid", "records": record_ids}
    if arguments.record_id:
        record_id = arguments.record_id
        record_directory = project / STATE_DIRECTORY / "records" / record_id
        payload.update(
            {
                "record_id": record_id,
                "revision": manifest["records"][record_id]["revision"],
                "current_path": str(record_directory / "current.md"),
                "history_path": str(record_directory / "history.md"),
            }
        )
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
        record_directory = project / STATE_DIRECTORY / "records" / record_id
        expected_paths = {
            "current_path": str(record_directory / "current.md"),
            "history_path": str(record_directory / "history.md"),
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
    record_directory = project / STATE_DIRECTORY / "records" / arguments.record_id
    binding = {
        "project": str(project),
        "record_id": arguments.record_id,
        "revision": arguments.expected_revision,
        "current_path": str(record_directory / "current.md"),
        "history_path": str(record_directory / "history.md"),
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
        staged = run_git(project, ["add", "--", *snapshot_paths])
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
    apply_parser.add_argument("--expected-revision", required=True, type=int)
    apply_parser.set_defaults(handler=command_apply)

    validate_parser = subparsers.add_parser("validate")
    validate_parser.add_argument("--project", required=True)
    validate_parser.add_argument("--record-id")
    validate_parser.set_defaults(handler=command_validate)

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


if __name__ == "__main__":
    sys.exit(main())
