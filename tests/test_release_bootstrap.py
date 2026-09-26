import json
import os
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _inside_root(path: str) -> bool:
    child = os.path.normcase(os.path.abspath(path))
    parent = os.path.normcase(os.path.abspath(ROOT))
    return child.startswith(parent.rstrip("\\/") + os.sep)


class ReleaseBootstrapTest(unittest.TestCase):
    def test_release_setup_dry_run_is_pinned_and_stays_under_root(self):
        completed = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(ROOT / "bootstrap" / "setup-release.ps1"),
                "-DryRun",
            ],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        result = json.loads(completed.stdout)
        self.assertEqual(result["versions"], {
            "gltf_validator": "2.0.0-dev.3.10",
            "gltfpack": "1.2",
            "node": "24.17.0",
            "playwright_core": "1.61.1",
            "three": "0.185.1",
        })
        self.assertTrue(result["targets"])
        self.assertTrue(all(_inside_root(path) for path in result["targets"]))

    def test_manifest_pins_download_checksums_and_licenses(self):
        manifest = json.loads((ROOT / "tools" / "manifests" / "release-toolchain.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["node"]["sha256"], "f2aa33b35b75aca5f3f7b85675a6f6423201053e9381911e64961f3bda2528ab")
        self.assertEqual(manifest["gltfpack"]["sha256"], "52e0c061d8b42f1c6bd8fe1cbc1e26a9da579ad5a4f5dd30a8ee0d599062f6c4")
        self.assertEqual(manifest["gltfpack"]["license"], "MIT")
        self.assertEqual(manifest["gltf_validator"]["license"], "Apache-2.0")

    def test_partial_node_extraction_requires_npm_before_it_is_complete(self):
        installer = (ROOT / "bootstrap" / "setup-release.ps1").read_text(encoding="utf-8")
        extraction_guard = installer.split("$nodeArchive =", 1)[0].rsplit("if (", 1)[-1]
        self.assertIn("$nodeExe", extraction_guard)
        self.assertIn("$npmCmd", extraction_guard)


if __name__ == "__main__":
    unittest.main()
