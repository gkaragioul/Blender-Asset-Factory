import ast
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / "scripts" / "generate_ww2_pack.py"
JOB = ROOT / "specs" / "jobs" / "ww2_lowpoly_frontline_pack.json"


class WW2BatchGeneratorTest(unittest.TestCase):
    def test_generator_defines_every_first_batch_asset(self):
        job = json.loads(JOB.read_text(encoding="utf-8"))
        source = GENERATOR.read_text(encoding="utf-8")
        tree = ast.parse(source)
        definitions = next(
            node for node in tree.body
            if isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == "ASSET_DEFINITIONS" for target in node.targets)
        )
        asset_definitions = ast.literal_eval(definitions.value)
        self.assertEqual(sorted(job["first_batch"]), sorted(asset_definitions))

    def test_generator_uses_linux_native_relative_output_root(self):
        source = GENERATOR.read_text(encoding="utf-8")
        self.assertIn("products/ww2_lowpoly_frontline_pack/generated", source)
        self.assertNotIn("G:\\", source)
        self.assertNotIn(".exe", source)


if __name__ == "__main__":
    unittest.main()
