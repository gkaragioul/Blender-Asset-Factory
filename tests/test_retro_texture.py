import json
import struct
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from factory.blender import discover_blender, run_blender_script
from factory.config import FactoryConfig
from factory.palette import conformance, load_palette
from factory.png import decode_rgba
from tests.fixtures import FixtureUnavailable, retro_palette_png, trenchgun_fbx
from tests.temp_paths import temporary_root

SCRIPT = Path(__file__).resolve().parents[1] / "factory" / "scripts" / "retro_pass.py"
TEXTURE_SIZE = 256
CONTRACT_PAYLOAD = {
    "texture_size": TEXTURE_SIZE,
    "filtering": "nearest",
    "polycount_bands": {"small": 400, "medium": 1000, "large": 2500},
    "grid_unit": 0.5,
    "up_axis": "Y",
    "drop_maps": ["normal", "roughness", "metallic"],
    "vertex_light_bake": True,
}
GL_NEAREST = 9728


def _glb_document(path: Path) -> dict:
    data = path.read_bytes()
    json_length = struct.unpack_from("<I", data, 12)[0]
    return json.loads(data[20 : 20 + json_length].decode("utf-8"))


def _glb_textures(path: Path) -> list[bytes]:
    data = path.read_bytes()
    json_length = struct.unpack_from("<I", data, 12)[0]
    document = json.loads(data[20 : 20 + json_length].decode("utf-8"))
    binary_offset = 20 + json_length + 8
    images = []
    for image in document.get("images", []):
        view = document["bufferViews"][image["bufferView"]]
        start = binary_offset + view.get("byteOffset", 0)
        images.append(data[start : start + view["byteLength"]])
    return images


