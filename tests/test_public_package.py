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

    def test_patch_release_metadata_records_the_invocation_fix(self):
        manifest = json.loads(
            (PLUGIN_ROOT / ".codex-plugin" / "plugin.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(manifest["version"], "0.1.2")
        self.assertIn(
            QUALIFIED_INVOCATION,
            "\n".join(manifest["interface"]["defaultPrompt"]),
        )

        changelog = (REPOSITORY_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        self.assertIn("## [0.1.2] - 2026-08-26", changelog)
        self.assertIn("plugin-qualified Skill invocation", changelog)


if __name__ == "__main__":
    unittest.main()
