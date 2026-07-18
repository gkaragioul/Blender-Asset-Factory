import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from factory.config import FactoryConfig
from factory.io import sha256_file
from factory.release import ReleaseAdapters, ReleaseError, release_package
from tests.glb_fixture import _fixture_png, write_triangle_glb


class ReleaseTest(unittest.TestCase):
    def _fixture(self, root: Path) -> tuple[FactoryConfig, Path, Path, Path]:
        source = write_triangle_glb(root / "projects" / "fixture" / "authoritative.glb")
        view = root / "projects" / "fixture" / "beauty.png"
        view.write_bytes(_fixture_png())
        job = root / "projects" / "fixture" / "release-job.json"
        job.write_text(json.dumps({
            "schema_version": 1,
            "asset_id": "fixture_triangle",
            "version": "1.0.0",
            "authoritative_glb": str(source),
            "source_job_hash": hashlib.sha256(b"fixture job").hexdigest(),
            "pixel_atlas": True,
            "uv_tolerance": 0.000001,
            "required_views": ["beauty", "engine"],
            "views": [{"id": "beauty", "label": "Beauty", "path": str(view)}],
        }))
        config = FactoryConfig(root, root / "models", root / ".tooling", root / "reports", "http://127.0.0.1:9876", ())
        published = root / "assets" / "releases" / "fixture_triangle" / "1.0.0"
        return config, source, job, published

    def _adapters(self, published: Path, calls: list[str], fail_validate: bool = False) -> ReleaseAdapters:
        def validate(_config, source, report):
            calls.append("validate")
            self.assertFalse(published.exists())
            if fail_validate:
                raise ValueError("validator gate failed")
            report.parent.mkdir(parents=True, exist_ok=True)
            report.write_text(json.dumps({"ok": True, "input": str(source), "issues": {"numErrors": 0}}))
            return {"ok": True, "input": str(source), "issues": {"numErrors": 0}}

        def optimize(_config, source, destination, report, **_options):
            calls.append("optimize")
            self.assertFalse(published.exists())
            destination.write_bytes(source.read_bytes())
            report.write_text(json.dumps({"ok": True}))
            return {"ok": True, "derivative": str(destination), "derivative_sha256": sha256_file(destination)}

        def preview(_config, _source, screenshot, report):
            calls.append("preview")
            self.assertFalse(published.exists())
            screenshot.parent.mkdir(parents=True, exist_ok=True)
            screenshot.write_bytes(_fixture_png())
            report.write_text(json.dumps({"ok": True, "viewer": {"status": "loaded"}}))
            return {"ok": True, "viewer": {"status": "loaded"}, "screenshot": str(screenshot)}

        def contact(_config, _manifest, output, report):
            calls.append("contact")
            self.assertFalse(published.exists())
            output.write_bytes(_fixture_png())
            report.write_text(json.dumps({"ok": True}))
            return {"ok": True, "output": str(output), "output_sha256": sha256_file(output)}

        return ReleaseAdapters(validate, optimize, preview, contact)

    def test_all_gates_finish_before_atomic_publication(self):
        with tempfile.TemporaryDirectory(dir="G:\\") as temp:
            root = Path(temp)
            config, source, job, published = self._fixture(root)
            before = sha256_file(source)
            calls = []
            result = release_package(config, job, self._adapters(published, calls), run_id="fixture-success")
            self.assertEqual(calls, ["validate", "optimize", "preview", "preview", "contact"])
            self.assertEqual(sha256_file(source), before)
            self.assertEqual(Path(result["published_path"]), published)
            self.assertTrue((published / "release.complete.json").is_file())
            manifest = json.loads((published / "package-manifest.json").read_text())
            self.assertEqual(manifest["authority"]["authoritative"], "authoritative.glb")
            self.assertEqual(manifest["authority"]["optimized_derivative"], "optimized.glb")
            self.assertTrue(all(len(item["sha256"]) == 64 for item in manifest["files"]))

    def test_failed_gate_reports_but_never_publishes(self):
        with tempfile.TemporaryDirectory(dir="G:\\") as temp:
            root = Path(temp)
            config, _source, job, published = self._fixture(root)
            calls = []
            with self.assertRaisesRegex(ReleaseError, "validator gate failed"):
                release_package(config, job, self._adapters(published, calls, fail_validate=True), run_id="fixture-failure")
            self.assertEqual(calls, ["validate"])
            self.assertFalse(published.exists())
            failure = root / "reports" / "runs" / "fixture-failure" / "release-failure.json"
            self.assertTrue(failure.is_file())
            self.assertFalse(json.loads(failure.read_text())["ok"])


if __name__ == "__main__":
    unittest.main()
