import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from bic_v2_support import load_bic, write_v1


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ROOT = REPOSITORY_ROOT / "plugins" / "brainstorming-intent-continuity"
QUALIFIED_INVOCATION = (
    "$brainstorming-intent-continuity:brainstorming-intent-continuity"
)
BARE_INVOCATION = "$brainstorming-intent-continuity"
SKILL_ROOT = PLUGIN_ROOT / "skills" / "brainstorming-intent-continuity"


def documented_commands(path):
    """Read copyable CLI examples, excluding shell setup and syntax synopses."""
    text = path.read_text(encoding="utf-8").replace("\\\n", " ")
    commands = []
    names = {"read", "save-version", "bind", "migrate", "validate"}
    for block in re.findall(r"```(?:bash|text)\n(.*?)```", text, re.S):
        for line in block.splitlines():
            words = shlex.split(line, comments=True)
            if len(words) >= 3 and words[:2] == ["python3", "${BIC_SKILL_DIR}/scripts/bic.py"]:
                commands.append(words[2:])
            elif words and words[0] in names:
                commands.append(words)
    return commands


class PublicCommandExamplesTestCase(unittest.TestCase):
    def test_skill_and_bilingual_examples_match_the_real_parser(self):
        parser = load_bic().build_parser()
        for path in (SKILL_ROOT / "SKILL.md", REPOSITORY_ROOT / "README.md",
                     REPOSITORY_ROOT / "README.zh-CN.md"):
            commands = documented_commands(path)
            with self.subTest(path=path.name):
                self.assertTrue({"read", "save-version", "bind", "migrate", "validate"}
                                <= {command[0] for command in commands},
                                "Missing copyable current/saved input and migration commands")
            for command in commands:
                with self.subTest(path=path.name, command=command):
                    args = parser.parse_args(["3" if word == "N" else word for word in command])
                    if args.command == "bind":
                        self.assertIsNotNone(args.project)
                        self.assertIsNone(args.plugin_data)
                        if not args.lookup:
                            self.assertIsNotNone(args.record_id)
                            self.assertIsNotNone(args.expected_revision)

    def test_bilingual_migration_and_saved_input_examples_preserve_originals(self):
        # A stale flag, wrong revision, or mutable pointer in a published example
        # must fail against actual project-local storage, not a prose assertion.
        base = REPOSITORY_ROOT / ".tmp"
        base.mkdir(exist_ok=True)
        for name in ("README.md", "README.zh-CN.md"):
            with self.subTest(document=name), tempfile.TemporaryDirectory(dir=base) as folder:
                project = Path(folder)
                scratch = project / ".tmp"
                scratch.mkdir()
                write_v1(project)
                original = {kind: (project / ".brainstorming-intent" / "records" /
                            "BIC-0001" / f"{kind}.md").read_bytes()
                            for kind in ("current", "history")}
                env = dict(os.environ, TMPDIR=str(scratch), PYTHONDONTWRITEBYTECODE="1")
                examples = documented_commands(REPOSITORY_ROOT / name)
                self.assertTrue(examples, "No executable migration/binding examples")
                examples.sort(key=lambda command: command[0] != "migrate")
                results = []
                for command in examples:
                    substitutions = {"$BIC_PROJECT": str(project), "PROJECT": str(project),
                                     "ID": "BIC-0001", "N": "3"}
                    argv = [substitutions.get(word, word) for word in command]
                    result = subprocess.run([sys.executable, str(SKILL_ROOT / "scripts/bic.py"), *argv],
                                            capture_output=True, text=True, env=env)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    results.append((argv, json.loads(result.stdout)))
                reads = [value for argv, value in results if argv[0] == "read"]
                validations = [value for argv, value in results if argv[0] == "validate"]
                self.assertEqual(len(validations), 1)
                self.assertEqual(validations[0]["validation_scope"], "current")
                self.assertEqual(validations[0]["record_id"], "BIC-0001")
                self.assertEqual(validations[0]["revision"], 3)
                self.assertEqual({value["source_kind"] for value in reads}, {"current", "saved"})
                for value in reads:
                    self.assertEqual(value["revision"], 3)
                    self.assertEqual(value["round"]["state"], "unknown")
                    for kind in ("current", "history"):
                        self.assertEqual(value[kind]["text"].encode(), original[kind])
                binding = json.loads((project / ".brainstorming-intent/session-bindings.json").read_text())
                entry = binding["sessions"]["SESSION"]
                self.assertEqual(entry["revision"], 3)
                for kind in ("current", "history"):
                    saved = Path(entry[f"{kind}_path"])
                    self.assertTrue(saved.is_relative_to(project / ".brainstorming-intent/versions"))
                    self.assertEqual(saved.read_bytes(), original[kind])


