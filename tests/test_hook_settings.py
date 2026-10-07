"""The hook entrypoint must work when the project-dir environment variable is wrong."""

import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.agent_harness.jev_gate import resolve_repo


ROOT = Path(__file__).resolve().parents[1]


class HookSettingsTest(unittest.TestCase):
    def test_invalid_project_dir_falls_back_to_event_repo(self):
        with patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": str(ROOT.anchor)}):
            self.assertEqual(resolve_repo(cwd=str(ROOT)), ROOT)

    def test_hook_commands_use_repo_relative_entrypoint(self):
        expected = {
            "UserPromptSubmit": ["user-prompt"],
            "SessionStart": ["session-compact"],
            "PreToolUse": ["pre-bash", "pre-review"],
        }
        self.assertTrue((ROOT / "scripts" / "agent_harness" / "hook.py").is_file())
        for name in ("settings.json", "settings.local.json.example"):
            with self.subTest(settings=name):
                settings = json.loads((ROOT / ".claude" / name).read_text(encoding="utf-8"))
                for event, args in expected.items():
                    commands = [hook["command"] for entry in settings["hooks"][event] for hook in entry["hooks"]]
                    self.assertEqual(commands, [f'python "scripts/agent_harness/hook.py" {arg}' for arg in args])


if __name__ == "__main__":
    unittest.main()
