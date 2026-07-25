import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from factory.blender import BlenderError, discover_blender
from factory.config import FactoryConfig
from factory.png import encode_rgba
from factory.retro import RetroError, canonical_glb_bytes, retro_pass
from factory.style_contract import StyleContract
from tests.fixtures import FixtureUnavailable, trenchgun_fbx

CONTRACT = {
    "schema_version": 1,
    "palette": "palette.png",
    "texture_size": 256,
    "filtering": "nearest",
    "polycount_bands": {"small": 400, "medium": 1000, "large": 2500},
    "grid_unit": 0.5,
    "up_axis": "Y",
    "drop_maps": ["normal", "roughness", "metallic"],
    "vertex_light_bake": True,
}


class RetroPassTest(unittest.TestCase):
    def setUp(self):
        self.config = FactoryConfig.load()
        if discover_blender(self.config) is None:
            self.skipTest("Blender is not available on this host")
        try:
            self.source = trenchgun_fbx()
        except FixtureUnavailable as error:
            self.skipTest(str(error))
        self.work = self.config.root / "tmp" / "factory" / "tests" / "retro"
        self.work.mkdir(parents=True, exist_ok=True)

    def _contract(self, temp: Path) -> StyleContract:
        rgba = bytearray()
        for colour in ((20, 18, 16), (104, 82, 56), (132, 138, 130), (188, 192, 186)):
            rgba.extend((*colour, 255))
        (temp / "palette.png").write_bytes(encode_rgba(4, 1, bytes(rgba)))
        path = temp / "contract.json"
        path.write_text(json.dumps(CONTRACT), encoding="utf-8")
        return StyleContract.load(self.config, path)

    def test_produces_byte_identical_output_for_identical_inputs(self):
        with tempfile.TemporaryDirectory(dir=self.work) as temp:
            temp_path = Path(temp)
            contract = self._contract(temp_path)
            first = temp_path / "first.glb"
            second = temp_path / "second.glb"
            retro_pass(
                self.config, self.source, contract, "large", first,
                temp_path / "first.json",
            )
            retro_pass(
                self.config, self.source, contract, "large", second,
                temp_path / "second.json",
            )
            self.assertEqual(canonical_glb_bytes(first), canonical_glb_bytes(second))

    def test_rejects_an_unknown_role_before_launching_blender(self):
        # This is a HOST-side rejection: retro.py:58 calls contract.band_for
        # first, so the subprocess never starts. It was previously the ONLY
        # "blender-side failure" test, under that name -- which left the two
        # paths that actually matter (ok:false, and a missing report) with
        # zero coverage. Those are exactly the paths a stale report corrupts.
        with tempfile.TemporaryDirectory(dir=self.work) as temp:
            temp_path = Path(temp)
            contract = self._contract(temp_path)
            report_path = temp_path / "report.json"
            with self.assertRaisesRegex(RetroError, "colossal"):
                retro_pass(
                    self.config, self.source, contract, "colossal",
                    temp_path / "out.glb", report_path,
                )
            self.assertFalse(
                report_path.is_file(),
                "a host-side rejection must not leave a report behind",
            )

    def test_raises_when_the_blender_side_reports_failure(self):
        # A REAL Blender launch that fails inside the script: the role is
        # valid host-side, so the subprocess starts, and the source cannot be
        # imported, so retro_pass.main writes ok:false with a reason. This is
        # the path that returns a well-formed failure report.
        with tempfile.TemporaryDirectory(dir=self.work) as temp:
            temp_path = Path(temp)
            contract = self._contract(temp_path)
            absent = temp_path / "no-such-mesh.fbx"
            report_path = temp_path / "report.json"
            with self.assertRaisesRegex(RetroError, "retro pass failed"):
                retro_pass(
                    self.config, absent, contract, "large",
                    temp_path / "out.glb", report_path,
                )
            # The report must exist, be well formed, and say why.
            written = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertFalse(written["ok"])
            self.assertIsNotNone(written["error"])
            self.assertIn("texture", written)
            self.assertFalse((temp_path / "out.glb").is_file())
            # A failed run must NOT be stamped with a contract digest: that
            # stamp is the reproducibility certificate.
            self.assertNotIn("contract_digest", written)

    def test_raises_when_blender_writes_no_report_at_all(self):
        # The crash path: Blender launches and dies without the script ever
        # running, so nothing is written. Provoked for real by pointing the
        # launcher at a script that does not exist.
        #
        # This is the path a stale report used to corrupt: with a previous
        # run's report left in place, run_blender_script would have returned
        # THAT, retro.py would have seen its ok:true and the previous run's
        # .glb still on disk, and stamped the CURRENT contract digest onto it.
        with tempfile.TemporaryDirectory(dir=self.work) as temp:
            temp_path = Path(temp)
            contract = self._contract(temp_path)
            report_path = temp_path / "report.json"
            output = temp_path / "out.glb"
            # Both artefacts of a "previous run", exactly as they would be
            # left behind by a successful build into the same directory.
            report_path.write_text(
                json.dumps({"ok": True, "triangles_out": 1, "stale": True}),
                encoding="utf-8",
            )
            output.write_bytes(b"stale glb from the previous run")

            with mock.patch("factory.retro.SCRIPT", temp_path / "absent_script.py"):
                with self.assertRaisesRegex(BlenderError, "produced no report"):
                    retro_pass(
                        self.config, self.source, contract, "large",
                        output, report_path,
                    )
            self.assertFalse(report_path.is_file())

    def test_raises_when_the_report_claims_success_but_nothing_was_written(self):
        # The remaining branch of retro_pass's own contract. Reached with a
        # stubbed launcher because a real Blender that reports ok:true has by
        # definition already exported.
        with tempfile.TemporaryDirectory(dir=self.work) as temp:
            temp_path = Path(temp)
            contract = self._contract(temp_path)
            with mock.patch(
                "factory.retro.run_blender_script",
                return_value={"ok": True, "triangles_out": 10},
            ):
                with self.assertRaisesRegex(RetroError, "does not exist"):
                    retro_pass(
                        self.config, self.source, contract, "large",
                        temp_path / "never-written.glb", temp_path / "report.json",
                    )


if __name__ == "__main__":
    unittest.main()
