import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from factory.config import FactoryConfig
from factory.runtime_preview import PreviewError, preview_glb
from factory.runtime_preview import _browser_path
from tests.glb_fixture import write_triangle_glb


ROOT = Path(__file__).resolve().parents[1]


class RuntimePreviewTest(unittest.TestCase):
    def test_browser_path_discovers_linux_chrome_from_path(self):
        with patch("factory.runtime_preview.shutil.which", return_value="/usr/bin/google-chrome"), patch("factory.runtime_preview.Path.is_file", return_value=True):
            self.assertEqual(_browser_path(), Path("/usr/bin/google-chrome"))

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

    def test_output_must_stay_under_owned_roots(self):
        source = write_triangle_glb(ROOT / "tmp" / "factory" / "tests" / "preview-owned.glb")
        with self.assertRaisesRegex(Exception, "factory root or model root"):
            preview_glb(FactoryConfig.load(), source, Path("/tmp/factory-preview-outside.png"), ROOT / "tmp" / "factory" / "tests" / "preview-owned.json")


if __name__ == "__main__":
    unittest.main()
