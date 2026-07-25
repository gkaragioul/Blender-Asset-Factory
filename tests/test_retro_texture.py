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
from tests.glb_fixture import TRANSLUCENT_ALPHA, write_multi_texture_cube_glb
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

    def test_source_albedo_maps_were_actually_relinked(self):
        # The failure `test_baked_texture_carries_real_detail` does NOT
        # catch. The trenchgun's maps all point at dead absolute paths from
        # the machine that exported the FBX, and _resolve_source_maps
        # relinks them from the shipped `textures/` directory. If that stops
        # working -- `textures/` moves, the zip layout changes,
        # bpy.ops.file.find_missing_files behaves differently -- then 0 of 18
        # resolve, every map is unlinked, and the bake falls back to seven
        # materials' flat base colours. That is seven distinct colours over
        # thousands of texels each: it passes distinct_colours > 1, passes
        # the most_common(2) > 100 check, passes conformance, and never
        # trips _bake_wrote_nothing because the image is not black. The
        # texture would carry zero albedo information and nothing would say
        # so.
        #
        # Thresholds are set against the measured real state of the fixture:
        # 18 maps referenced, 15 relinked, 3 unresolvable.
        stages = self.report["stages"]

        # 15 is exactly what relinking achieves today. Asserting >= 15 fails
        # the moment relinking degrades at all, while still allowing the
        # remaining 3 to start resolving if the fixture is ever repacked.
        self.assertGreaterEqual(
            stages["source_uvs_pinned"],
            15,
            "source albedo maps were not relinked, so the bake is reading "
            "flat base colours instead of real texture data",
        )

        # The 3 known-unresolvable maps are a NAME mismatch, not a path
        # failure: the FBX asks for Cartridge_low_Cartridge_*.png and the zip
        # ships Cartridge_*.png. Bounding the count catches regression;
        # requiring every unresolved name to be one of the understood
        # Cartridge maps catches a NEW class of failure rather than letting
        # it hide inside the allowance.
        unresolved = stages["source_maps_unresolved"]
        self.assertLessEqual(len(unresolved), 3, unresolved)
        for name in unresolved:
            self.assertIn("Cartridge", name, f"unexpected unresolved map: {name}")

    def test_pixel_buffer_semantics_are_verified_at_runtime(self):
        # Quantization reads image.pixels and treats value * 255 as the
        # stored sRGB byte, which holds only because bpy.data.images.new
        # returns a byte-backed image with a raw passthrough buffer
        # (measured: writing 0.5 reads back 128/255, not the 188 an
        # sRGB-encoding round trip would give).
        #
        # This cannot be caught downstream. The exported PNG is assembled
        # literally out of palette entry bytes, so it is palette-exact by
        # construction whatever the source values meant -- if the buffer
        # semantics change, every texel snaps to the WRONG palette entry,
        # conformance still passes, distinct_colours stays plausible, and the
        # only symptom is a systematically washed-out texture. So the script
        # re-derives the claim on every run and fails the pass if it breaks.
        self.assertEqual(self.report["stages"]["pixel_semantics"], "byte-passthrough")

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


def _material_by_name(document: dict, name: str) -> dict:
    for material in document.get("materials", []):
        if material.get("name") == name:
            return material
    raise AssertionError(
        f"no material {name!r} in {[m.get('name') for m in document.get('materials', [])]}"
    )


