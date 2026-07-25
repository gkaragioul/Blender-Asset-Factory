import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import factory.silhouette as silhouette
from factory.blender import discover_blender
from factory.config import FactoryConfig
from factory.gltf_inspection import inspect_glb
from factory.png import encode_rgba
from factory.retro import retro_pass
from factory.silhouette import (
    VIEWS,
    SilhouetteError,
    compare,
    effective_radius,
    iou,
    mask_from_png,
    render_masks,
)
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


def _mask_png(rows: list[str]) -> bytes:
    rgba = bytearray()
    for row in rows:
        for character in row:
            value = 255 if character == "#" else 0
            rgba.extend((value, value, value, 255))
    return encode_rgba(len(rows[0]), len(rows), bytes(rgba))


class SilhouetteMathTest(unittest.TestCase):
    def test_eight_fixed_views_are_declared(self):
        self.assertEqual(len(VIEWS), 8)
        self.assertEqual(len(set(VIEWS)), 8)

    def test_identical_masks_score_one(self):
        _width, mask = mask_from_png(_mask_png(["##..", ".##.", "...."]))
        self.assertEqual(iou(mask, mask), 1.0)

    def test_disjoint_masks_score_zero(self):
        _w1, first = mask_from_png(_mask_png(["##..", "....", "...."]))
        _w2, second = mask_from_png(_mask_png(["....", "....", "..##"]))
        self.assertEqual(iou(first, second), 0.0)

    def test_half_overlap_scores_one_third(self):
        _w1, first = mask_from_png(_mask_png(["##.."]))
        _w2, second = mask_from_png(_mask_png([".##."]))
        self.assertAlmostEqual(iou(first, second), 1 / 3, places=6)

    def test_compare_reports_minimum_and_mean(self):
        _w, full = mask_from_png(_mask_png(["##"]))
        _w2, half = mask_from_png(_mask_png(["#."]))
        result = compare([full, full], [full, half])
        self.assertEqual(result["per_view"][0], 1.0)
        self.assertAlmostEqual(result["per_view"][1], 0.5, places=6)
        self.assertAlmostEqual(result["minimum"], 0.5, places=6)
        self.assertAlmostEqual(result["mean"], 0.75, places=6)

    def test_compare_rejects_mismatched_view_counts(self):
        _w, full = mask_from_png(_mask_png(["##"]))
        with self.assertRaisesRegex(ValueError, "view count"):
            compare([full], [full, full])


class RenderMasksDegenerateGuardTest(unittest.TestCase):
    """render_masks must refuse degenerate (blank/solid) renders.

    Fix-round-1 finding: previously, TWO renders that both came back blank
    (or both fully solid) would sail through render_masks and then score
    IoU 1.0 in compare() -- a scene-setup regression masquerading as a
    perfect conversion. render_masks now reads the per-view coverage
    silhouette_render.py measures and raises SilhouetteError on any
    degenerate view. These tests exercise that guard directly, without a
    real Blender invocation, by patching run_blender_script to return a
    synthetic report -- so this coverage does not depend on being able to
    reproduce a broken render for real.
    """

    def setUp(self):
        self.config = FactoryConfig.load()
        self.output_dir = self.config.root / "tmp" / "factory" / "tests" / "silhouette"
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _report(self, coverage: list[float]) -> dict:
        renders = [f"view_{index:02d}.png" for index in range(len(coverage))]
        return {
            "ok": True,
            "renders": renders,
            "coverage": coverage,
            "radius": 1.0,
            "centre": [0.0, 0.0, 0.0],
            "error": None,
        }

    def test_raises_when_every_view_is_blank(self):
        report = self._report([0.0] * len(VIEWS))
        with mock.patch.object(silhouette, "run_blender_script", return_value=report):
            with self.assertRaisesRegex(SilhouetteError, "degenerate"):
                render_masks(
                    self.config, Path("source.fbx"), self.output_dir,
                    self.output_dir / "report.json",
                )

    def test_raises_when_every_view_is_solid(self):
        # The case the old iou()-only guard could not catch at all: two
        # fully SOLID masks give intersection == union == every pixel, so
        # the pre-fix union==0 special case never even triggers.
        report = self._report([1.0] * len(VIEWS))
        with mock.patch.object(silhouette, "run_blender_script", return_value=report):
            with self.assertRaisesRegex(SilhouetteError, "degenerate"):
                render_masks(
                    self.config, Path("source.fbx"), self.output_dir,
                    self.output_dir / "report.json",
                )

    def test_raises_when_a_single_view_is_degenerate(self):
        coverage = [0.05] * len(VIEWS)
        coverage[3] = 0.0
        report = self._report(coverage)
        with mock.patch.object(silhouette, "run_blender_script", return_value=report):
            with self.assertRaisesRegex(SilhouetteError, "view 3"):
                render_masks(
                    self.config, Path("source.fbx"), self.output_dir,
                    self.output_dir / "report.json",
                )

    def test_accepts_non_degenerate_coverage(self):
        report = self._report([0.02] * len(VIEWS))
        with mock.patch.object(silhouette, "run_blender_script", return_value=report):
            paths = render_masks(
                self.config, Path("source.fbx"), self.output_dir,
                self.output_dir / "report.json",
            )
        self.assertEqual(len(paths), len(VIEWS))


