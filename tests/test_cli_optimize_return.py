import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "factory" / "cli.py"


class CliOptimizeReturnTest(unittest.TestCase):
    def test_optimize_handler_returns_envelope(self):
        source = CLI.read_text(encoding="utf-8")
        tree = ast.parse(source)
        optimize = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "_optimize")
        self.assertTrue(any(isinstance(node, ast.Return) for node in ast.walk(optimize)))


if __name__ == "__main__":
    unittest.main()
