import json
import os
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ContinuityTest(unittest.TestCase):
    def test_repository_memory_recovers_active_task(self):
        completed = subprocess.run(
            [sys.executable, "-m", "factory", "resume", "--json"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        result = json.loads(completed.stdout)
        self.assertTrue(result["ok"])
        self.assertEqual(
            result["data"]["project_id"], "ps1_ww2_pump_shotgun_01"
        )
        self.assertEqual(
            result["data"]["next_action"], "finish_task_3_atlas_uv_wear"
        )
        start = (ROOT / "knowledge" / "START_HERE.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("ps1_ww2_pump_shotgun_01", start)
        self.assertIn("finish_task_3_atlas_uv_wear", start)

    @unittest.skipIf(
        os.environ.get("BAF_VERIFY_CHILD") == "1",
        "avoid recursive verify child",
    )
    def test_verify_command_records_success_on_g(self):
        completed = subprocess.run(
            [sys.executable, "-m", "factory", "verify", "--json"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        result = json.loads(completed.stdout)
        self.assertTrue(result["ok"])
        self.assertEqual(
            Path(result["data"]["report_path"]).drive.upper(), "G:"
        )


if __name__ == "__main__":
    unittest.main()