class _BlenderIntegrationTest(unittest.TestCase):
    """Shared setUp for tests that need a real Blender + the trenchgun fixture."""

    def setUp(self):
        self.config = FactoryConfig.load()
        if discover_blender(self.config) is None:
            self.skipTest("Blender is not available on this host")
        try:
            self.source = trenchgun_fbx()
        except FixtureUnavailable as error:
            self.skipTest(str(error))
        self.work = self.config.root / "tmp" / "factory" / "tests" / "silhouette"
        self.work.mkdir(parents=True, exist_ok=True)

    def _contract(self, temp: Path) -> StyleContract:
        rgba = bytearray()
        for colour in ((20, 18, 16), (104, 82, 56), (132, 138, 130), (188, 192, 186)):
            rgba.extend((*colour, 255))
        (temp / "palette.png").write_bytes(encode_rgba(4, 1, bytes(rgba)))
        path = temp / "contract.json"
        path.write_text(json.dumps(CONTRACT), encoding="utf-8")
        return StyleContract.load(self.config, path)


class SilhouetteRenderTest(_BlenderIntegrationTest):
    def test_renders_one_mask_per_view_with_visible_coverage(self):
        work = self.work
        with tempfile.TemporaryDirectory(dir=work) as temp:
            temp_path = Path(temp)
            renders = render_masks(
                self.config, self.source, temp_path / "views", temp_path / "report.json"
            )
            self.assertEqual(len(renders), len(VIEWS))
            for path in renders:
                _width, mask = mask_from_png(path.read_bytes())
                coverage = sum(mask) / len(mask)
                self.assertGreater(coverage, 0.01, f"{path.name} is essentially empty")
                self.assertLess(coverage, 0.99, f"{path.name} is essentially solid")


