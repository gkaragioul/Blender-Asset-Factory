import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / "scripts" / "generate_ps1_over_under_shotgun_v1.py"
TEXTURE_TOOL = ROOT / "scripts" / "prepare_ps1_over_under_texture.py"


class PS1OverUnderShotgunContractTest(unittest.TestCase):
    def test_final_generator_has_ps1_budget_lods_and_collision(self):
        source = GENERATOR.read_text(encoding="utf-8")
        tree = ast.parse(source)
        functions = {node.name for node in tree.body if isinstance(node, ast.FunctionDef)}
        self.assertTrue({"reduce_ps1_source", "make_lod1", "make_collision_proxy", "export_final_asset"}.issubset(functions))
        self.assertIn("TARGET_TRIANGLES = 2200", source)
        self.assertIn("LOD1_TARGET_TRIANGLES = 900", source)
        self.assertIn("TEXTURE_SIZE = 128", source)
        self.assertIn("COLLISION_SHOTGUN", source)
        self.assertIn("PS1_LOD1", source)

    def test_final_materials_are_flat_nearest_and_non_pbr(self):
        source = GENERATOR.read_text(encoding="utf-8")
        self.assertIn('texture.interpolation = "Closest"', source)
        self.assertIn("polygon.use_smooth = False", source)
        self.assertIn('material["ps1_unlit"] = True', source)
        self.assertNotIn('inputs["Metallic"]', source)

    def test_texture_tool_enforces_small_palette(self):
        source = TEXTURE_TOOL.read_text(encoding="utf-8")
        self.assertIn("TEXTURE_SIZE = 128", source)
        self.assertIn("COLORS = 24", source)
        self.assertIn("Image.Resampling.NEAREST", source)
        self.assertIn("Image.Dither.FLOYDSTEINBERG", source)


if __name__ == "__main__":
    unittest.main()
