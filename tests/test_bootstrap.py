import json
import os
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _inside(path: Path, base: Path) -> bool:
    child = os.path.normcase(os.path.abspath(path))
    parent = os.path.normcase(os.path.abspath(base))
    return child == parent or child.startswith(parent.rstrip("\\/") + os.sep)


def _dry_run(*extra: str) -> dict:
    completed = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(ROOT / "bootstrap" / "setup.ps1"),
            "-DryRun",
            *extra,
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)


class BootstrapContractTest(unittest.TestCase):
    def test_dry_run_keeps_every_owned_path_under_root_or_model_root(self):
        result = _dry_run()
        config = json.loads((ROOT / "factory" / "config.json").read_text(encoding="utf-8"))
        model_root = ROOT / config["model_root"]
        self.assertEqual(result["schema_version"], 1)
        self.assertEqual(Path(result["root"]), ROOT)
        self.assertTrue(_inside(Path(result["model_root"]), model_root))
        self.assertTrue(_inside(model_root, Path(result["model_root"])))
        self.assertEqual(result["uv_version"], "0.11.29")
        self.assertEqual(result["python_version"], "3.12.11")
        for action in result["actions"]:
            target = Path(action["target"])
            self.assertTrue(
                _inside(target, ROOT) or _inside(target, model_root),
                f"{action['name']} target outside the factory and model roots: {target}",
            )

    def test_model_root_parameter_overrides_config(self):
        override = ROOT / "tmp" / "factory" / "tests" / "model-root-override"
        result = _dry_run("-ModelRoot", str(override))
        self.assertTrue(_inside(Path(result["model_root"]), override))
        self.assertTrue(_inside(override, Path(result["model_root"])))
        model_action = next(a for a in result["actions"] if a["name"] == "create_model_root")
        self.assertTrue(_inside(Path(model_action["target"]), override))

    def test_python_install_disables_external_executable_shims(self):
        setup = (ROOT / "bootstrap" / "setup.ps1").read_text(encoding="utf-8")
        self.assertIn("--no-bin", setup)


if __name__ == "__main__":
    unittest.main()
