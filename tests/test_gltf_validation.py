import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from factory.config import FactoryConfig
from factory.gltf_validation import GltfValidationError, validate_glb
from tests.glb_fixture import write_triangle_glb


ROOT = Path(__file__).resolve().parents[1]


class GltfValidationTest(unittest.TestCase):
    def test_real_khronos_validator_accepts_embedded_triangle(self):
        source = write_triangle_glb(ROOT / "tmp" / "factory" / "tests" / "validator-triangle.glb")
        report_path = ROOT / "tmp" / "factory" / "tests" / "validator-report.json"
        report = validate_glb(FactoryConfig.load(), source, report_path)
        self.assertTrue(report["ok"])
        self.assertEqual(report["issues"]["numErrors"], 0)
        self.assertEqual(report["inspection"]["triangle_count"], 1)
        self.assertEqual(json.loads(report_path.read_text())["input_sha256"], report["input_sha256"])

    def test_validator_errors_fail_closed_and_are_recorded(self):
        with tempfile.TemporaryDirectory(dir="G:\\") as temp:
            root = Path(temp)
            source = write_triangle_glb(root / "bad.glb")
            config = FactoryConfig(root, root / "models", root / ".tooling", root / "reports", "http://127.0.0.1:9876", ())
            runtime = config.tooling_root / "release-runtime.json"
            runtime.parent.mkdir(parents=True)
            node = root / "node.exe"
            node.write_bytes(b"node")
            node_modules = root / "node_modules"
            node_modules.mkdir()
            adapter = root / "tools" / "release-node" / "validate-gltf.mjs"
            adapter.parent.mkdir(parents=True)
            adapter.write_text("// fixture")
            runtime.write_text(json.dumps({"node": str(node), "node_modules": str(node_modules)}))
            fake = subprocess.CompletedProcess([], 0, json.dumps({"issues": {"numErrors": 1, "numWarnings": 0, "messages": [{"code": "BROKEN"}]}}), "")
            with patch("factory.gltf_validation.subprocess.run", return_value=fake):
                with self.assertRaisesRegex(GltfValidationError, "1 error"):
                    validate_glb(config, source, root / "failed.json")
            self.assertEqual(json.loads((root / "failed.json").read_text())["issues"]["numErrors"], 1)


if __name__ == "__main__":
    unittest.main()
