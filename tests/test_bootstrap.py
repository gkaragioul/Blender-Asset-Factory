import json
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class BootstrapContractTest(unittest.TestCase):
    def test_dry_run_keeps_every_owned_path_on_g(self):
        completed = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(ROOT / "bootstrap" / "setup.ps1"),
                "-DryRun",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        result = json.loads(completed.stdout)
        self.assertEqual(result["schema_version"], 1)
        self.assertEqual(Path(result["root"]), ROOT)
        self.assertEqual(result["model_root"], r"G:\LLMs")
        self.assertEqual(result["uv_version"], "0.11.29")
        self.assertEqual(result["python_version"], "3.12.11")
        for action in result["actions"]:
            self.assertEqual(Path(action["target"]).drive.upper(), "G:")

    def test_python_install_disables_external_executable_shims(self):
        setup = (ROOT / "bootstrap" / "setup.ps1").read_text(encoding="utf-8")
        self.assertIn("--no-bin", setup)


if __name__ == "__main__":
    unittest.main()
