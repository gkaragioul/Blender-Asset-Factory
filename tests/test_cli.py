import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class FactoryCliTest(unittest.TestCase):
    def test_version_returns_result_envelope(self):
        completed = subprocess.run(
            [sys.executable, "-m", "factory", "version", "--json"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        result = json.loads(completed.stdout)
        self.assertEqual(result["schema_version"], 1)
        self.assertEqual(result["command"], "version")
        self.assertTrue(result["ok"])
        self.assertEqual(result["data"]["version"], "0.1.0")
        self.assertEqual(result["errors"], [])

    def test_unknown_command_is_structured_failure(self):
        completed = subprocess.run(
            [sys.executable, "-m", "factory", "missing", "--json"],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(completed.returncode, 0)
        result = json.loads(completed.stdout)
        self.assertFalse(result["ok"])
        self.assertEqual(result["errors"][0]["code"], "unknown_command")


if __name__ == "__main__":
    unittest.main()