class ExportedTriangleCountTest(_BlenderIntegrationTest):
    """Converts Blender's vague export warning into a pass/fail signal.

    A known defect makes retro_pass's intermediate meshes geometrically
    invalid, and Blender's glTF exporter warns the result "may be exported
    wrongly". retro_pass now calls mesh.validate() (_validate_meshes) before
    export and recounts triangles_out when it repairs anything, so both
    sides of the comparison below read the same, post-repair count.
    Comparing the exported GLB's own triangle count (read straight from its
    accessors, independent of Blender) against the triangles_out the
    conversion reported is what catches a regression in that: indices
    referencing geometry that silently vanished on export.
    """

    # This carried @unittest.expectedFailure through Task 9. retro_pass's
    # triangles_out was captured immediately after _decimate and never
    # re-measured, while the decimate collapse left duplicate faces behind --
    # exactly the invalid-mesh condition Blender's own exporter warns about
    # ("may be exported wrongly") -- and glTF export repaired them away on
    # the way out. Measured on the real trenchgun/large-band conversion:
    # triangles_out=2479 against 2470 triangles in the exported GLB, a silent
    # 9-triangle (0.36%) loss. See task-9-report.md for that measurement.
    #
    # retro_pass now validates its meshes before export and recounts after
    # (_validate_meshes), so both sides read 2470 and this stands as a real
    # gate. Do not re-quarantine it: a failure here means geometry is once
    # again vanishing between the measurement Gate 2 thresholds on and the
    # file that ships, which makes the IoU below meaningless rather than low.
    def test_exported_triangle_count_matches_retro_pass_report(self):
        with tempfile.TemporaryDirectory(dir=self.work) as temp:
            temp_path = Path(temp)
            contract = self._contract(temp_path)
            output = temp_path / "converted.glb"
            report = retro_pass(
                self.config, self.source, contract, "large", output,
                temp_path / "retro_report.json",
            )
            inspection = inspect_glb(output)
            self.assertEqual(
                inspection["triangle_count"],
                report["triangles_out"],
                "exported GLB triangle count disagrees with retro_pass's own "
                "triangles_out; the export may have silently dropped or "
                "duplicated geometry",
            )


