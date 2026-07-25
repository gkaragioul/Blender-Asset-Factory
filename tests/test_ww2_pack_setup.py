import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACK_ROOT = ROOT / "products" / "ww2_lowpoly_frontline_pack"


class WW2PackSetupTest(unittest.TestCase):
    def test_sellable_pack_manifest_exists_with_commercial_metadata(self):
        manifest = json.loads((PACK_ROOT / "pack-manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["schema_version"], 1)
        self.assertEqual(manifest["pack_id"], "ww2_lowpoly_frontline_pack")
        self.assertIn("commercial", manifest["license"]["summary"].lower())
        self.assertEqual(manifest["engine_targets"], ["threejs", "gltf-glb", "blender"])
        self.assertGreaterEqual(len(manifest["planned_assets"]), 12)
        self.assertTrue(all(asset["asset_id"].startswith("ww2_") for asset in manifest["planned_assets"]))
        self.assertTrue(all(asset["triangle_budget"] <= 1200 for asset in manifest["planned_assets"] if asset["type"] == "weapon"))

    def test_storefront_and_buyer_docs_are_present(self):
        required = [
            "README.md",
            "LICENSE.txt",
            "STORE_LISTING.md",
            "PRODUCTION_CHECKLIST.md",
            "TECHNICAL_SPECS.md",
        ]
        for filename in required:
            path = PACK_ROOT / filename
            self.assertTrue(path.is_file(), filename)
            self.assertGreater(len(path.read_text(encoding="utf-8")), 200, filename)

    def test_autonomous_job_contract_is_linux_native(self):
        job = json.loads((ROOT / "specs" / "jobs" / "ww2_lowpoly_frontline_pack.json").read_text(encoding="utf-8"))
        self.assertEqual(job["schema_version"], 1)
        self.assertEqual(job["pack_id"], "ww2_lowpoly_frontline_pack")
        self.assertEqual(job["automation"], "ai_only")
        self.assertEqual(job["platform"], "linux-native")
        self.assertEqual(job["output_root"], "products/ww2_lowpoly_frontline_pack")
        self.assertGreaterEqual(job["quality_gates"]["minimum_visual_score"], 0.82)

    def test_style_profile_encodes_sale_quality_bar(self):
        profile_root = ROOT / "profiles" / "ps1_ww2_frontline"
        profile = json.loads((profile_root / "profile.json").read_text(encoding="utf-8"))
        materials = json.loads((profile_root / "materials.json").read_text(encoding="utf-8"))
        evaluations = json.loads((profile_root / "evaluations.json").read_text(encoding="utf-8"))
        self.assertEqual(profile["profile_id"], "ps1_ww2_frontline")
        self.assertTrue(profile["legal_style_bounds"]["fictionalized_designs"])
        self.assertIn("aged_walnut", materials["materials"])
        self.assertIn("blued_steel", materials["materials"])
        self.assertGreaterEqual(evaluations["visual_scores"]["minimum_total"], 0.82)


if __name__ == "__main__":
    unittest.main()
