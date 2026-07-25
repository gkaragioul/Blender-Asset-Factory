import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / "scripts" / "generate_ww2_pack_v2.py"


class WW2PolishPass2GeneratorTest(unittest.TestCase):
    def test_polish_generator_outputs_to_separate_pass2_folder(self):
        source = GENERATOR.read_text(encoding="utf-8")
        self.assertIn("products/ww2_lowpoly_frontline_pack/polish-pass-2", source)
        self.assertNotIn("products/ww2_lowpoly_frontline_pack/generated\"", source)

    def test_polish_generator_defines_texture_atlas_and_visual_score_contract(self):
        source = GENERATOR.read_text(encoding="utf-8")
        tree = ast.parse(source)
        function_names = {node.name for node in tree.body if isinstance(node, ast.FunctionDef)}
        self.assertIn("create_pixel_atlas", function_names)
        self.assertIn("score_asset_candidate", function_names)
        self.assertIn("make_lumpy_bag", function_names)
        self.assertIn("mesh_prism", function_names)
        self.assertIn('"visual_score"', source)
        self.assertIn('"texture_atlases"', source)
        self.assertIn('"polish_pass_2"', source)


if __name__ == "__main__":
    unittest.main()
