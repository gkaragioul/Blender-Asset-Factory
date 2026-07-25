import unittest

from factory.c09_spec import build_c09_spec


class C09GeometrySpecTests(unittest.TestCase):
    def test_side_by_side_barrels_are_horizontal_and_equal(self):
        spec = build_c09_spec()
        barrels = spec["barrels"]
        self.assertEqual(len(barrels), 2)
        self.assertEqual(barrels[0]["center_z_m"], barrels[1]["center_z_m"])
        self.assertAlmostEqual(
            barrels[0]["center_y_m"], -barrels[1]["center_y_m"]
        )
        self.assertEqual(barrels[0]["length_m"], barrels[1]["length_m"])
        self.assertLess(barrels[0]["bore_radius_m"], barrels[0]["outer_radius_m"])

    def test_contract_has_required_connected_and_moving_parts(self):
        spec = build_c09_spec()
        required = {
            "stock",
            "receiver",
            "barrel_left",
            "barrel_right",
            "rib",
            "fore_end",
            "hinge",
            "top_lever",
            "trigger_front",
            "trigger_rear",
            "trigger_guard",
            "bead_sight",
        }
        self.assertTrue(required.issubset(set(spec["semantic_parts"])))
        self.assertEqual(spec["moving_groups"]["break_action"], [
            "barrel_left", "barrel_right", "rib", "fore_end"
        ])
        self.assertGreater(spec["dimensions_m"]["overall_length"], 1.0)
        self.assertLess(spec["dimensions_m"]["overall_length"], 1.25)


if __name__ == "__main__":
    unittest.main()
