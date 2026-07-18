import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from factory.config import FactoryConfig
from factory.contact_sheet import ContactSheetError, build_contact_sheet
from tests.glb_fixture import _fixture_png


ROOT = Path(__file__).resolve().parents[1]


class ContactSheetTest(unittest.TestCase):
    def test_missing_required_semantic_view_fails(self):
        temp_root = ROOT / "tmp" / "factory" / "tests"
        temp_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=temp_root) as temp:
            root = Path(temp)
            image = root / "beauty.png"
            image.write_bytes(_fixture_png())
            manifest = root / "views.json"
            manifest.write_text(json.dumps({
                "schema_version": 1,
                "title": "Fixture",
                "required_views": ["beauty", "engine"],
                "views": [{"id": "beauty", "label": "Beauty", "path": str(image)}],
            }))
            with self.assertRaisesRegex(ContactSheetError, "engine"):
                build_contact_sheet(FactoryConfig.load(), manifest, root / "sheet.png", root / "sheet.json")

    def test_real_browser_builds_deterministic_semantic_sheet(self):
        temp_root = ROOT / "tmp" / "factory" / "tests"
        temp_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=temp_root) as temp:
            root = Path(temp)
            views = []
            for view_id, label in (("beauty", "Beauty"), ("wireframe", "Wireframe"), ("engine", "Three.js Engine")):
                image = root / f"{view_id}.png"
                image.write_bytes(_fixture_png())
                views.append({"id": view_id, "label": label, "path": str(image)})
            manifest = root / "views.json"
            manifest.write_text(json.dumps({"schema_version": 1, "title": "Fixture Contact Sheet", "required_views": ["beauty", "wireframe", "engine"], "views": views}))
            output = root / "contact-sheet.png"
            report_path = root / "contact-sheet.json"
            report = build_contact_sheet(FactoryConfig.load(), manifest, output, report_path)
            self.assertTrue(report["ok"])
            self.assertEqual(report["view_ids"], ["beauty", "wireframe", "engine"])
            self.assertEqual(output.read_bytes()[:8], b"\x89PNG\r\n\x1a\n")
            self.assertEqual(json.loads(report_path.read_text())["output_sha256"], report["output_sha256"])

    def test_browser_timeout_records_failure_report(self):
        temp_root = ROOT / "tmp" / "factory" / "tests"
        temp_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=temp_root) as temp:
            root = Path(temp)
            image = root / "engine.png"
            image.write_bytes(_fixture_png())
            manifest = root / "views.json"
            manifest.write_text(json.dumps({"schema_version": 1, "title": "Timeout", "required_views": ["engine"], "views": [{"id": "engine", "label": "Engine", "path": str(image)}]}))
            report_path = root / "timeout-report.json"
            with patch("factory.contact_sheet.subprocess.run", side_effect=subprocess.TimeoutExpired(["node"], 300)):
                with self.assertRaisesRegex(ContactSheetError, "timed out"):
                    build_contact_sheet(FactoryConfig.load(), manifest, root / "sheet.png", report_path)
            self.assertFalse(json.loads(report_path.read_text())["ok"])


if __name__ == "__main__":
    unittest.main()
