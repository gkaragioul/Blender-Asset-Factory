import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / "scripts" / "generate_double_barrel_shotgun_v3.py"


class DoubleBarrelShotgunV3ContractTest(unittest.TestCase):
    def test_generator_is_clean_sheet_and_has_required_semantic_parts(self):
        source = GENERATOR.read_text(encoding="utf-8")
        tree = ast.parse(source)
        functions = {node.name for node in tree.body if isinstance(node, ast.FunctionDef)}
        self.assertTrue({"extruded_profile", "create_barrel", "create_trigger_guard", "build_shotgun", "export_asset"}.issubset(functions))
        for part in (
            "Buttstock",
            "Pistol_Grip_Wrist",
            "Break_Action_Receiver",
            "Left_Barrel",
            "Right_Barrel",
            "Top_Rib",
            "Fore_End",
            "Trigger_Guard",
            "Front_Trigger",
            "Rear_Trigger",
            "Front_Bead_Sight",
        ):
            self.assertIn(part, source)

    def test_generator_writes_to_new_clean_sheet_folder(self):
        source = GENERATOR.read_text(encoding="utf-8")
        self.assertIn("clean-sheet-shotgun-v3", source)
        self.assertNotIn("polish-pass-2", source)
        self.assertNotIn("create_pixel_atlas", source)
    def test_generator_uses_blender_4_agx_look(self):
        source = GENERATOR.read_text(encoding="utf-8")
        self.assertIn('"AgX - Medium High Contrast"', source)
    def test_generator_emits_multiple_visual_qa_views(self):
        source = GENERATOR.read_text(encoding="utf-8")
        self.assertIn("preview_side", source)
        self.assertIn("preview_muzzle", source)


if __name__ == "__main__":
    unittest.main()
