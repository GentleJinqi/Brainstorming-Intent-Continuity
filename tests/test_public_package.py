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

    def test_patch_release_metadata_records_fail_closed_activation(self):
        manifest = json.loads(
            (PLUGIN_ROOT / ".codex-plugin" / "plugin.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(manifest["version"], "0.1.3")
        self.assertIn(
            QUALIFIED_INVOCATION,
            "\n".join(manifest["interface"]["defaultPrompt"]),
        )

        changelog = (REPOSITORY_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        self.assertIn("## [0.1.3] - 2026-08-26", changelog)
        changelog_lower = changelog.lower()
        self.assertIn("fail closed", changelog_lower)
        self.assertIn("semantic delta", changelog_lower)

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


if __name__ == "__main__":
    unittest.main()
