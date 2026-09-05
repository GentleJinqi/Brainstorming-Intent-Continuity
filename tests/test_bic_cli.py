import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
CLI = (
    REPOSITORY_ROOT
    / "plugins"
    / "brainstorming-intent-continuity"
    / "skills"
    / "brainstorming-intent-continuity"
    / "scripts"
    / "bic.py"
)


CURRENT_DRAFT = """# {{RECORD_ID}} Current Intent

Revision: {{REVISION}}

## Goal and non-goals

Keep the approved direction; do not expand scope.

## Approved decisions

Use the deterministic writer.

## Explicit prohibitions

Do not infer semantics from chat.

## Rationale and consequences

The controller remains semantic authority.

## Observable proof

The record validates and can be recovered.

## Examples and edge cases

Repeated status calls do not create files.

## Open questions

Whether a later hook should be promoted remains open.

## Current Intent Map

```mermaid
flowchart TD
    G[Goal] --> D[Approved decision]
```
"""


HISTORY_DRAFT = """# {{RECORD_ID}} History

Revision: {{REVISION}}

## Rejected or superseded directions

Transcript persistence was rejected.

## Key turning points

The design selected project-owned records.

## Material counterexamples

A spec-free brainstorming path still needs continuity.

## Evolution Map

```mermaid
flowchart LR
    A[Transcript authority] -->|rejected| B[Structured record]
```
"""