class PublicPackageContractTestCase(unittest.TestCase):
    def test_user_facing_surfaces_use_the_plugin_qualified_skill_name(self):
        relative_paths = (
            "README.md",
            "README.zh-CN.md",
            "plugins/brainstorming-intent-continuity/skills/"
            "brainstorming-intent-continuity/SKILL.md",
            "plugins/brainstorming-intent-continuity/skills/"
            "brainstorming-intent-continuity/agents/openai.yaml",
        )

        for relative_path in relative_paths:
            with self.subTest(path=relative_path):
                text = (REPOSITORY_ROOT / relative_path).read_text(encoding="utf-8")
                self.assertIn(QUALIFIED_INVOCATION, text)
                self.assertNotIn(BARE_INVOCATION, text.splitlines())

    def test_existing_installation_upgrade_path_is_bilingual_and_complete(self):
        commands = (
            "codex plugin marketplace upgrade gentlejinqi-bic",
            "codex plugin remove brainstorming-intent-continuity@gentlejinqi-bic",
            "codex plugin add brainstorming-intent-continuity@gentlejinqi-bic",
            "codex plugin list",
        )
        english = (REPOSITORY_ROOT / "README.md").read_text(encoding="utf-8")
        chinese = (REPOSITORY_ROOT / "README.zh-CN.md").read_text(encoding="utf-8")

        for command in commands:
            with self.subTest(command=command):
                self.assertIn(command, english)
                self.assertIn(command, chinese)

        normalized_english = " ".join(english.split())
        self.assertIn("Start a new Codex task after upgrading", normalized_english)
        self.assertIn(
            "does not delete project-owned `.brainstorming-intent/` records",
            normalized_english,
        )

        normalized_chinese = " ".join(chinese.split())
        self.assertIn("更新后请新建一个 Codex 任务", normalized_chinese)
        self.assertIn(
            "不会删除项目自有的 `.brainstorming-intent/` 记录",
            normalized_chinese,
        )

    def test_v020_release_metadata_and_documentation_links(self):
        manifest = json.loads(
            (PLUGIN_ROOT / ".codex-plugin" / "plugin.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(manifest["version"], "0.2.0")
        self.assertIn(
            QUALIFIED_INVOCATION,
            "\n".join(manifest["interface"]["defaultPrompt"]),
        )

        changelog = (REPOSITORY_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        self.assertIn("## [0.2.0] - 2026-09-06", changelog)
        self.assertIn("## [0.1.4] - 2026-08-26", changelog)
        changelog_lower = changelog.lower()
        self.assertIn("fail closed", changelog_lower)
        self.assertIn("semantic delta", changelog_lower)

        for relative_path in ("README.md", "README.zh-CN.md"):
            with self.subTest(path=relative_path):
                text = (REPOSITORY_ROOT / relative_path).read_text(encoding="utf-8")
                self.assertIn("0.2.0", text)
                self.assertIn("[CHANGELOG.md](CHANGELOG.md)", text)
                self.assertIn(
                    "https://github.com/GentleJinqi/Brainstorming-Intent-Continuity/releases",
                    text,
                )

    def test_workflow_diagrams_return_to_exploration_after_an_update(self):
        for relative_path in ("README.md", "README.zh-CN.md"):
            with self.subTest(path=relative_path):
                text = (REPOSITORY_ROOT / relative_path).read_text(encoding="utf-8")
                self.assertIn('L --> E0', text)
                self.assertNotIn('L --> D', text)

    def test_partial_activation_requires_evidence_and_recovery_is_forward_only(self):
        skill = (
            PLUGIN_ROOT
            / "skills"
            / "brainstorming-intent-continuity"
            / "SKILL.md"
        ).read_text(encoding="utf-8")
        normalized_skill = " ".join(skill.split())
        self.assertIn("full runtime `<skill>` payload", normalized_skill)
        self.assertIn("forward-only", normalized_skill)
        self.assertIn("controlled bootstrap", normalized_skill)

        for relative_path in ("README.md", "README.zh-CN.md"):
            with self.subTest(path=relative_path):
                text = (REPOSITORY_ROOT / relative_path).read_text(encoding="utf-8")
                normalized_text = " ".join(text.split())
                self.assertIn("forward-only", normalized_text)
                self.assertIn("controlled bootstrap", normalized_text)

    def test_controlled_bootstrap_reconciles_native_authority_before_apply(self):
        skill = (
            PLUGIN_ROOT
            / "skills"
            / "brainstorming-intent-continuity"
            / "SKILL.md"
        ).read_text(encoding="utf-8")
        normalized_skill = " ".join(skill.split())
        self.assertIn(
            "Before presenting a controlled bootstrap reconstruction, inspect any applicable native project authority and reconcile the reconstruction to it.",
            normalized_skill,
        )
        self.assertIn(
            "Native authority controls project state, source routing, lifecycle, evidence, permissions and write eligibility, and handoff ownership over recovered Task history and BIC defaults; BIC never overrides it.",
            normalized_skill,
        )
        self.assertIn(
            "Do not apply where that authority forbids the record or write; obtain user confirmation only after reconciliation.",
            normalized_skill,
        )

        english_readme = (REPOSITORY_ROOT / "README.md").read_text(encoding="utf-8")
        normalized_english = " ".join(english_readme.split())
        self.assertIn(
            "inspect any applicable native project authority and reconcile the reconstruction to it",
            normalized_english,
        )
        self.assertIn("BIC never overrides it", normalized_english)
        self.assertIn(
            "Do not apply where that authority forbids the record or write",
            normalized_english,
        )

        chinese_readme = (REPOSITORY_ROOT / "README.zh-CN.md").read_text(
            encoding="utf-8"
        )
        normalized_chinese = " ".join(chinese_readme.split())
        self.assertIn("先检查适用的原生项目权威", normalized_chinese)
        self.assertIn("将重建内容与其协调一致", normalized_chinese)
        self.assertIn("BIC 不得覆盖该权威", normalized_chinese)
        self.assertIn("若该权威禁止记录或写入，则不得 apply", normalized_chinese)

    def test_skill_commands_invoke_bic_with_python3(self):
        skill = (
            PLUGIN_ROOT
            / "skills"
            / "brainstorming-intent-continuity"
            / "SKILL.md"
        ).read_text(encoding="utf-8")
        script_path = '"${BIC_SKILL_DIR}/scripts/bic.py"'
        command_lines = [line for line in skill.splitlines() if script_path in line]

        self.assertTrue(command_lines)
        for line in command_lines:
            with self.subTest(line=line):
                self.assertIn(f"python3 {script_path}", line)


if __name__ == "__main__":
    unittest.main()
