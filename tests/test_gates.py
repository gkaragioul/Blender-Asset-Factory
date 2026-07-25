import json
import tempfile
import unittest
from pathlib import Path

from factory.config import FactoryConfig
from factory.gates import (
    GATE2_CATASTROPHE,
    MIN_ATLAS_COVERAGE,
    MIN_DISTINCT_COLOURS,
    MIN_PART_TEXELS,
    NEAREST_FILTER,
    PLACEMENT_TOLERANCE,
    gate1,
    gate2,
    rank_candidates,
    verdict,
)
from factory.png import encode_rgba
from factory.style_contract import StyleContract
from tests.glb_fixture import (
    GATE_PALETTE,
    GATE_TEXTURE_SIZE,
    LINEAR,
    black_texture_png,
    conforming_retro_report,
    flat_part_colours_png,
    gate_glb_bytes,
    lost_cutout_retro_report,
    misplaced_retro_report,
    palette_texture_png,
    untextured_part_retro_report,
    wiped_atlas_retro_report,
)
from tests.temp_paths import temporary_root

CONTRACT = {
    "schema_version": 1,
    "palette": "palette.png",
    "texture_size": GATE_TEXTURE_SIZE,
    "filtering": "nearest",
    "polycount_bands": {"small": 400, "medium": 1000, "large": 2500},
    "grid_unit": 0.5,
    "up_axis": "Y",
    "drop_maps": ["normal", "roughness", "metallic"],
    "vertex_light_bake": True,
}


