import json
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ROOT = REPOSITORY_ROOT / "plugins" / "brainstorming-intent-continuity"
QUALIFIED_INVOCATION = (
    "$brainstorming-intent-continuity:brainstorming-intent-continuity"
)
BARE_INVOCATION = "$brainstorming-intent-continuity"


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

    def test_v014_release_metadata_and_documentation_links(self):
        manifest = json.loads(
            (PLUGIN_ROOT / ".codex-plugin" / "plugin.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(manifest["version"], "0.1.4")
        self.assertIn(
            QUALIFIED_INVOCATION,
            "\n".join(manifest["interface"]["defaultPrompt"]),
        )

        changelog = (REPOSITORY_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        self.assertIn("## [0.1.4] - 2026-08-26", changelog)
        changelog_lower = changelog.lower()
        self.assertIn("fail closed", changelog_lower)
        self.assertIn("semantic delta", changelog_lower)

        for relative_path in ("README.md", "README.zh-CN.md"):
            with self.subTest(path=relative_path):
                text = (REPOSITORY_ROOT / relative_path).read_text(encoding="utf-8")
                self.assertIn("0.1.4", text)
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

    def test_partial_activation_stops_and_recovery_is_forward_only(self):
        skill = (
            PLUGIN_ROOT
            / "skills"
            / "brainstorming-intent-continuity"
            / "SKILL.md"
        ).read_text(encoding="utf-8")
        normalized_skill = " ".join(skill.split())
        self.assertIn("full runtime `<skill>` payload", normalized_skill)
        self.assertIn("End the turn immediately", normalized_skill)
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


if __name__ == "__main__":
    unittest.main()
