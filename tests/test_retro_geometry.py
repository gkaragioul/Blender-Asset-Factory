import json
import struct
import tempfile
import unittest
from pathlib import Path

from factory.blender import discover_blender, run_blender_script
from factory.config import FactoryConfig
from factory.style_contract import StyleContract
from tests.fixtures import FixtureUnavailable, retro_palette_png, trenchgun_fbx
from tests.glb_fixture import write_thin_plane_glb
from tests.temp_paths import temporary_root

SCRIPT = Path(__file__).resolve().parents[1] / "factory" / "scripts" / "retro_pass.py"
CONTRACT_PAYLOAD = {
    "texture_size": 256,
    "filtering": "nearest",
    "polycount_bands": {"small": 400, "medium": 1000, "large": 2500},
    "grid_unit": 0.5,
    "up_axis": "Y",
    "drop_maps": ["normal", "roughness", "metallic"],
    "vertex_light_bake": True,
}

# Same fixture, but with a budget of 1 triangle for the whole asset. This
# is unreachable within MAX_DECIMATE_PASSES: the trenchgun's 7 split parts
# each hit a topological floor (a DECIMATE collapse modifier cannot reduce
# a part below a handful of triangles without breaking manifoldness) well
# above 1 triangle combined. Used to exercise the non-convergence branch in
# retro_pass.py's main(), which the "large" role never reaches because it
# converges (2604 -> 2479 in earlier measurement).
UNREACHABLE_CONTRACT_PAYLOAD = {
    **CONTRACT_PAYLOAD,
    "polycount_bands": {**CONTRACT_PAYLOAD["polycount_bands"], "impossible": 1},
}

# The contract declares up_axis "Y". retro_pass.py rotates the imported mesh
# -90deg about X whenever up_axis == "Y" (Blender's own coordinate frame is
# always Z-up; this rotation moves the mesh's "up" extent from world Z onto
# world Y). So in the reported world-space bounds, Y is the up axis and X/Z
# are the horizontal axes that get grid-centred.
UP_AXIS = "y"
HORIZONTAL_AXES = ("x", "z")


def _glb_triangles(path: Path) -> int:
    """Triangles actually present in the exported GLB.

    Counted from the file rather than trusted from the report, because the
    whole point of the export-time validation is that the number the report
    carries and the number that ships are the same number.
    """
    data = path.read_bytes()
    json_length = struct.unpack_from("<I", data, 12)[0]
    document = json.loads(data[20 : 20 + json_length].decode("utf-8"))
    total = 0
    for mesh in document.get("meshes", []):
        for primitive in mesh["primitives"]:
            # glTF mode 4 is TRIANGLES and is the default when absent.
            if primitive.get("mode", 4) != 4:
                raise AssertionError(
                    f"unexpected primitive mode {primitive.get('mode')}"
                )
            accessor = document["accessors"][primitive["indices"]]
            total += accessor["count"] // 3
    return total


