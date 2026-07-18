import json
import tempfile
import unittest
from pathlib import Path

from factory.config import FactoryConfig
from factory.runtime_preview import PreviewError, preview_glb
from tests.glb_fixture import write_triangle_glb


ROOT = Path(__file__).resolve().parents[1]


class RuntimePreviewTest(unittest.TestCase):
    def test_real_threejs_viewer_loads_and_captures_triangle(self):
        temp_root = ROOT / "tmp" / "factory" / "tests"
        temp_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=temp_root) as temp:
            source = write_triangle_glb(Path(temp) / "preview.glb")
            screenshot = Path(temp) / "engine.png"
            report_path = Path(temp) / "preview-report.json"
            report = preview_glb(FactoryConfig.load(), source, screenshot, report_path)
            self.assertTrue(report["ok"])
            self.assertEqual(report["viewer"]["status"], "loaded")
            self.assertEqual(report["viewer"]["mesh_count"], 1)
            self.assertEqual(report["viewer"]["triangle_count"], 1)
            self.assertTrue(report["url"].startswith("http://127.0.0.1:"))
            self.assertEqual(screenshot.read_bytes()[:8], b"\x89PNG\r\n\x1a\n")
            self.assertEqual(json.loads(report_path.read_text())["source_sha256"], report["source_sha256"])

    def test_output_must_stay_on_g(self):
        source = write_triangle_glb(ROOT / "tmp" / "factory" / "tests" / "preview-owned.glb")
        with self.assertRaisesRegex(Exception, "drive G"):
            preview_glb(FactoryConfig.load(), source, Path(r"C:\preview.png"), ROOT / "tmp" / "factory" / "tests" / "preview-owned.json")


if __name__ == "__main__":
    unittest.main()
