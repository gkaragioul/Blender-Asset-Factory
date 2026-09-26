import json
import tempfile
import unittest
from pathlib import Path

from factory.config import FactoryConfig
from factory.review_sheet import KNOWN_VIEWS, ReviewError, review_glb
from tests.glb_fixture import write_triangle_glb


ROOT = Path(__file__).resolve().parents[1]


def _runtime_available(config: FactoryConfig) -> bool:
    return (config.tooling_root / "release-runtime.json").is_file()


class ReviewSheetArgumentTest(unittest.TestCase):
    def test_unknown_view_is_rejected_before_any_browser_work(self):
        source = write_triangle_glb(ROOT / "tmp" / "factory" / "tests" / "review-args.glb")
        with self.assertRaisesRegex(ReviewError, "unknown view"):
            review_glb(FactoryConfig.load(), source, ROOT / "tmp" / "factory" / "tests" / "r.png", ROOT / "tmp" / "factory" / "tests" / "r.json", views=("front", "sideways"))

    def test_outputs_must_stay_under_owned_roots(self):
        source = write_triangle_glb(ROOT / "tmp" / "factory" / "tests" / "review-owned.glb")
        with self.assertRaisesRegex(Exception, "factory root or model root"):
            review_glb(FactoryConfig.load(), source, Path("/tmp/factory-review-outside.png"), ROOT / "tmp" / "factory" / "tests" / "r.json")

    def test_standard_views_cover_every_side(self):
        for view in ("q-front", "front", "left", "right", "rear", "q-rear", "top", "bottom", "ground"):
            self.assertIn(view, KNOWN_VIEWS)


class ReviewCliTest(unittest.TestCase):
    def test_cli_rejects_unknown_view_with_error_envelope(self):
        from factory.cli import run

        source = write_triangle_glb(ROOT / "tmp" / "factory" / "tests" / "review-cli.glb")
        code, result, _ = run(["review", "--input", str(source), "--output", "tmp/factory/tests/cli.png", "--views", "front,sideways", "--json"])
        self.assertEqual(code, 1)
        self.assertFalse(result["ok"])
        self.assertIn("unknown view", result["errors"][0]["message"])


class ReviewSheetBrowserTest(unittest.TestCase):
    def setUp(self):
        self.config = FactoryConfig.load()
        if not _runtime_available(self.config):
            raise unittest.SkipTest("release runtime (Node, Three.js, Playwright) is not installed")

    def test_real_browser_renders_views_and_measures_placement(self):
        temp_root = ROOT / "tmp" / "factory" / "tests"
        temp_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=temp_root) as temp:
            # The fixture triangle spans y -1..1, so it is deliberately NOT grounded.
            source = write_triangle_glb(Path(temp) / "review.glb")
            output = Path(temp) / "review.png"
            report_path = Path(temp) / "review.json"
            report = review_glb(
                self.config, source, output, report_path,
                views=("q-front", "front", "ground"), scale_figure=True, width=900, height=400,
                expectations={"triangles": [1, 10], "max_draw_calls": 1},
            )
            self.assertTrue(report["rendered"])
            self.assertEqual(output.read_bytes()[:8], b"\x89PNG\r\n\x1a\n")
            measured = report["measured"]
            self.assertEqual(measured["triangle_count"], 1)
            self.assertEqual(measured["draw_calls"], 1)
            self.assertAlmostEqual(measured["bounds"]["min"][1], -1.0, places=4)
            self.assertEqual(report["views"], ["q-front", "front", "ground"])
            self.assertFalse(report["checks"]["passed"])
            self.assertEqual(report["checks"]["failures"], ["not_grounded"])
            self.assertEqual(json.loads(report_path.read_text())["source_sha256"], report["source_sha256"])


if __name__ == "__main__":
    unittest.main()