class GateTest(unittest.TestCase):
    def setUp(self):
        self.config = FactoryConfig.load()
        self.temp = tempfile.TemporaryDirectory(dir=temporary_root())
        temp_path = Path(self.temp.name)
        rgba = bytearray()
        for colour in GATE_PALETTE:
            rgba.extend((*colour, 255))
        (temp_path / "palette.png").write_bytes(
            encode_rgba(len(GATE_PALETTE), 1, bytes(rgba))
        )
        path = temp_path / "contract.json"
        path.write_text(json.dumps(CONTRACT), encoding="utf-8")
        self.contract = StyleContract.load(self.config, path)

    def tearDown(self):
        self.temp.cleanup()

    def _gate1(self, glb=None, report=None, role="small", **kwargs):
        options = {
            "triangles": 100,
            "validator_ok": True,
            "preview_ok": True,
        }
        options.update(kwargs)
        return gate1(
            gate_glb_bytes() if glb is None else glb,
            self.contract,
            role,
            retro_report=conforming_retro_report() if report is None else report,
            **options,
        )

    # -- the conforming baseline ------------------------------------------

    def test_gate1_passes_a_conforming_asset(self):
        report = self._gate1(triangles=380)
        self.assertTrue(report["ok"], report["failures"])

    # -- pre-existing protections, unchanged -------------------------------

    def test_gate1_fails_over_budget_triangles(self):
        report = self._gate1(triangles=401)
        self.assertFalse(report["ok"])
        self.assertIn("triangle_budget", report["failures"])

    def test_gate1_fails_off_palette_texture(self):
        report = self._gate1(glb=gate_glb_bytes(palette_texture_png(colours=((1, 2, 3),))))
        self.assertFalse(report["ok"])
        self.assertIn("palette_conformance", report["failures"])

    def test_gate1_fails_forbidden_material_texture(self):
        report = self._gate1(
            glb=gate_glb_bytes(materials=[{"name": "flat", "normalTexture": {"index": 0}}])
        )
        self.assertFalse(report["ok"])
        self.assertIn("dropped_maps", report["failures"])

    def test_gate1_fails_forbidden_metallic_roughness_texture(self):
        # drop_maps includes "roughness" and "metallic", but in glTF those
        # live nested at pbrMetallicRoughness.metallicRoughnessTexture, not
        # as a top-level material key like normalTexture/occlusionTexture/
        # emissiveTexture. A shipped metallic/roughness texture must still
        # be caught.
        report = self._gate1(
            glb=gate_glb_bytes(
                materials=[
                    {
                        "name": "flat",
                        "pbrMetallicRoughness": {
                            "metallicRoughnessTexture": {"index": 0}
                        },
                    }
                ]
            )
        )
        self.assertFalse(report["ok"])
        self.assertIn("dropped_maps", report["failures"])

    def test_gate1_fails_when_the_validator_failed(self):
        report = self._gate1(validator_ok=False)
        self.assertFalse(report["ok"])
        self.assertIn("gltf_validator", report["failures"])

    def test_gate1_fails_when_the_runtime_preview_failed(self):
        # The counterpart branch. It was never exercised, because build_pack
        # hardcoded preview_ok=True and the test named
        # "..._validator_or_preview_failed" only ever passed validator_ok=False
        # -- so the spec's "loads in the pinned Three.js viewer" criterion
        # could not fail in production OR in test.
        report = self._gate1(preview_ok=False)
        self.assertFalse(report["ok"])
        self.assertIn("runtime_preview", report["failures"])

    # -- spec coverage gap: texture size and filtering ----------------------

    def test_gate1_fails_a_texture_of_the_wrong_size(self):
        wrong = GATE_TEXTURE_SIZE * 2
        report = self._gate1(glb=gate_glb_bytes(palette_texture_png(size=wrong)))
        self.assertFalse(report["ok"])
        self.assertIn("texture_size", report["failures"])
        self.assertEqual(report["details"]["texture_dimensions"], [[wrong, wrong]])

    def test_gate1_fails_linear_filtering(self):
        report = self._gate1(glb=gate_glb_bytes(mag_filter=LINEAR))
        self.assertFalse(report["ok"])
        self.assertIn("texture_filtering", report["failures"])

    def test_gate1_fails_an_absent_sampler(self):
        # glTF leaves the default filter implementation-defined and every real
        # runtime picks a linear one, so "no sampler" must fail rather than be
        # assumed nearest.
        report = self._gate1(glb=gate_glb_bytes(mag_filter=None))
        self.assertFalse(report["ok"])
        self.assertIn("texture_filtering", report["failures"])

    def test_the_nearest_filter_constant_is_the_gltf_enum(self):
        self.assertEqual(NEAREST_FILTER, 9728)

    # -- LOWER BOUNDS: the degenerate assets that used to pass ---------------

    def test_gate1_rejects_a_black_texture(self):
        # Blind spot #1. Uniformly black, and PERFECTLY palette-conforming:
        # one colour is trivially a member of any palette.
        glb = gate_glb_bytes(black_texture_png())
        report = self._gate1(glb=glb)
        self.assertFalse(report["ok"])
        self.assertIn("texture_detail", report["failures"])
        self.assertNotIn("palette_conformance", report["failures"])
        self.assertEqual(report["details"]["distinct_colours"], 1)

    def test_gate1_rejects_flat_per_part_colours(self):
        # Blind spot #2. Two flat regions: passes every `distinct > 1` check
        # the project previously relied on, and passes conformance.
        report = self._gate1(glb=gate_glb_bytes(flat_part_colours_png()))
        self.assertFalse(report["ok"])
        self.assertIn("texture_detail", report["failures"])
        self.assertNotIn("palette_conformance", report["failures"])
        self.assertEqual(report["details"]["distinct_colours"], 2)

    def test_gate1_rejects_a_wiped_atlas(self):
        # Blind spot #4. The texture itself is fine; the atlas behind it
        # claims nothing, so the texture describes no surface.
        report = self._gate1(report=wiped_atlas_retro_report())
        self.assertFalse(report["ok"])
        self.assertIn("atlas_coverage", report["failures"])
        self.assertIn("empty_part_texture", report["failures"])

    def test_gate1_rejects_a_part_with_no_texture_region(self):
        # The per-material black bake. Six healthy materials outvote one dead
        # one, so retro_pass's aggregate _bake_wrote_nothing check never fires.
        report = self._gate1(report=untextured_part_retro_report())
        self.assertFalse(report["ok"])
        self.assertIn("empty_part_texture", report["failures"])
        self.assertEqual(report["details"]["lower_bounds"]["smallest_part_texels"], 0)

    def test_gate1_rejects_a_lost_cutout_mask(self):
        # Blind spot #3, and the tracked barbed_wire_coil launch blocker: the
        # source declared alpha sources and the export shipped OPAQUE, i.e. a
        # solid slab where a cutout belongs.
        report = self._gate1(report=lost_cutout_retro_report())
        self.assertFalse(report["ok"])
        self.assertIn("alpha_mode", report["failures"])

    def test_gate1_accepts_a_cutout_that_survived(self):
        # The control for the check above: declaring MASK is the expected
        # outcome, and must not be penalised.
        report = self._gate1(
            report=conforming_retro_report(
                stages={"alpha_sources": ["CutoutMaterial"]},
                texture={"alpha_mode": "MASK"},
            )
        )
        self.assertTrue(report["ok"], report["failures"])

    def test_lower_bound_constants_sit_below_the_measured_conversion(self):
        # The measured trenchgun conversion: smallest part 187 atlas texels,
        # atlas coverage 0.0729, 8 distinct colours from an 8-entry palette.
        # Every floor must sit below those, or the gate rejects the only asset
        # the pipeline is known to produce correctly.
        self.assertLess(MIN_PART_TEXELS, 187)
        self.assertLess(MIN_ATLAS_COVERAGE, 0.0729)
        self.assertLess(MIN_DISTINCT_COLOURS, 8)

    # -- grid and pivot conformance ----------------------------------------

    def test_gate1_rejects_an_asset_that_is_not_grounded_or_grid_aligned(self):
        # Grid and pivot conformance is what lets 30 assets sit together in
        # one scene, and it was implemented NOWHERE. Gate 2 cannot cover it:
        # silhouette IoU frames each render on its own bounding box, which is
        # deliberately translation-invariant and therefore blind to pivot.
        report = self._gate1(report=misplaced_retro_report())
        self.assertFalse(report["ok"])
        self.assertIn("grounding", report["failures"])
        self.assertIn("grid_alignment", report["failures"])

    def test_gate1_rejects_grounding_alone(self):
        report = self._gate1(
            report=conforming_retro_report(
                bounds={
                    "min": {"x": -0.25, "y": 0.31, "z": -0.5},
                    "max": {"x": 0.25, "y": 0.51, "z": 0.5},
                }
            )
        )
        self.assertFalse(report["ok"])
        self.assertIn("grounding", report["failures"])
        self.assertNotIn("grid_alignment", report["failures"])

    def test_gate1_rejects_grid_misalignment_alone(self):
        report = self._gate1(
            report=conforming_retro_report(
                bounds={
                    "min": {"x": -0.12, "y": 0.0, "z": -0.5},
                    "max": {"x": 0.38, "y": 0.2, "z": 0.5},
                }
            )
        )
        self.assertFalse(report["ok"])
        self.assertIn("grid_alignment", report["failures"])
        self.assertNotIn("grounding", report["failures"])

    def test_gate1_accepts_a_footprint_centred_on_a_nonzero_grid_multiple(self):
        # Grid alignment is a multiple of grid_unit, not "at the origin".
        report = self._gate1(
            report=conforming_retro_report(
                bounds={
                    "min": {"x": 0.75, "y": 0.0, "z": -0.5},
                    "max": {"x": 1.25, "y": 0.2, "z": 0.5},
                }
            )
        )
        self.assertTrue(report["ok"], report["failures"])
        self.assertEqual(report["details"]["placement"]["horizontal_centres"]["x"], 1.0)

    def test_gate1_fails_closed_when_bounds_are_missing(self):
        report = self._gate1(report=conforming_retro_report(bounds=None))
        self.assertFalse(report["ok"])
        self.assertIn("bounds_missing", report["failures"])

    def test_placement_tolerance_admits_the_measured_grounding(self):
        # The real conversion grounded its base at 1.66e-09.
        self.assertGreater(PLACEMENT_TOLERANCE, 1.66e-09)

    # -- gate 2 and verdict -------------------------------------------------

    def test_gate2_uses_a_catastrophe_floor_not_a_quality_threshold(self):
        # 0.613 is a MEASURED good conversion (45,881 -> 2,470 triangles).
        # It must pass. The old 0.95 threshold would have rejected it.
        self.assertEqual(gate2({"minimum": 0.613, "mean": 0.637})["verdict"], "pass")
        self.assertEqual(gate2({"minimum": 0.46, "mean": 0.50})["verdict"], "pass")
        # 0.03 is the MEASURED Y-up double-rotation defect. It must be rejected.
        self.assertEqual(gate2({"minimum": 0.03, "mean": 0.05})["verdict"], "reject")
        self.assertEqual(gate2({"minimum": 0.44, "mean": 0.60})["verdict"], "reject")
        self.assertEqual(GATE2_CATASTROPHE, 0.45)

    def test_rank_candidates_orders_best_first(self):
        comparisons = [
            {"minimum": 0.58, "mean": 0.61},
            {"minimum": 0.71, "mean": 0.74},
            {"minimum": 0.63, "mean": 0.66},
        ]
        self.assertEqual(rank_candidates(comparisons), [1, 2, 0])

    def test_rank_candidates_rejects_an_empty_list(self):
        with self.assertRaisesRegex(ValueError, "at least one candidate"):
            rank_candidates([])

    def test_verdict_combines_both_gates(self):
        good = {"ok": True, "failures": []}
        bad = {"ok": False, "failures": ["triangle_budget"]}
        self.assertEqual(verdict(good, {"verdict": "pass"}), "pass")

        self.assertEqual(verdict(good, {"verdict": "reject"}), "reject")
        self.assertEqual(verdict(bad, {"verdict": "pass"}), "reject")


if __name__ == "__main__":
    unittest.main()