class BicCliTestCase(unittest.TestCase):
    def setUp(self):
        base = REPOSITORY_ROOT / '.tmp'
        base.mkdir(exist_ok=True)
        self.temporary_directory = tempfile.TemporaryDirectory(dir=base)
        self.root = Path(self.temporary_directory.name)
        self.project = self.root / "project"
        self.project.mkdir()
        subprocess.run(["git", "init", "-q", str(self.project)], check=True)
        self.scratch = self.project / ".tmp"
        self.scratch.mkdir()
        self.env = dict(os.environ, TMPDIR=str(self.scratch), PYTHONDONTWRITEBYTECODE="1")
        self.current_draft = self.scratch / "current-draft.md"
        self.history_draft = self.scratch / "history-draft.md"
        self.current_draft.write_text(CURRENT_DRAFT, encoding="utf-8")
        self.history_draft.write_text(HISTORY_DRAFT, encoding="utf-8")

    def tearDown(self):
        self.temporary_directory.cleanup()

    def run_cli(self, *arguments):
        return subprocess.run(
            [sys.executable, str(CLI), *map(str, arguments)],
            cwd=self.project,
            env=self.env,
            text=True,
            capture_output=True,
            check=False,
        )

    def apply(self, *extra_arguments):
        return self.run_cli(
            "apply",
            "--project",
            self.project,
            "--current-draft",
            self.current_draft,
            "--history-draft",
            self.history_draft,
            "--expected-revision",
            "0",
            *extra_arguments,
        )

    def assert_success(self, result):
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
        return json.loads(result.stdout)

    def test_status_is_lazy_and_repeated_status_does_not_write(self):
        state_directory = self.project / ".brainstorming-intent"
        self.assertFalse(state_directory.exists())

        first = self.assert_success(
            self.run_cli("status", "--project", self.project)
        )
        second = self.assert_success(
            self.run_cli("status", "--project", self.project)
        )

        self.assertEqual(first, {"ok": True, "state": "not_enrolled"})
        self.assertEqual(second, first)
        self.assertFalse(state_directory.exists())

    def test_first_apply_creates_only_manifest_and_two_record_files(self):
        result = self.assert_success(self.apply())

        state_directory = self.project / ".brainstorming-intent"
        relative_files = sorted(
            path.relative_to(state_directory).as_posix()
            for path in state_directory.rglob("*")
            if path.is_file()
        )
        self.assertEqual(
            relative_files,
            [
                "manifest.json",
                "records/BIC-0001/slots/a/current.md",
                "records/BIC-0001/slots/a/history.md",
            ],
        )
        self.assertEqual(result["record_id"], "BIC-0001")
        self.assertEqual(result["revision"], 1)
        self.assertEqual(result["state"], "commit_pending")

        manifest = json.loads(
            (state_directory / "manifest.json").read_text(encoding="utf-8")
        )
        self.assertEqual(manifest["schema_version"], 2)
        self.assertEqual(manifest["writer_version"], "1.0.1")
        self.assertIn("compatibility_state", manifest)
        self.assertEqual(manifest["compatibility_state"], "compatible")
        self.assertTrue(manifest["commit_pending"])
        self.assertEqual(manifest["records"]["BIC-0001"]["revision"], 1)

        current = (
            state_directory / "records" / "BIC-0001" / "slots" / "a" / "current.md"
        ).read_text(encoding="utf-8")
        history = (
            state_directory / "records" / "BIC-0001" / "slots" / "a" / "history.md"
        ).read_text(encoding="utf-8")
        self.assertIn("# BIC-0001 Current Intent", current)
        self.assertIn("Revision: 1", current)
        self.assertIn("# BIC-0001 History", history)
        self.assertIn("Revision: 1", history)
        self.assertNotIn("{{RECORD_ID}}", current + history)
        self.assertNotIn("{{REVISION}}", current + history)

    def test_apply_returns_the_exact_handoff_pointer(self):
        payload = self.assert_success(self.apply())
        record_directory = (
            self.project.resolve()
            / ".brainstorming-intent"
            / "records"
            / "BIC-0001"
            / "slots"
            / "a"
        )

        self.assertEqual(payload["record_id"], "BIC-0001")
        self.assertEqual(payload["revision"], 1)
        self.assertEqual(payload.get("current_path"), str(record_directory / "current.md"))
        self.assertEqual(payload.get("history_path"), str(record_directory / "history.md"))

    def test_apply_rejects_a_missing_required_section_without_creating_state(self):
        self.current_draft.write_text(
            CURRENT_DRAFT.replace("## Explicit prohibitions", "## Other notes"),
            encoding="utf-8",
        )

        result = self.apply()

        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(result.stdout, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["state"], "invalid_draft")
        self.assertIn("## Explicit prohibitions", payload["error"])
        self.assertFalse((self.project / ".brainstorming-intent").exists())

    def test_apply_rejects_a_missing_mermaid_block_without_creating_state(self):
        self.history_draft.write_text(
            HISTORY_DRAFT.replace("```mermaid", "```text"), encoding="utf-8"
        )

        result = self.apply()

        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(result.stdout, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["state"], "invalid_draft")
        self.assertIn("Mermaid", payload["error"])
        self.assertFalse((self.project / ".brainstorming-intent").exists())

    def test_apply_requires_mermaid_inside_each_map_section(self):
        cases = (
            (
                self.current_draft,
                CURRENT_DRAFT.replace(
                    "Use the deterministic writer.",
                    "Use the deterministic writer.\n\n"
                    "```mermaid\nflowchart LR\n    X[Misplaced] --> Y[Earlier]\n```",
                ).replace(
                    "```mermaid\nflowchart TD\n    G[Goal] --> D[Approved decision]\n```",
                    "No current map projection is present.",
                ),
                "## Current Intent Map",
            ),
            (
                self.history_draft,
                HISTORY_DRAFT.replace(
                    "Transcript persistence was rejected.",
                    "Transcript persistence was rejected.\n\n"
                    "```mermaid\nflowchart LR\n    X[Misplaced] --> Y[Earlier]\n```",
                ).replace(
                    "```mermaid\nflowchart LR\n"
                    "    A[Transcript authority] -->|rejected| B[Structured record]\n```",
                    "No evolution map projection is present.",
                ),
                "## Evolution Map",
            ),
        )

        for draft_path, malformed_draft, map_heading in cases:
            with self.subTest(map_heading=map_heading):
                self.current_draft.write_text(CURRENT_DRAFT, encoding="utf-8")
                self.history_draft.write_text(HISTORY_DRAFT, encoding="utf-8")
                draft_path.write_text(malformed_draft, encoding="utf-8")

                result = self.apply()

                self.assertNotEqual(result.returncode, 0)
                self.assertTrue(result.stdout, result.stderr)
                payload = json.loads(result.stdout)
                self.assertEqual(payload["state"], "invalid_draft")
                self.assertIn(map_heading, payload["error"])
                self.assertFalse((self.project / ".brainstorming-intent").exists())

    def test_apply_rejects_a_stale_expected_revision_without_writing(self):
        self.assert_success(self.apply())
        state_directory = self.project / ".brainstorming-intent"
        before = {
            path.relative_to(state_directory): path.read_bytes()
            for path in state_directory.rglob("*")
            if path.is_file()
        }
        time.sleep(0.01)

        result = self.run_cli(
            "apply",
            "--project",
            self.project,
            "--record-id",
            "BIC-0001",
            "--current-draft",
            self.current_draft,
            "--history-draft",
            self.history_draft,
            "--expected-revision",
            "0",
        )

        self.assertNotEqual(result.returncode, 0)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["state"], "revision_conflict")
        after = {
            path.relative_to(state_directory): path.read_bytes()
            for path in state_directory.rglob("*")
            if path.is_file()
        }
        self.assertEqual(after, before)

    def test_apply_fails_before_rendering_when_four_digit_record_ids_are_exhausted(self):
        self.assert_success(self.apply())
        state_directory = self.project / ".brainstorming-intent"
        old_record_directory = state_directory / "records" / "BIC-0001"
        exhausted_record_directory = state_directory / "records" / "BIC-9999"
        old_record_directory.rename(exhausted_record_directory)
        for filename in ("current.md", "history.md"):
            record_path = exhausted_record_directory / "slots" / "a" / filename
            record_path.write_text(
                record_path.read_text(encoding="utf-8").replace(
                    "BIC-0001", "BIC-9999"
                ),
                encoding="utf-8",
            )
        manifest_path = state_directory / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        metadata = manifest["records"].pop("BIC-0001")
        metadata["current_path"] = "records/BIC-9999/slots/a/current.md"
        metadata["history_path"] = "records/BIC-9999/slots/a/history.md"
        manifest["records"]["BIC-9999"] = metadata
        manifest["next_record_number"] = 10000
        manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        self.assert_success(self.run_cli("validate", "--project", self.project))
        before = {
            path.relative_to(state_directory): (path.read_bytes(), path.stat().st_mtime_ns)
            for path in state_directory.rglob("*")
            if path.is_file()
        }
        time.sleep(0.01)

        result = self.run_cli(
            "apply",
            "--project",
            self.project,
            "--current-draft",
            self.root / "must-not-be-read-current.md",
            "--history-draft",
            self.root / "must-not-be-read-history.md",
            "--expected-revision",
            "0",
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(len(result.stdout.strip().splitlines()), 1)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["state"], "record_id_exhausted")
        self.assertNotIn("draft", payload["error"].lower())
        after = {
            path.relative_to(state_directory): (path.read_bytes(), path.stat().st_mtime_ns)
            for path in state_directory.rglob("*")
            if path.is_file()
        }
        self.assertEqual(after, before)

    def configure_git_identity_and_baseline(self):
        subprocess.run(
            ["git", "config", "user.name", "BIC Test"],
            cwd=self.project,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "bic-test@example.invalid"],
            cwd=self.project,
            check=True,
        )
        (self.project / "unrelated-staged.txt").write_text(
            "baseline staged\n", encoding="utf-8"
        )
        (self.project / "unrelated-modified.txt").write_text(
            "baseline modified\n", encoding="utf-8"
        )
        subprocess.run(["git", "add", "--", "."], cwd=self.project, check=True)
        subprocess.run(
            ["git", "commit", "-q", "-m", "baseline"],
            cwd=self.project,
            check=True,
        )

    def update_record(self, record_id="BIC-0001", expected_revision=1):
        return self.run_cli(
            "apply",
            "--project",
            self.project,
            "--record-id",
            record_id,
            "--current-draft",
            self.current_draft,
            "--history-draft",
            self.history_draft,
            "--expected-revision",
            str(expected_revision),
        )

    def commit_snapshot(self, message="BIC registry snapshot"):
        return self.run_cli(
            "commit-snapshot",
            "--project",
            self.project,
            "--message",
            message,
        )

    def test_commit_snapshot_is_a_clean_checkout_valid_multilineage_registry(self):
        self.configure_git_identity_and_baseline()
        (self.project / "unrelated-staged.txt").write_text(
            "staged change\n", encoding="utf-8"
        )
        subprocess.run(
            ["git", "add", "--", "unrelated-staged.txt"],
            cwd=self.project,
            check=True,
        )
        (self.project / "unrelated-modified.txt").write_text(
            "unstaged change\n", encoding="utf-8"
        )
        self.assert_success(self.apply())
        self.assert_success(self.apply())
        staged_diff_before = subprocess.run(
            ["git", "diff", "--cached", "--binary", "--", "unrelated-staged.txt"],
            cwd=self.project,
            env=self.env,
            text=True,
            capture_output=True,
            check=True,
        ).stdout
        staged_blob_before = subprocess.run(
            ["git", "show", ":unrelated-staged.txt"],
            cwd=self.project,
            env=self.env,
            text=True,
            capture_output=True,
            check=True,
        ).stdout
        worktree_bytes_before = {
            name: (self.project / name).read_bytes()
            for name in ("unrelated-staged.txt", "unrelated-modified.txt")
        }

        payload = self.assert_success(self.commit_snapshot())

        committed_paths = subprocess.run(
            ["git", "show", "--pretty=format:", "--name-only", "HEAD"],
            cwd=self.project,
            env=self.env,
            text=True,
            capture_output=True,
            check=True,
        ).stdout.splitlines()
        self.assertEqual(
            sorted(path for path in committed_paths if path),
            [
                ".brainstorming-intent/manifest.json",
                ".brainstorming-intent/records/BIC-0001/slots/a/current.md",
                ".brainstorming-intent/records/BIC-0001/slots/a/history.md",
                ".brainstorming-intent/records/BIC-0002/slots/a/current.md",
                ".brainstorming-intent/records/BIC-0002/slots/a/history.md",
            ],
        )
        self.assertEqual(payload["state"], "committed")
        self.assertTrue(payload["bic_paths_clean"])
        self.assertNotIn("worktree_clean", payload)
        self.assertNotIn("record_id", payload)
        self.assertNotIn("revision", payload)
        self.assertEqual(
            subprocess.run(
                ["git", "status", "--porcelain", "--", ".brainstorming-intent"],
                cwd=self.project,
                text=True,
                capture_output=True,
                check=True,
            ).stdout,
            "",
        )
        manifest = json.loads(
            (self.project / ".brainstorming-intent" / "manifest.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertFalse(manifest["commit_pending"])
        self.assertEqual(
            {
                record_id: metadata["commit_pending"]
                for record_id, metadata in manifest["records"].items()
            },
            {"BIC-0001": False, "BIC-0002": False},
        )
        self.assertEqual(
            subprocess.run(
                ["git", "diff", "--cached", "--binary", "--", "unrelated-staged.txt"],
                cwd=self.project,
                text=True,
                capture_output=True,
                check=True,
            ).stdout,
            staged_diff_before,
        )
        self.assertEqual(
            subprocess.run(
                ["git", "show", ":unrelated-staged.txt"],
                cwd=self.project,
                text=True,
                capture_output=True,
                check=True,
            ).stdout,
            staged_blob_before,
        )
        self.assertEqual(
            {
                name: (self.project / name).read_bytes()
                for name in ("unrelated-staged.txt", "unrelated-modified.txt")
            },
            worktree_bytes_before,
        )

        clean_checkout = self.root / "clean-checkout"
        subprocess.run(
            ["git", "worktree", "add", "--detach", "-q", str(clean_checkout), "HEAD"],
            cwd=self.project,
            check=True,
        )
        clean_validation = subprocess.run(
            [sys.executable, str(CLI), "validate", "--project", str(clean_checkout)],
            cwd=clean_checkout,
            text=True,
            capture_output=True,
            check=True,
        )
        self.assertEqual(
            json.loads(clean_validation.stdout),
            {"ok": True, "records": ["BIC-0001", "BIC-0002"], "state": "valid"},
        )
        self.assertEqual(
            subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=clean_checkout,
                text=True,
                capture_output=True,
                check=True,
            ).stdout,
            "",
        )

    def test_snapshot_stages_only_registered_retirements_after_slot_rotation(self):
        self.configure_git_identity_and_baseline()
        initial = self.assert_success(self.apply())
        self.assert_success(self.commit_snapshot())
        self.assert_success(self.update_record())
        self.assert_success(self.commit_snapshot())
        for kind in ("current", "history"):
            retired = str(Path(initial[f"{kind}_path"]).relative_to(self.project))
            result = subprocess.run(["git", "ls-tree", "HEAD", "--", retired],
                                    cwd=self.project, env=self.env, text=True,
                                    capture_output=True, check=True)
            self.assertEqual(result.stdout, "")
        status = subprocess.run(["git", "status", "--porcelain", "--", ".brainstorming-intent"],
                                cwd=self.project, env=self.env, text=True,
                                capture_output=True, check=True)
        self.assertEqual(status.stdout, "")

    def test_commit_snapshot_rejects_an_invalid_registered_record_before_git_changes(self):
        self.configure_git_identity_and_baseline()
        self.assert_success(self.apply())
        self.assert_success(self.apply())
        invalid_record = (
            self.project
            / ".brainstorming-intent"
            / "records"
            / "BIC-0002"
            / "slots"
            / "a"
            / "current.md"
        )
        invalid_record.write_text(
            invalid_record.read_text(encoding="utf-8").replace(
                "## Explicit prohibitions", "## Missing required section"
            ),
            encoding="utf-8",
        )
        manifest_path = self.project / ".brainstorming-intent" / "manifest.json"
        manifest_before = (manifest_path.read_bytes(), manifest_path.stat().st_mtime_ns)
        index_before = subprocess.run(
            ["git", "ls-files", "--stage"],
            cwd=self.project,
            env=self.env,
            text=True,
            capture_output=True,
            check=True,
        ).stdout
        head_before = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=self.project,
            env=self.env,
            text=True,
            capture_output=True,
            check=True,
        ).stdout

        result = self.commit_snapshot()

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(len(result.stdout.strip().splitlines()), 1)
        self.assertEqual(json.loads(result.stdout)["state"], "invalid_record")
        self.assertEqual(
            (manifest_path.read_bytes(), manifest_path.stat().st_mtime_ns),
            manifest_before,
        )
        self.assertEqual(
            subprocess.run(
                ["git", "ls-files", "--stage"],
                cwd=self.project,
                text=True,
                capture_output=True,
                check=True,
            ).stdout,
            index_before,
        )
        self.assertEqual(
            subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=self.project,
                text=True,
                capture_output=True,
                check=True,
            ).stdout,
            head_before,
        )

    def test_commit_snapshot_pre_commit_failure_restores_exact_pending_set_and_head(self):
        self.configure_git_identity_and_baseline()
        self.assert_success(self.apply())
        self.assert_success(self.apply())
        manifest_path = self.project / ".brainstorming-intent" / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["records"]["BIC-0001"]["commit_pending"] = False
        manifest["records"]["BIC-0002"]["commit_pending"] = True
        manifest["commit_pending"] = True
        manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        pending_before = {
            record_id: metadata["commit_pending"]
            for record_id, metadata in manifest["records"].items()
        }
        head_before = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=self.project,
            env=self.env,
            text=True,
            capture_output=True,
            check=True,
        ).stdout
        hook = self.project / ".git" / "hooks" / "pre-commit"
        hook.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
        os.chmod(hook, 0o755)

        result = self.commit_snapshot()

        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(result.stdout, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["state"], "commit_pending")
        self.assertNotIn("worktree_clean", payload)
        restored = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertTrue(restored["commit_pending"])
        self.assertEqual(
            {
                record_id: metadata["commit_pending"]
                for record_id, metadata in restored["records"].items()
            },
            pending_before,
        )
        self.assertEqual(
            subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=self.project,
                text=True,
                capture_output=True,
                check=True,
            ).stdout,
            head_before,
        )

    def test_commit_snapshot_post_commit_mutation_marks_all_records_pending(self):
        self.configure_git_identity_and_baseline()
        self.assert_success(self.apply())
        self.assert_success(self.apply())
        hook = self.project / ".git" / "hooks" / "post-commit"
        hook.write_text(
            "#!/bin/sh\n"
            "printf '\\npost-commit mutation\\n' >> "
            ".brainstorming-intent/records/BIC-0002/slots/a/current.md\n",
            encoding="utf-8",
        )
        os.chmod(hook, 0o755)

        result = self.commit_snapshot()

        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(result.stdout, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["state"], "commit_pending")
        self.assertFalse(payload["bic_paths_clean"])
        self.assertNotIn("worktree_clean", payload)
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=self.project,
            env=self.env,
            text=True,
            capture_output=True,
            check=True,
        ).stdout.strip()
        self.assertEqual(payload["commit"], head)
        manifest = json.loads(
            (self.project / ".brainstorming-intent" / "manifest.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertTrue(manifest["commit_pending"])
        self.assertEqual(
            {
                record_id: metadata["commit_pending"]
                for record_id, metadata in manifest["records"].items()
            },
            {"BIC-0001": True, "BIC-0002": True},
        )

    def test_record_scoped_commit_is_not_a_valid_subcommand(self):
        result = self.run_cli("commit", "--help")

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertIn("invalid choice", result.stderr)

    def test_bind_requires_an_explicit_record_among_multiple_and_lookup_is_exact(self):
        first = self.assert_success(self.apply())
        second = self.assert_success(self.apply())
        self.assertEqual(first["record_id"], "BIC-0001")
        self.assertEqual(second["record_id"], "BIC-0002")
        plugin_data = self.root / "plugin-data"

        ambiguous = self.run_cli(
            "bind",
            "--plugin-data",
            plugin_data,
            "--session-id",
            "session-1",
            "--project",
            self.project,
            "--expected-revision",
            "1",
        )
        self.assertNotEqual(ambiguous.returncode, 0)
        self.assertTrue(ambiguous.stdout, ambiguous.stderr)
        self.assertEqual(json.loads(ambiguous.stdout)["state"], "record_required")
        self.assertFalse(plugin_data.exists())

        bound = self.assert_success(
            self.run_cli(
                "bind",
                "--plugin-data",
                plugin_data,
                "--session-id",
                "session-1",
                "--project",
                self.project,
                "--record-id",
                "BIC-0002",
                "--expected-revision",
                "1",
            )
        )
        self.assertEqual(bound["state"], "bound")
        binding_file = plugin_data / "session-bindings.json"
        self.assertTrue(binding_file.is_file())
        self.assertFalse(
            str(binding_file.resolve()).startswith(str(self.project.resolve()) + os.sep)
        )

        looked_up = self.assert_success(
            self.run_cli(
                "bind",
                "--plugin-data",
                plugin_data,
                "--session-id",
                "session-1",
                "--lookup",
            )
        )
        self.assertEqual(looked_up["record_id"], "BIC-0002")
        self.assertEqual(looked_up["revision"], 1)
        self.assertEqual(looked_up["project"], str(self.project.resolve()))

    def test_binding_lookup_fails_closed_when_the_session_entry_is_not_an_object(self):
        plugin_data = self.root / "plugin-data"
        plugin_data.mkdir()
        (plugin_data / "session-bindings.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "sessions": {"session-1": "not-an-object"},
                }
            ),
            encoding="utf-8",
        )

        result = self.run_cli(
            "bind",
            "--plugin-data",
            plugin_data,
            "--session-id",
            "session-1",
            "--lookup",
        )

        self.assertEqual(result.returncode, 2, result.stderr)
        output_lines = result.stdout.strip().splitlines()
        self.assertEqual(len(output_lines), 1)
        payload = json.loads(output_lines[0])
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["state"], "invalid_bindings")
        self.assertNotIn("Traceback", result.stderr)

    def test_binding_lookup_fails_closed_for_invalid_required_binding_fields(self):
        plugin_data = self.root / "plugin-data"
        plugin_data.mkdir()
        binding_file = plugin_data / "session-bindings.json"
        binding = {
            "project": str(self.project),
            "record_id": "BIC-0001",
            "revision": 1,
            "current_path": str(self.project / "current.md"),
            "history_path": str(self.project / "history.md"),
        }

        for field, invalid_value in (
            ("project", None),
            ("record_id", None),
            ("record_id", "invalid"),
            ("revision", True),
            ("revision", 0),
            ("current_path", None),
            ("history_path", None),
        ):
            with self.subTest(field=field, invalid_value=invalid_value):
                malformed = dict(binding)
                malformed[field] = invalid_value
                binding_file.write_text(
                    json.dumps(
                        {"schema_version": 1, "sessions": {"session-1": malformed}}
                    ),
                    encoding="utf-8",
                )

                result = self.run_cli(
                    "bind",
                    "--plugin-data",
                    plugin_data,
                    "--session-id",
                    "session-1",
                    "--lookup",
                )

                self.assertEqual(result.returncode, 2, result.stderr)
                output_lines = result.stdout.strip().splitlines()
                self.assertEqual(len(output_lines), 1)
                payload = json.loads(output_lines[0])
                self.assertFalse(payload["ok"])
                self.assertEqual(payload["state"], "invalid_bindings")
                self.assertNotIn("Traceback", result.stderr)

    def assert_binding_lookup_failure(self, plugin_data, expected_state):
        result = self.run_cli(
            "bind",
            "--plugin-data",
            plugin_data,
            "--session-id",
            "session-1",
            "--lookup",
        )

        self.assertEqual(result.returncode, 2, result.stderr)
        output_lines = result.stdout.strip().splitlines()
        self.assertEqual(len(output_lines), 1)
        payload = json.loads(output_lines[0])
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["state"], expected_state)
        self.assertNotIn("Traceback", result.stderr)

    def test_binding_lookup_rejects_invalid_binding_envelopes(self):
        plugin_data = self.root / "plugin-data"
        plugin_data.mkdir()
        binding_file = plugin_data / "session-bindings.json"

        for label, bindings in (
            ("array", []),
            ("null", None),
            ("string", "not-an-object"),
            ("invalid_utf8", b"\xff"),
            ("boolean_schema_version", {"schema_version": True, "sessions": {}}),
            ("float_schema_version", {"schema_version": 1.0, "sessions": {}}),
        ):
            with self.subTest(label=label):
                if isinstance(bindings, bytes):
                    binding_file.write_bytes(bindings)
                else:
                    binding_file.write_text(json.dumps(bindings), encoding="utf-8")

                self.assert_binding_lookup_failure(plugin_data, "invalid_bindings")

    def test_binding_lookup_distinguishes_missing_and_null_session_entries(self):
        plugin_data = self.root / "plugin-data"
        plugin_data.mkdir()
        binding_file = plugin_data / "session-bindings.json"

        for label, sessions, expected_state in (
            ("missing", {}, "unbound_session"),
            ("null", {"session-1": None}, "invalid_bindings"),
        ):
            with self.subTest(label=label):
                binding_file.write_text(
                    json.dumps({"schema_version": 1, "sessions": sessions}),
                    encoding="utf-8",
                )

                self.assert_binding_lookup_failure(plugin_data, expected_state)

    def test_binding_lookup_rejects_unsafe_or_noncanonical_project_paths(self):
        plugin_data = self.root / "plugin-data"
        plugin_data.mkdir()
        binding_file = plugin_data / "session-bindings.json"
        binding = {
            "project": str(self.project),
            "record_id": "BIC-0001",
            "revision": 1,
            "current_path": str(self.project / "current.md"),
            "history_path": str(self.project / "history.md"),
        }

        for label, project in (
            ("nul", "\x00"),
            ("unpaired_surrogate", "\ud800"),
            ("overlong", "/" + "x" * 5000),
            ("relative", "project"),
            ("noncanonical", f"{self.project}/../{self.project.name}"),
        ):
            with self.subTest(label=label):
                malformed = dict(binding)
                malformed["project"] = project
                binding_file.write_text(
                    json.dumps(
                        {"schema_version": 1, "sessions": {"session-1": malformed}}
                    ),
                    encoding="utf-8",
                )

                self.assert_binding_lookup_failure(plugin_data, "invalid_bindings")

    def test_binding_lookup_rejects_project_symlink_cycle(self):
        plugin_data = self.root / "plugin-data"
        plugin_data.mkdir()
        binding_file = plugin_data / "session-bindings.json"
        cycle = self.root / "project-cycle"
        cycle.symlink_to(cycle)
        binding = {
            "project": str(cycle),
            "record_id": "BIC-0001",
            "revision": 1,
            "current_path": str(self.project / "current.md"),
            "history_path": str(self.project / "history.md"),
        }
        binding_file.write_text(
            json.dumps({"schema_version": 1, "sessions": {"session-1": binding}}),
            encoding="utf-8",
        )

        self.assert_binding_lookup_failure(plugin_data, "invalid_bindings")

    def test_binding_lookup_fails_closed_when_record_revision_is_stale(self):
        self.assert_success(self.apply())
        plugin_data = self.root / "plugin-data"
        self.assert_success(
            self.run_cli(
                "bind",
                "--plugin-data",
                plugin_data,
                "--session-id",
                "session-1",
                "--project",
                self.project,
                "--record-id",
                "BIC-0001",
                "--expected-revision",
                "1",
            )
        )
        self.assert_success(self.update_record())
        binding_file = plugin_data / "session-bindings.json"
        before = (binding_file.read_bytes(), binding_file.stat().st_mtime_ns)

        result = self.run_cli(
            "bind",
            "--plugin-data",
            plugin_data,
            "--session-id",
            "session-1",
            "--lookup",
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(result.stdout, result.stderr)
        self.assertEqual(json.loads(result.stdout)["state"], "stale_binding")
        self.assertEqual(
            (binding_file.read_bytes(), binding_file.stat().st_mtime_ns), before
        )

    def test_binding_lookup_fails_closed_when_stored_record_paths_are_changed(self):
        self.assert_success(self.apply())
        plugin_data = self.root / "plugin-data"
        self.assert_success(
            self.run_cli(
                "bind",
                "--plugin-data",
                plugin_data,
                "--session-id",
                "session-1",
                "--project",
                self.project,
                "--record-id",
                "BIC-0001",
                "--expected-revision",
                "1",
            )
        )
        binding_file = plugin_data / "session-bindings.json"
        original = json.loads(binding_file.read_text(encoding="utf-8"))
        canonical = original["sessions"]["session-1"]

        for field, wrong_path in (
            ("current_path", canonical["history_path"]),
            ("history_path", canonical["current_path"]),
        ):
            with self.subTest(field=field):
                mutated = json.loads(json.dumps(original))
                mutated["sessions"]["session-1"][field] = wrong_path
                binding_file.write_text(json.dumps(mutated), encoding="utf-8")

                result = self.run_cli(
                    "bind",
                    "--plugin-data",
                    plugin_data,
                    "--session-id",
                    "session-1",
                    "--lookup",
                )

                self.assertNotEqual(result.returncode, 0)
                self.assertTrue(result.stdout, result.stderr)
                self.assertEqual(json.loads(result.stdout)["state"], "stale_binding")

    def test_binding_data_path_inside_project_is_rejected_without_writes(self):
        self.assert_success(self.apply())
        plugin_data = self.project / "forbidden-plugin-data"

        result = self.run_cli(
            "bind",
            "--plugin-data",
            plugin_data,
            "--session-id",
            "session-1",
            "--project",
            self.project,
            "--record-id",
            "BIC-0001",
            "--expected-revision",
            "1",
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(result.stdout, result.stderr)
        self.assertEqual(json.loads(result.stdout)["state"], "invalid_plugin_data")
        self.assertFalse(plugin_data.exists())

    def test_unsupported_schema_holds_every_mutating_command_read_only(self):
        self.assert_success(self.apply())
        state_directory = self.project / ".brainstorming-intent"
        manifest_path = state_directory / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["schema_version"] = 99
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        before = {
            path.relative_to(state_directory): path.read_bytes()
            for path in state_directory.rglob("*")
            if path.is_file()
        }
        plugin_data = self.root / "plugin-data"

        commands = (
            ("status", "--project", self.project),
            (
                "bind",
                "--plugin-data",
                plugin_data,
                "--session-id",
                "session-1",
                "--project",
                self.project,
                "--record-id",
                "BIC-0001",
                "--expected-revision",
                "1",
            ),
            (
                "commit-snapshot",
                "--project",
                self.project,
                "--message",
                "must not commit",
            ),
        )
        for command in commands:
            with self.subTest(command=command[0]):
                result = self.run_cli(*command)
                self.assertNotEqual(result.returncode, 0)
                self.assertTrue(result.stdout, result.stderr)
                payload = json.loads(result.stdout)
                self.assertEqual(payload["state"], "compatibility_hold")
                self.assertIn("schema_version", payload)
                self.assertEqual(payload["schema_version"], 99)

        after = {
            path.relative_to(state_directory): path.read_bytes()
            for path in state_directory.rglob("*")
            if path.is_file()
        }
        self.assertEqual(after, before)
        self.assertFalse(plugin_data.exists())

    def test_malformed_schema_v1_manifest_returns_one_fail_closed_json_object(self):
        from bic_v2_support import write_v1
        write_v1(self.project, revision=1)
        manifest_path = self.project / ".brainstorming-intent" / "manifest.json"
        valid = json.loads(manifest_path.read_text(encoding="utf-8"))
        cases = [("root_not_object", [])]

        missing_writer_version = json.loads(json.dumps(valid))
        del missing_writer_version["writer_version"]
        cases.append(("missing_writer_version", missing_writer_version))

        unsafe_record_id = json.loads(json.dumps(valid))
        unsafe_record_id["records"]["../BIC-0001"] = unsafe_record_id["records"].pop(
            "BIC-0001"
        )
        cases.append(("unsafe_record_id", unsafe_record_id))

        non_object_metadata = json.loads(json.dumps(valid))
        non_object_metadata["records"]["BIC-0001"] = []
        cases.append(("non_object_metadata", non_object_metadata))

        missing_record_field = json.loads(json.dumps(valid))
        del missing_record_field["records"]["BIC-0001"]["revision"]
        cases.append(("missing_record_field", missing_record_field))

        unsafe_record_path = json.loads(json.dumps(valid))
        unsafe_record_path["records"]["BIC-0001"]["current_path"] = "../escape.md"
        cases.append(("unsafe_record_path", unsafe_record_path))

        reused_next_number = json.loads(json.dumps(valid))
        reused_next_number["next_record_number"] = 1
        cases.append(("reused_next_number", reused_next_number))

        inconsistent_pending = json.loads(json.dumps(valid))
        inconsistent_pending["commit_pending"] = False
        cases.append(("inconsistent_pending", inconsistent_pending))

        boolean_revision = json.loads(json.dumps(valid))
        boolean_revision["records"]["BIC-0001"]["revision"] = True
        cases.append(("boolean_revision", boolean_revision))

        for label, malformed in cases:
            with self.subTest(label=label):
                manifest_path.write_text(json.dumps(malformed), encoding="utf-8")

                result = self.run_cli("status", "--project", self.project)

                self.assertNotEqual(result.returncode, 0)
                self.assertTrue(result.stdout, result.stderr)
                output_lines = result.stdout.strip().splitlines()
                self.assertEqual(len(output_lines), 1)
                payload = json.loads(output_lines[0])
                self.assertEqual(payload["state"], "invalid_manifest")
                self.assertNotIn("Traceback", result.stderr)

    def test_validate_checks_the_persisted_record_without_writing(self):
        self.assert_success(self.apply())
        state_directory = self.project / ".brainstorming-intent"
        before = {
            path.relative_to(state_directory): (path.read_bytes(), path.stat().st_mtime_ns)
            for path in state_directory.rglob("*")
            if path.is_file()
        }

        payload = self.assert_success(
            self.run_cli("validate", "--project", self.project)
        )

        self.assertEqual(payload["state"], "valid")
        self.assertEqual(payload["records"], ["BIC-0001"])
        after = {
            path.relative_to(state_directory): (path.read_bytes(), path.stat().st_mtime_ns)
            for path in state_directory.rglob("*")
            if path.is_file()
        }
        self.assertEqual(after, before)

    def test_record_scoped_validate_returns_the_exact_handoff_pointer(self):
        self.assert_success(self.apply())
        record_directory = (
            self.project.resolve()
            / ".brainstorming-intent"
            / "records"
            / "BIC-0001"
            / "slots"
            / "a"
        )

        payload = self.assert_success(
            self.run_cli(
                "validate",
                "--project",
                self.project,
                "--record-id",
                "BIC-0001",
            )
        )

        self.assertEqual(payload.get("record_id"), "BIC-0001")
        self.assertEqual(payload.get("revision"), 1)
        self.assertEqual(payload.get("current_path"), str(record_directory / "current.md"))
        self.assertEqual(payload.get("history_path"), str(record_directory / "history.md"))


if __name__ == "__main__":
    unittest.main()
