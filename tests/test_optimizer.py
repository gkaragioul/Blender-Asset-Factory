import json
import tempfile
import unittest
from pathlib import Path

from factory.config import FactoryConfig
from factory.io import sha256_file
from factory.optimizer import OptimizationError, optimize_glb
from tests.glb_fixture import write_triangle_glb


ROOT = Path(__file__).resolve().parents[1]


class OptimizerTest(unittest.TestCase):
    def test_real_gltfpack_creates_valid_uv_stable_derivative(self):
        temp_root = ROOT / "tmp" / "factory" / "tests"
        temp_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=temp_root) as temp:
            source = write_triangle_glb(Path(temp) / "optimizer-source.glb")
            destination = Path(temp) / "optimizer-derivative.glb"
            report_path = Path(temp) / "optimizer-report.json"
            before = sha256_file(source)
            report = optimize_glb(FactoryConfig.load(), source, destination, report_path, pixel_atlas=True)
            self.assertEqual(sha256_file(source), before)
            self.assertNotEqual(source.resolve(), destination.resolve())
            self.assertTrue(report["ok"])
            self.assertIn("-vtf", report["command"])
            self.assertEqual(report["source_validation"]["issues"]["numErrors"], 0)
            self.assertEqual(report["derivative_validation"]["issues"]["numErrors"], 0)
            self.assertLessEqual(report["uv_max_drift"], report["uv_tolerance"])
            self.assertEqual(json.loads(report_path.read_text())["derivative_sha256"], sha256_file(destination))

    def test_refuses_to_replace_authoritative_source(self):
        with tempfile.TemporaryDirectory(dir="G:\\") as temp:
            source = write_triangle_glb(Path(temp) / "source.glb")
            base = FactoryConfig.load()
            config = FactoryConfig(Path(temp), base.model_root, base.tooling_root, Path(temp) / "reports", base.bridge_url, ())
            with self.assertRaisesRegex(OptimizationError, "must differ"):
                optimize_glb(config, source, source, Path(temp) / "report.json")


if __name__ == "__main__":
    unittest.main()