class RetroTextureTest(unittest.TestCase):
    """Assertions over ONE real Blender run of the full retro pass.

    A run of retro_pass.py against the trenchgun fixture costs tens of
    seconds (FBX import, six-way material split, decimation, a Cycles bake).
    Every assertion in this class reads a different property of the same
    export, so the run is shared across the class rather than repeated
    per-test method. Nothing here mutates the result, so the sharing cannot
    leak state between tests.
    """

    report: dict
    output: Path
    palette: Path

    @classmethod
    def setUpClass(cls):
        cls.config = FactoryConfig.load()
        if discover_blender(cls.config) is None:
            raise unittest.SkipTest("Blender is not available on this host")
        cls.source = trenchgun_fbx()

        work = temporary_root() / "retro"
        work.mkdir(parents=True, exist_ok=True)
        temp_dir = tempfile.TemporaryDirectory(dir=work)
        cls.addClassCleanup(temp_dir.cleanup)
        temp = Path(temp_dir.name)

        cls.palette = retro_palette_png(temp)
        cls.output = temp / "out.glb"
        cls.report = run_blender_script(
            cls.config,
            SCRIPT,
            {
                "source": str(cls.source),
                "output": str(cls.output),
                "role": "large",
                "palette": str(cls.palette),
                "contract": CONTRACT_PAYLOAD,
            },
            temp / "report.json",
        )

    def test_run_succeeded(self):
        self.assertTrue(self.report["ok"], self.report.get("error"))
        self.assertTrue(self.output.is_file())

    def test_bakes_a_quantized_texture_at_contract_size(self):
        self.assertTrue(self.report["ok"], self.report.get("error"))
        self.assertEqual(self.report["texture"]["size"], TEXTURE_SIZE)
        self.assertTrue(self.report["texture"]["quantized"])
        self.assertEqual(
            self.report["texture"]["palette_colours"],
            len(load_palette(self.palette)),
        )

    def test_baked_texture_carries_real_detail(self):
        # The failure this exists to catch: Cycles reports "No active and
        # selected image texture node found in material X" as an *Info* line
        # and still exits successfully, so a misconfigured bake target
        # leaves the image untouched black. Every texel then snaps to the
        # darkest palette entry and the export is one flat colour that
        # passes palette conformance perfectly. This suite was green in
        # exactly that state until the texture was inspected by hand, so
        # conformance alone is not evidence that the bake ran.
        distinct = self.report["texture"]["distinct_colours"]
        self.assertGreater(
            distinct, 1, "baked texture is a single flat colour: the bake wrote nothing"
        )
        colours = Counter()
        for image in _glb_textures(self.output):
            _width, _height, rgba = decode_rgba(image)
            colours.update(
                (rgba[i], rgba[i + 1], rgba[i + 2]) for i in range(0, len(rgba), 4)
            )
        self.assertEqual(len(colours), distinct)
        # And the detail must be spread over the atlas, not a stray texel:
        # the second-most-common colour has to be more than noise.
        self.assertGreater(colours.most_common(2)[1][1], 100)

    def test_every_part_receives_atlas_texels(self):
        # A part packed into zero texels is exported with a material and a
        # texture that contain nothing of it. No aggregate coverage number
        # would show that, so it is checked per part.
        per_part = self.report["stages"]["uv_texels_per_part"]
        self.assertEqual(sorted(per_part), sorted(self.report["parts"]))
        for name, texels in sorted(per_part.items()):
            self.assertGreater(texels, 0, f"part {name!r} got no atlas texels")

    def test_every_exported_texel_is_an_exact_palette_member(self):
        # This is the assertion Gate 1 (Task 10) will make about every asset
        # in a pack, made here at the point where the bytes are produced.
        # "Exact" is not negotiable and is not approximated: a single
        # foreign colour means the palette round trip through Blender's
        # colour management is lossy, and every asset in every pack would be
        # rejected downstream.
        textures = _glb_textures(self.output)
        self.assertTrue(textures, "exported GLB embeds no image")
        colours = load_palette(self.palette)
        for image in textures:
            result = conformance(image, colours)
            self.assertEqual(result["pixels"], TEXTURE_SIZE * TEXTURE_SIZE)
            self.assertTrue(
                result["ok"],
                f"{result['foreign_pixels']} foreign pixels: "
                f"{result['foreign_colours'][:4]}",
            )

    def test_exports_exactly_one_texture(self):
        # A PS1 asset carries ONE texture. Six parts baking into six images
        # would also pass conformance, so this is what actually pins the
        # shared-atlas design in place.
        self.assertEqual(len(_glb_textures(self.output)), 1)
        document = _glb_document(self.output)
        self.assertEqual(len(document.get("images", [])), 1)

    def test_shared_uv_atlas_has_no_cross_part_overlap(self):
        # The hazard this measures: _split_by_material leaves ~six objects,
        # and if each is unwrapped on its own it gets the whole 0..1 square.
        # Baking those into one shared image makes each part overwrite the
        # last, and the result is garbage that no other number in the report
        # would reveal. So the script rasterizes each part's UV triangles
        # onto a shared grid AT THE TEXTURE'S OWN RESOLUTION -- a cell is a
        # texel of the actual bake target -- and counts texels claimed by
        # more than one part. Zero is the only acceptable answer, and
        # covered_cells guards against the degenerate way to score zero:
        # having no UV coverage at all.
        #
        # This is a measurement, not an assumption: smart_project on its own
        # scored 10 overlapping cells here, which is what motivated the
        # explicit pack_islands pass in retro_pass.py.
        stages = self.report["stages"]
        self.assertEqual(
            stages["uv_overlap_cells"],
            0,
            f"{stages['uv_overlap_cells']} of {stages['uv_covered_cells']} "
            "covered atlas cells are claimed by more than one part",
        )
        self.assertGreater(stages["uv_covered_cells"], 1000)
        self.assertTrue(stages["uv_regenerated"])

    def test_uses_nearest_neighbour_sampling(self):
        document = _glb_document(self.output)
        samplers = document.get("samplers", [])
        self.assertTrue(samplers, "exported GLB declares no sampler")
        for sampler in samplers:
            self.assertEqual(sampler.get("magFilter"), GL_NEAREST)

    def test_drops_pbr_maps_named_in_the_contract(self):
        self.assertEqual(
            self.report["dropped_maps"], ["metallic", "normal", "roughness"]
        )
        document = _glb_document(self.output)
        self.assertTrue(document.get("materials"))
        for material in document["materials"]:
            self.assertNotIn("normalTexture", material)
            self.assertNotIn("occlusionTexture", material)
            self.assertNotIn("emissiveTexture", material)
            pbr = material.get("pbrMetallicRoughness", {})
            self.assertNotIn("metallicRoughnessTexture", pbr)

    def test_reports_vertex_light_bake_as_not_applied(self):
        # The style contract carries the flag and this plan does not
        # implement it. Reporting False keeps a later stage from assuming
        # vertex lighting happened because the contract asked for it.
        self.assertTrue(CONTRACT_PAYLOAD["vertex_light_bake"])
        self.assertFalse(self.report["vertex_light_bake"])


class RetroTextureFailurePathTest(unittest.TestCase):
    def setUp(self):
        self.config = FactoryConfig.load()
        if discover_blender(self.config) is None:
            self.skipTest("Blender is not available on this host")
        self.source = trenchgun_fbx()

    def test_failed_run_still_reports_a_well_formed_texture_section(self):
        # run_blender_script turns a missing report into an opaque
        # BlenderError, and a report missing keys its caller indexes is
        # barely better. A run that dies before the texture stages must
        # still answer "texture" and "dropped_maps".
        work = temporary_root() / "retro"
        work.mkdir(parents=True, exist_ok=True)
        temp_dir = tempfile.TemporaryDirectory(dir=work)
        self.addCleanup(temp_dir.cleanup)
        temp = Path(temp_dir.name)

        report = run_blender_script(
            self.config,
            SCRIPT,
            {
                "source": str(self.source),
                "output": str(temp / "out.glb"),
                "role": "colossal",
                "palette": str(retro_palette_png(temp)),
                "contract": CONTRACT_PAYLOAD,
            },
            temp / "report.json",
        )
        self.assertFalse(report["ok"])
        self.assertIn("colossal", report["error"])
        self.assertEqual(
            report["texture"],
            {
                "size": 0,
                "quantized": False,
                "palette_colours": 0,
                "distinct_colours": 0,
                "atlas_coverage": 0.0,
            },
        )
        self.assertEqual(report["dropped_maps"], [])
        self.assertFalse(report["vertex_light_bake"])


if __name__ == "__main__":
    unittest.main()
