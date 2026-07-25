import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / "scripts" / "generate_reference_derived_shotgun_v1.py"


class ReferenceDerivedShotgunV1ContractTest(unittest.TestCase):
    def test_generator_uses_both_reference_sources_and_required_build_stages(self):
        source = GENERATOR.read_text(encoding="utf-8")
        tree = ast.parse(source)
        functions = {node.name for node in tree.body if isinstance(node, ast.FunctionDef)}
        self.assertTrue(
            {
                "import_structural_source",
                "reduce_source_parts",
                "make_full_stock",
                "apply_ps1_materials",
                "render_qa_views",
                "export_asset",
            }.issubset(functions)
        )
        self.assertIn("shotgun-fbx/source/shotgun.fbx", source)
        self.assertIn("m1897-trenchgun", source)

    def test_generator_targets_ps1_runtime_contract(self):
        source = GENERATOR.read_text(encoding="utf-8")
        self.assertIn('OUTPUT_RELATIVE = "products/ww2_lowpoly_frontline_pack/source-derived-shotgun-v1"', source)
        self.assertIn("TARGET_TRIANGLES = 2400", source)
        self.assertIn("TEXTURE_SIZE = 256", source)
        self.assertIn('texture.interpolation = "Closest"', source)
        self.assertIn("polygon.use_smooth = False", source)

    def test_generator_records_unresolved_external_license_evidence(self):
        source = GENERATOR.read_text(encoding="utf-8")
        self.assertIn('"license_status": "pending_source_page_evidence"', source)
        self.assertIn("fda5628431fa3a1993b4072d24bee9f85280f2f1c3fe3ab81f7de740330eb285", source)
        self.assertIn("57d22c8ba7085b1b20367ebf94dd14be854072df0dd26bea1549ace81f946d6f", source)


if __name__ == "__main__":
    unittest.main()
