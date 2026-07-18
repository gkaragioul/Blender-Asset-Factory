import json
import tempfile
import unittest
from pathlib import Path

from factory.config import FactoryConfig
from factory.state import refresh_bootstrap, resume_action


class StateTest(unittest.TestCase):
    def make_config(self, root: Path) -> FactoryConfig:
        return FactoryConfig(
            root=root,
            model_root=Path(r"G:\LLMs"),
            tooling_root=root / ".tooling",
            reports_root=root / "reports",
            bridge_url="http://127.0.0.1:9876",
            blender_candidates=(),
        )

    def test_resume_returns_exact_m42_continuation(self):
        with tempfile.TemporaryDirectory(dir="G:\\") as temp:
            root = Path(temp)
            (root / "knowledge").mkdir()
            (root / "knowledge" / "active-project.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "project_id": "ps1_ww2_pump_shotgun_01",
                        "status": "active",
                        "working_directory": "G:/DevWork/GameDev/BlenderAssetFactory/.worktrees/codex-ps1-ww2-pump-shotgun",
                        "next_action": "finish_task_3_atlas_uv_wear",
                        "required_reads": [".superpowers/sdd/task-3-brief.md"],
                        "blocked_by": [],
                    }
                ),
                encoding="utf-8",
            )
            action = resume_action(self.make_config(root))
        self.assertEqual(action["project_id"], "ps1_ww2_pump_shotgun_01")
        self.assertEqual(action["next_action"], "finish_task_3_atlas_uv_wear")

    def test_refresh_bootstrap_is_deterministic(self):
        with tempfile.TemporaryDirectory(dir="G:\\") as temp:
            root = Path(temp)
            knowledge = root / "knowledge"
            knowledge.mkdir()
            (knowledge / "active-project.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "project_id": None,
                        "status": "idle",
                        "working_directory": None,
                        "next_action": None,
                        "required_reads": [],
                        "blocked_by": [],
                    }
                ),
                encoding="utf-8",
            )
            (knowledge / "factory-state.json").write_text(
                '{"schema_version":1,"capabilities":{}}', encoding="utf-8"
            )
            config = self.make_config(root)
            refresh_bootstrap(config)
            first = (knowledge / "START_HERE.md").read_text(encoding="utf-8")
            refresh_bootstrap(config)
            second = (knowledge / "START_HERE.md").read_text(encoding="utf-8")
        self.assertEqual(first, second)
        self.assertIn("Run `factory.ps1 doctor` before mutations", first)


if __name__ == "__main__":
    unittest.main()
