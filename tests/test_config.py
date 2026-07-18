import json
import tempfile
import unittest
from pathlib import Path

from factory.config import ConfigurationError, FactoryConfig


class FactoryConfigTest(unittest.TestCase):
    def test_loads_canonical_roots(self):
        config = FactoryConfig.load()
        self.assertEqual(config.root, Path(__file__).resolve().parents[1])
        self.assertEqual(config.model_root, Path(r"G:\LLMs"))
        self.assertEqual(config.bridge_url, "http://127.0.0.1:9876")

    def test_rejects_owned_write_outside_g(self):
        config = FactoryConfig.load()
        with self.assertRaisesRegex(ConfigurationError, "drive G"):
            config.require_owned_path(Path(r"C:\temp\forbidden"))

    def test_rejects_configuration_root_mismatch(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "config.json"
            path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "root": "C:/wrong",
                        "model_root": "G:/LLMs",
                        "tooling_root": "G:/safe",
                        "reports_root": "G:/safe/reports",
                        "bridge_url": "http://127.0.0.1:9876",
                        "blender_candidates": [],
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaises(ConfigurationError):
                FactoryConfig.load(path)


if __name__ == "__main__":
    unittest.main()
