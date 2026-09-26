import unittest
from pathlib import Path

from factory.placement import PlacementError, check_measurements, resolve_expectations


ROOT = Path(__file__).resolve().parents[1]


def _measured(minimum=(-0.5, 0.0, -1.0), maximum=(0.5, 2.0, 1.0), triangles=800, draw_calls=3):
    return {
        "bounds": {"min": list(minimum), "max": list(maximum)},
        "triangle_count": triangles,
        "draw_calls": draw_calls,
    }


class CheckMeasurementsTest(unittest.TestCase):
    def test_grounded_centred_in_budget_asset_passes(self):
        result = check_measurements(
            _measured(),
            {"triangles": [500, 1200], "max_draw_calls": 4, "dimensions": {"width": 1.0, "height": 2.0, "length": 2.0}},
        )
        self.assertTrue(result["passed"], result)
        self.assertEqual(result["failures"], [])
        self.assertEqual(result["details"]["size"], {"width": 1.0, "height": 2.0, "length": 2.0})

    def test_empty_asset_fails_without_any_expectations(self):
        # An upper bound is satisfied by zero, so "nothing" must be rejected explicitly.
        result = check_measurements(_measured(triangles=0, draw_calls=0), {})
        self.assertFalse(result["passed"])
        self.assertIn("no_geometry", result["failures"])
        self.assertIn("no_draw_calls", result["failures"])

    def test_floating_and_sinking_assets_are_not_grounded(self):
        for low in (0.02, -0.02):
            with self.subTest(min_y=low):
                result = check_measurements(_measured(minimum=(-0.5, low, -1.0)), {})
                self.assertIn("not_grounded", result["failures"])

    def test_float_noise_at_ground_is_tolerated(self):
        self.assertTrue(check_measurements(_measured(minimum=(-0.5, 1e-7, -1.0)), {})["passed"])

    def test_off_centre_footprint_fails(self):
        result = check_measurements(_measured(minimum=(-0.3, 0.0, -1.0), maximum=(0.7, 2.0, 1.0)), {})
        self.assertIn("not_centred", result["failures"])
        self.assertAlmostEqual(result["details"]["centre_offset"]["x"], 0.2)

    def test_centring_can_be_disabled_for_assets_with_deliberate_pivots(self):
        result = check_measurements(_measured(minimum=(-0.3, 0.0, -1.0), maximum=(0.7, 2.0, 1.0)), {"centre_tolerance": None})
        self.assertTrue(result["passed"], result)

    def test_triangle_budget_has_both_bounds(self):
        self.assertIn("triangles_above_max", check_measurements(_measured(triangles=1300), {"triangles": [500, 1200]})["failures"])
        self.assertIn("triangles_below_min", check_measurements(_measured(triangles=40), {"triangles": [500, 1200]})["failures"])

    def test_draw_call_ceiling(self):
        self.assertIn("draw_calls_above_max", check_measurements(_measured(draw_calls=9), {"max_draw_calls": 4})["failures"])

    def test_real_world_dimensions_use_relative_tolerance(self):
        result = check_measurements(_measured(), {"dimensions": {"width": 0.8, "length": 2.02}, "dimension_tolerance": 0.05})
        self.assertIn("width_out_of_range", result["failures"])
        self.assertNotIn("length_out_of_range", result["failures"])

    def test_unknown_dimension_axis_is_rejected(self):
        with self.assertRaisesRegex(PlacementError, "unknown dimension"):
            check_measurements(_measured(), {"dimensions": {"depth": 1.0}})

    def test_missing_bounds_is_a_failure_not_a_pass(self):
        result = check_measurements({"triangle_count": 10, "draw_calls": 1}, {})
        self.assertEqual(result["failures"], ["bounds_missing"])


class ResolveExpectationsTest(unittest.TestCase):
    def test_profile_category_supplies_triangle_band_and_placement_defaults(self):
        resolved = resolve_expectations(ROOT, {"profile": "ps1_ww2_frontline", "category": "weapon"})
        self.assertEqual(resolved["triangles"], [500, 1200])
        self.assertEqual(resolved["ground_tolerance"], 0.0005)
        self.assertEqual(resolved["centre_tolerance"], 0.005)

    def test_explicit_values_override_profile(self):
        resolved = resolve_expectations(ROOT, {"profile": "ps1_ww2_frontline", "category": "weapon", "triangles": [1, 50]})
        self.assertEqual(resolved["triangles"], [1, 50])

    def test_unknown_category_is_rejected(self):
        with self.assertRaisesRegex(PlacementError, "no triangle band"):
            resolve_expectations(ROOT, {"profile": "ps1_ww2_frontline", "category": "spaceship"})

    def test_profile_id_cannot_escape_profiles_folder(self):
        with self.assertRaisesRegex(PlacementError, "profile"):
            resolve_expectations(ROOT, {"profile": "../factory", "category": "weapon"})


if __name__ == "__main__":
    unittest.main()