class RetroTextureForeignMapTest(unittest.TestCase):
    """The pass must export ONE image whatever the source carried.

    Separate source from the trenchgun on purpose. The trenchgun's maps are
    base colour / roughness / metallic / normal, and the contract's drop_maps
    names the last three, so on that fixture "the pass enforces one texture"
    and "this source happened to have nothing else" are indistinguishable.
    The cube here carries an EMISSIVE map, on a socket drop_maps does not
    name, so it survives anything that works from a list of sockets to clear.

    Without positive enforcement the export carries two images: the
    palettized albedo and the raw source emissive. Gate 1 would then report
    thousands of foreign pixels coming from a source PNG and every clue would
    point at the quantizer, which is innocent.
    """

    report: dict
    output: Path
    palette: Path
    source: Path

    @classmethod
    def setUpClass(cls):
        cls.config = FactoryConfig.load()
        if discover_blender(cls.config) is None:
            raise unittest.SkipTest("Blender is not available on this host")

        work = temporary_root() / "retro"
        work.mkdir(parents=True, exist_ok=True)
        temp_dir = tempfile.TemporaryDirectory(dir=work)
        cls.addClassCleanup(temp_dir.cleanup)
        temp = Path(temp_dir.name)

        cls.source = write_multi_texture_cube_glb(temp / "multi_texture_cube.glb")
        cls.output = temp / "out.glb"
        cls.palette = retro_palette_png(temp)
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

    def test_exports_one_texture_even_when_the_source_has_extra_maps(self):
        report = self.report
        source, output, palette = self.source, self.output, self.palette
        # Confirm the fixture really does present two images, so a green
        # result cannot come from the fixture quietly losing its extra map.
        self.assertEqual(len(_glb_document(source).get("images", [])), 2)
        self.assertTrue(report["ok"], report.get("error"))

        # This source is fully metallic, and a metallic surface has no
        # diffuse component, so its albedo bake is black unless the pass
        # neutralises Metallic before baking. glTF's metallicFactor even
        # DEFAULTS to 1.0 when omitted, so this is the common case for the
        # metal weapons this pack converts, not an edge case.
        self.assertIn("Metallic", report["stages"]["bake_neutralized"])
        self.assertGreater(
            report["texture"]["distinct_colours"],
            1,
            "metallic source baked to a single flat colour",
        )

        # The emissive map must have been removed by name, not merely
        # unlinked -- an unlinked-but-present node is what the exporter
        # walks and writes.
        self.assertIn("CubeEmissive", report["stages"]["foreign_textures_removed"])

        document = _glb_document(output)
        self.assertEqual(
            len(document.get("images", [])),
            1,
            "export carries more than the one baked albedo texture",
        )
        for material in document.get("materials", []):
            self.assertNotIn("emissiveTexture", material)

        # And the one surviving image is still exactly palette-conformant.
        textures = _glb_textures(output)
        self.assertEqual(len(textures), 1)
        result = conformance(textures[0], load_palette(palette))
        self.assertTrue(
            result["ok"],
            f"{result['foreign_pixels']} foreign pixels: "
            f"{result['foreign_colours'][:4]}",
        )

    def test_source_transparency_survives_to_the_export(self):
        # The bake needs opaque, non-metallic inputs to yield a usable
        # albedo; the EXPORT must still say what the source said. Those are
        # different things, and conflating them destroys assets silently.
        #
        # The glTF exporter writes an unlinked Principled socket's
        # default_value out as a material factor, so a bake-time
        # neutralisation that is never restored SHIPS. Forcing alpha to 1.0
        # turns intentionally transparent or cutout geometry into a solid
        # slab, and no gate catches it: Gate 1 checks palette conformance and
        # triangle budget, Gate 2 compares silhouettes of the same geometry
        # before and after. Alpha cutout is how PS1-era art renders barbed
        # wire, chain-link, foliage and glass -- and barbed_wire_coil is a
        # planned asset in this pack.
        source_material = _material_by_name(
            _glb_document(self.source), "TranslucentMaterial"
        )
        # Assert the SOURCE really is translucent, so this test cannot pass
        # by the fixture quietly becoming opaque.
        self.assertEqual(source_material["alphaMode"], "BLEND")
        self.assertAlmostEqual(
            source_material["pbrMetallicRoughness"]["baseColorFactor"][3],
            TRANSLUCENT_ALPHA,
            places=4,
        )

        exported = _material_by_name(
            _glb_document(self.output), "TranslucentMaterial"
        )
        self.assertAlmostEqual(
            exported["pbrMetallicRoughness"].get("baseColorFactor", [1, 1, 1, 1])[3],
            TRANSLUCENT_ALPHA,
            places=4,
            msg="alpha was forced to 1.0; a cutout asset would export as a solid slab",
        )
        self.assertEqual(exported.get("alphaMode"), "BLEND")

        # And the decision about what was restored vs deliberately flattened
        # is recorded rather than implicit.
        factors = self.report["stages"]["shading_factors"]
        self.assertIn("Alpha", factors["restored"])
        self.assertIn("Transmission Weight", factors["restored"])
        # Metallic is the one deliberate exception, driven by the contract
        # naming `metallic` in drop_maps: the pass bakes flat albedo into the
        # base colour texture, and a renderer told metallicFactor 1 treats
        # that albedo as reflectance and draws the asset black.
        self.assertIn("metallic", CONTRACT_PAYLOAD["drop_maps"])
        self.assertIn("Metallic", factors["flattened"])
        self.assertNotIn("Metallic", factors["restored"])
        self.assertEqual(exported["pbrMetallicRoughness"]["metallicFactor"], 0)

    def test_translucent_part_still_bakes_real_detail(self):
        # The other half of the tension: restoring alpha must not come at the
        # cost of the bake. Both parts of this cube have to end up with real
        # texels, not a flat colour.
        self.assertTrue(self.report["ok"], self.report.get("error"))
        self.assertGreater(self.report["texture"]["distinct_colours"], 1)
        per_part = self.report["stages"]["uv_texels_per_part"]
        self.assertIn("TranslucentMaterial", per_part)
        for name, texels in sorted(per_part.items()):
            self.assertGreater(texels, 0, f"part {name!r} got no atlas texels")


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
