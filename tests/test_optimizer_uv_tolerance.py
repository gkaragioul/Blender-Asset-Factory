import unittest

from factory.optimizer import _uv_drift


class OptimizerUvToleranceTest(unittest.TestCase):
    def test_pixel_atlas_optimization_allows_texcoord_count_change_when_bounds_match(self):
        source = {"texcoord_bounds": {"0": {"min": [0.0, 0.0], "max": [1.0, 1.0], "count": 492}}}
        derivative = {"texcoord_bounds": {"0": {"min": [0.0, 0.0], "max": [1.0, 1.0], "count": 444}}}
        self.assertEqual(_uv_drift(source, derivative, required=True), 0.0)


if __name__ == "__main__":
    unittest.main()
