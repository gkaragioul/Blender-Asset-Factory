import json
import tempfile
import unittest
from pathlib import Path

from factory.blender import discover_blender
from factory.cli import run
from factory.config import FactoryConfig
from factory.png import encode_rgba
from tests.fixtures import FixtureUnavailable, trenchgun_fbx


class CliPackTest(unittest.TestCase):
    def setUp(self):
        self.config = FactoryConfig.load()
        if discover_blender(self.config) is None:
            self.skipTest("Blender is not available on this host")
        try:
            self.source = trenchgun_fbx()
        except FixtureUnavailable as error:
            self.skipTest(str(error))
        self.work = self.config.root / "tmp" / "factory" / "tests" / "cli-pack"
        self.work.mkdir(parents=True, exist_ok=True)

    def test_pack_command_returns_an_envelope_with_counts(self):
        with tempfile.TemporaryDirectory(dir=self.work) as temp:
            temp_path = Path(temp)
            rgba = bytearray()
            for colour in ((20, 18, 16), (104, 82, 56), (188, 192, 186)):
                rgba.extend((*colour, 255))
            (temp_path / "palette.png").write_bytes(encode_rgba(3, 1, bytes(rgba)))
            (temp_path / "contract.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "palette": "palette.png",
                        "texture_size": 256,
                        "filtering": "nearest",
                        "polycount_bands": {"small": 400, "medium": 1000, "large": 2500},
                        "grid_unit": 0.5,
                        "up_axis": "Y",
                        "drop_maps": ["normal", "roughness", "metallic"],
                        "vertex_light_bake": True,
                    }
                ),
                encoding="utf-8",
            )
            (temp_path / "catalog.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "pack_id": "cli_kit",
                        "style_contract": "contract.json",
                        "max_generations": 10,
                        "max_rerolls": 3,
                        "assets": [
                            {"id": "hero", "lane": "A", "role": "large",
                             "prompt": "a shotgun"}
                        ],
                    }
                ),
                encoding="utf-8",
            )
            (temp_path / "sources.json").write_text(
                json.dumps({"hero": str(self.source)}), encoding="utf-8"
            )
            code, payload, _ = run(
                [
                    "pack",
                    "--catalog", str(temp_path / "catalog.json"),
                    "--sources", str(temp_path / "sources.json"),
                    "--out", str(temp_path / "out"),
                    "--skip-validate",
                ]
            )
            self.assertEqual(code, 0, payload)
            self.assertEqual(payload["data"]["pack_id"], "cli_kit")
            self.assertIn("counts", payload["data"])

    def test_pack_command_reports_a_missing_catalog(self):
        code, payload, _ = run(
            ["pack", "--catalog", "absent.json", "--sources", "absent.json",
             "--out", "out"]
        )
        self.assertEqual(code, 1)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["errors"][0]["type"], "FileNotFoundError")


if __name__ == "__main__":
    unittest.main()
