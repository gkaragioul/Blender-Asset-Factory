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

    def _run(self, role: str) -> tuple[dict, Path]:
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
                "contract": CONTRACT_PAYLOAD,
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


if __name__ == "__main__":
    unittest.main()
