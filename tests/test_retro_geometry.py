import tempfile
import unittest
from pathlib import Path

from factory.blender import discover_blender, run_blender_script
from factory.config import FactoryConfig
from factory.style_contract import StyleContract
from tests.fixtures import FixtureUnavailable, trenchgun_fbx
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


if __name__ == "__main__":
    unittest.main()