class SilhouetteComparisonTest(unittest.TestCase):
    """End-to-end: silhouette IoU between the raw trenchgun and its PS1 pass.

    This is the actual measurement Gate 2 will threshold on. The pipeline
    (retro_pass, then render_masks on both the raw source and the
    converted GLB with shared-radius framing, then compare) runs ONCE in
    setUpClass and every test method below reads the shared result --
    three Blender round-trips' worth of cost is paid once, not once per
    assertion.

    Fix-round-1 note: this class used to be a single test method wrapped
    in @unittest.expectedFailure. A reviewer correctly flagged that as
    over-broad: it would silently absorb ANY failure anywhere in
    render_masks -> mask_from_png -> compare, including a regression in
    this task's own code, not just the known retro_pass rotation defect
    it was written to quarantine. It is now split into independently-
    reportable methods -- see each one's docstring for what it guards.

    That rotation defect has since been fixed (export_yup=False in
    retro_pass's main()), so nothing here is quarantined any more: both
    methods are undecorated and both must stay green.
    """

    _temp_dir: tempfile.TemporaryDirectory | None = None
    _result: dict | None = None

    @classmethod
    def setUpClass(cls):
        config = FactoryConfig.load()
        if discover_blender(config) is None:
            raise unittest.SkipTest("Blender is not available on this host")
        try:
            source = trenchgun_fbx()
        except FixtureUnavailable as error:
            raise unittest.SkipTest(str(error))

        work = config.root / "tmp" / "factory" / "tests" / "silhouette"
        work.mkdir(parents=True, exist_ok=True)
        cls._temp_dir = tempfile.TemporaryDirectory(dir=work)
        temp_path = Path(cls._temp_dir.name)

        rgba = bytearray()
        for colour in ((20, 18, 16), (104, 82, 56), (132, 138, 130), (188, 192, 186)):
            rgba.extend((*colour, 255))
        (temp_path / "palette.png").write_bytes(encode_rgba(4, 1, bytes(rgba)))
        contract_path = temp_path / "contract.json"
        contract_path.write_text(json.dumps(CONTRACT), encoding="utf-8")
        contract = StyleContract.load(config, contract_path)

        converted = temp_path / "converted.glb"
        retro_pass(
            config, source, contract, "large", converted,
            temp_path / "retro_report.json",
        )

        raw_report = temp_path / "raw_report.json"
        raw_paths = render_masks(config, source, temp_path / "raw", raw_report)
        # Frame the converted render with the SAME radius the raw render
        # used, so a converted mesh with slightly different bounds is not
        # penalized (or flattered) by a different zoom level. The centre
        # is intentionally NOT shared -- see render_masks' docstring: the
        # pipeline's normalize stage recentres/reorients the mesh, so raw
        # and converted do not occupy the same world-space position even
        # when the shape is unchanged.
        shared_radius = effective_radius(raw_report)
        ps1_paths = render_masks(
            config, converted, temp_path / "ps1", temp_path / "ps1_report.json",
            radius=shared_radius,
        )

        raw_masks = [mask_from_png(path.read_bytes())[1] for path in raw_paths]
        ps1_masks = [mask_from_png(path.read_bytes())[1] for path in ps1_paths]
        cls._result = compare(raw_masks, ps1_masks)

    @classmethod
    def tearDownClass(cls):
        if cls._temp_dir is not None:
            cls._temp_dir.cleanup()

    def test_pipeline_invariants_hold(self):
        """Undecorated on purpose: a regression in THIS task's own code

        must turn this red. None of these invariants depend on retro_pass's
        known rotation defect, so unlike the quality-threshold test below,
        nothing here should ever be expected to fail. If render_masks,
        mask_from_png or compare breaks -- wrong view count, an out-of-range
        score, a shape mismatch between per_view and the coverage lists --
        this is the test that reports it, instead of it being silently
        swallowed by an expectedFailure covering unrelated ground.
        """
        result = self._result
        self.assertIsNotNone(result)
        self.assertEqual(len(result["per_view"]), len(VIEWS))
        self.assertEqual(len(result["raw_coverage"]), len(VIEWS))
        self.assertEqual(len(result["ps1_coverage"]), len(VIEWS))
        for score in result["per_view"]:
            self.assertGreaterEqual(score, 0.0)
            self.assertLessEqual(score, 1.0)
        for coverage in (*result["raw_coverage"], *result["ps1_coverage"]):
            self.assertGreater(coverage, 0.0)
            self.assertLess(coverage, 1.0)
        self.assertEqual(result["minimum"], min(result["per_view"]))
        self.assertAlmostEqual(
            result["mean"], sum(result["per_view"]) / len(result["per_view"])
        )

    # Was @unittest.expectedFailure, quarantining the up-axis
    # double-rotation defect this measurement discovered: retro_pass's
    # _normalize applied a manual -90deg X rotation for up_axis == "Y" AND
    # main() exported with export_yup=True, so Blender's exporter applied
    # its own Z-up-to-Y-up conversion on top. The two compounded and every
    # converted asset shipped ~180deg about X from the authored
    # orientation -- baked into the vertex data, visible to any
    # spec-compliant glTF consumer. Minimum IoU measured 0.03-0.12 across
    # the 8 views (see task-9-report.md).
    #
    # Fixed by exporting with export_yup=False, leaving _normalize's
    # rotation as the single axis conversion -- which also keeps the
    # reported bounds/origin in the same frame the GLB ships in. Minimum
    # IoU is now 0.617, so the decorator is gone and this assertion stands
    # on its own as a real gate.
    #
    # A sibling test, ExportedTriangleCountTest, guarded a SEPARATE,
    # unrelated invalid-geometry defect in _split_by_material/_decimate. It
    # carried @unittest.expectedFailure through Task 9; this commit fixed
    # that defect too (retro_pass now calls _validate_meshes before export)
    # and removed the decorator, so that test is no longer quarantined
    # either. It stayed untouched by THIS fix -- the rotation defect below --
    # they were independent bugs.
    #
    # Deliberately NOT weakened to tolerate a rotation (e.g. by rotating
    # one mask before comparing): doing so would hide exactly this class
    # of ship-breaking regression from Gate 2 (Task 10).
    def test_quality_threshold_is_met(self):
        # Sanity bound, not Gate 2's real threshold (that belongs to
        # Task 10). This only needs to catch a badly broken camera or a
        # grossly wrong conversion; it must not be loosened to paper over
        # a real regression.
        self.assertGreater(
            self._result["minimum"], 0.5,
            f"silhouette IoU per-view: {self._result['per_view']}",
        )


if __name__ == "__main__":
    unittest.main()