class RetroGeometryTest(unittest.TestCase):
    def setUp(self):
        self.config = FactoryConfig.load()
        if discover_blender(self.config) is None:
            self.skipTest("Blender is not available on this host")
        try:
            self.source = trenchgun_fbx()
        except FixtureUnavailable as error:
            self.skipTest(str(error))

    def _run(self, role: str, contract: dict = CONTRACT_PAYLOAD) -> tuple[dict, Path]:
        work = self.config.root / "tmp" / "factory" / "tests" / "retro"
        work.mkdir(parents=True, exist_ok=True)
        # Deliberately not a `with tempfile.TemporaryDirectory(...) as temp:`
        # block: the caller inspects the returned output path (e.g.
        # `output.is_file()`) after _run() returns, but TemporaryDirectory
        # deletes its directory tree in __exit__, which for a `with` block
        # containing a `return` runs *before* control reaches the caller.
        # That silently wiped out the exported .glb before the assertion
        # ever ran. addCleanup defers deletion to the end of the test
        # method instead, after assertions have had a chance to inspect it.
        temp_dir = tempfile.TemporaryDirectory(dir=work)
        self.addCleanup(temp_dir.cleanup)
        temp = Path(temp_dir.name)
        output = temp / "out.glb"
        report_path = temp / "report.json"
        report = run_blender_script(
            self.config,
            SCRIPT,
            {
                "source": str(self.source),
                "output": str(output),
                "role": role,
                # retro_pass.py is one pipeline, not two: the texture stages
                # (Task 7) always run, so `palette` is always required. The
                # geometry assertions below do not care what the palette is,
                # only that a valid one is supplied.
                "palette": str(retro_palette_png(temp)),
                "contract": contract,
            },
            report_path,
        )
        return report, output if output.is_file() else Path()

    def test_decimates_to_large_band(self):
        report, output = self._run("large")
        self.assertTrue(report["ok"], report.get("error"))
        self.assertGreater(report["triangles_in"], 2500)
        self.assertLessEqual(report["triangles_out"], 2500)
        self.assertTrue(output.is_file())

    def test_exported_meshes_pass_blender_validation(self):
        # The glTF exporter used to log "Mesh <name> is not valid, and may be
        # exported wrongly" for every part. Two stages caused it: the bmesh
        # carve in _split_by_material carried the skinned source's deform
        # weights onto parts that have no vertex groups at all, and the
        # DECIMATE collapse modifier emitted duplicate faces. "May be exported
        # wrongly" makes the exported geometry a different thing from the
        # geometry measured in-process, which is exactly what Gate 2's
        # silhouette IoU compares -- so it has to be zero, not small.
        #
        # export_validation is the pass's own final check, run immediately
        # before the export call: it re-validates every mesh and reports what
        # it still had to repair. Empty means nothing reached the exporter in
        # a broken state.
        report, _output = self._run("large")
        self.assertTrue(report["ok"], report.get("error"))
        self.assertEqual(
            report["stages"]["export_validation"],
            {},
            "meshes were still being repaired at export time",
        )

    def test_reported_triangle_count_matches_export(self):
        # Independent of the report: validate() DELETES degenerate geometry,
        # so a validation step placed after the count is taken would leave
        # triangles_out describing a mesh that was never exported. Counting
        # from the GLB itself is what proves the two agree.
        report, output = self._run("large")
        self.assertTrue(report["ok"], report.get("error"))
        self.assertTrue(output.is_file())
        self.assertEqual(_glb_triangles(output), report["triangles_out"])

    def test_preserves_semantic_parts(self):
        report, _output = self._run("large")
        self.assertIn("Barrel", report["parts"])
        self.assertIn("Stock", report["parts"])

    def test_normalizes_origin_to_grid(self):
        # This asserts against the RAW reported bounds (min/max), not
        # against bounds["origin"] -- origin is itself produced by calling
        # snap() on the bounds inside the script, so asserting origin is
        # grid-snapped is vacuous: it would pass even if the underlying
        # transform were completely broken.
        report, _output = self._run("large")
        grid_unit = CONTRACT_PAYLOAD["grid_unit"]
        bounds = report["bounds"]

        for axis in HORIZONTAL_AXES:
            centre = (bounds["min"][axis] + bounds["max"][axis]) / 2
            remainder = abs(centre) % grid_unit
            self.assertTrue(
                remainder < 1e-4 or abs(remainder - grid_unit) < 1e-4,
                f"raw centre on {axis} is not grid-snapped: {centre} (bounds={bounds})",
            )

        base = bounds["min"][UP_AXIS]
        self.assertLess(
            abs(base),
            1e-4,
            f"object base on up axis {UP_AXIS!r} is not at zero: {base} (bounds={bounds})",
        )

    def test_rejects_unknown_role(self):
        report, _output = self._run("colossal")
        self.assertFalse(report["ok"])
        self.assertIn("colossal", report["error"])

    def test_reports_failure_when_decimate_cannot_converge(self):
        # Regression test for fix round 1: _decimate's pass loop used to be
        # bounded only by MAX_DECIMATE_PASSES, and main() exported and set
        # ok=True regardless of whether triangles_out actually reached the
        # budget. That let an over-budget asset report success here and get
        # silently rejected later by Gate 1 (Task 10) with no explanation
        # of why. A budget of 1 triangle is unreachable for this fixture,
        # so this exercises the "stop and report" branch for real rather
        # than asserting on a mock.
        report, output = self._run("impossible", contract=UNREACHABLE_CONTRACT_PAYLOAD)
        self.assertFalse(report["ok"])
        self.assertIn("did not converge", report["error"])
        self.assertIn("budget=1", report["error"])
        self.assertIn("impossible", report["error"])
        # triangles_out must still reflect what was actually achieved, and
        # it must be reported as over budget -- that's the whole point.
        self.assertGreater(report["triangles_out"], 1)
        # A failed geometry pass must not produce an exported asset that a
        # downstream stage could mistake for a valid, in-budget one.
        self.assertFalse(output.is_file())


class FlatGeometrySurvivesTest(unittest.TestCase):
    """A zero-thickness card must reach the exporter.

    `_remove_floaters` compared an AABB VOLUME -- with zero extents floored at
    1e-9 -- against `(diagonal * 0.001) ** 3`. That deletes ALL planar
    geometry, whatever its size: a 1x1 card scored 1e-9 against a threshold of
    2.8e-9. Cutout cards are how this pack renders `barbed_wire_coil`,
    `barbed_wire_post`, foliage, chain-link and signpost lettering, so the
    defect silently emptied real catalogued assets.

    It survived because it was worked AROUND rather than filed: every fixture
    in tests/glb_fixture.py was a cube, and two of them said so in their
    docstrings. This test uses a genuine plane, so nothing about it can dodge
    the defect.
    """

    def setUp(self):
        self.config = FactoryConfig.load()
        if discover_blender(self.config) is None:
            self.skipTest("Blender is not available on this host")
        work = self.config.root / "tmp" / "factory" / "tests" / "retro-plane"
        work.mkdir(parents=True, exist_ok=True)
        temp_dir = tempfile.TemporaryDirectory(dir=work)
        self.addCleanup(temp_dir.cleanup)
        self.temp = Path(temp_dir.name)

    def test_a_zero_thickness_plane_is_not_removed_as_a_floater(self):
        source = write_thin_plane_glb(self.temp / "plane" / "plane.glb")
        output = self.temp / "plane.glb"
        report = run_blender_script(
            self.config,
            SCRIPT,
            {
                "source": str(source),
                "output": str(output),
                "role": "small",
                "palette": str(retro_palette_png(self.temp)),
                "contract": CONTRACT_PAYLOAD,
            },
            self.temp / "report.json",
        )
        self.assertTrue(report["ok"], report.get("error"))
        # cleanup is the part count AFTER _remove_floaters. Under the old
        # volume threshold this was 0 and the run then failed outright with
        # an empty bounds computation -- so this assertion discriminates.
        self.assertEqual(report["stages"]["split"], 1)
        self.assertEqual(report["stages"]["cleanup"], 1)
        self.assertEqual(report["parts"], ["PlaneMaterial"])
        self.assertTrue(output.is_file())
        self.assertEqual(_glb_triangles(output), report["triangles_out"])
        self.assertEqual(report["triangles_out"], 2)
        # And the flat part must own real atlas texels: surviving the floater
        # cull is worth nothing if it ships untextured.
        self.assertGreater(min(report["stages"]["uv_texels_per_part"].values()), 0)


if __name__ == "__main__":
    unittest.main()
