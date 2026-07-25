import json
import tempfile
import unittest
from pathlib import Path

from factory.blender import discover_blender
from factory.catalog import Catalog
from factory.config import FactoryConfig
from factory.pack import build_pack
from factory.png import encode_rgba
from factory.style_contract import StyleContract
from tests.fixtures import FixtureUnavailable, trenchgun_fbx

CONTRACT = {
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


class PackBuildTest(unittest.TestCase):
    def setUp(self):
        self.config = FactoryConfig.load()
        if discover_blender(self.config) is None:
            self.skipTest("Blender is not available on this host")
        try:
            self.source = trenchgun_fbx()
        except FixtureUnavailable as error:
            self.skipTest(str(error))
        self.work = self.config.root / "tmp" / "factory" / "tests" / "pack"
        self.work.mkdir(parents=True, exist_ok=True)

    def _catalog(self, temp: Path, assets: list[dict]):
        rgba = bytearray()
        for colour in ((20, 18, 16), (104, 82, 56), (132, 138, 130), (188, 192, 186)):
            rgba.extend((*colour, 255))
        (temp / "palette.png").write_bytes(encode_rgba(4, 1, bytes(rgba)))
        contract_path = temp / "contract.json"
        contract_path.write_text(json.dumps(CONTRACT), encoding="utf-8")
        contract = StyleContract.load(self.config, contract_path)
        catalog_path = temp / "catalog.json"
        catalog_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "pack_id": "test_kit",
                    "style_contract": "contract.json",
                    "max_generations": 10,
                    "max_rerolls": 3,
                    "assets": assets,
                }
            ),
            encoding="utf-8",
        )
        return Catalog.load(self.config, catalog_path, contract), contract

    def test_builds_every_entry_and_reports_verdicts(self):
        with tempfile.TemporaryDirectory(dir=self.work) as temp:
            temp_path = Path(temp)
            catalog, contract = self._catalog(
                temp_path,
                [{"id": "hero", "lane": "A", "role": "large", "prompt": "a shotgun"}],
            )
            report = build_pack(
                self.config, catalog, contract,
                {"hero": self.source},
                temp_path / "out",
                validate=False,
            )
            self.assertEqual(report["pack_id"], "test_kit")
            self.assertEqual(len(report["assets"]), 1)
            entry = report["assets"][0]
            self.assertEqual(entry["id"], "hero")
            self.assertIn(entry["verdict"], ("pass", "flag", "reject"))
            self.assertIn("silhouette", entry)
            self.assertIn("gate1", entry)

    def test_missing_source_is_recorded_without_aborting_the_run(self):
        with tempfile.TemporaryDirectory(dir=self.work) as temp:
            temp_path = Path(temp)
            catalog, contract = self._catalog(
                temp_path,
                [
                    {"id": "hero", "lane": "A", "role": "large", "prompt": "a shotgun"},
                    {"id": "absent", "lane": "A", "role": "small", "prompt": "nothing"},
                ],
            )
            report = build_pack(
                self.config, catalog, contract,
                {"hero": self.source},
                temp_path / "out",
                validate=False,
            )
            self.assertEqual(len(report["assets"]), 2)
            failed = next(item for item in report["assets"] if item["id"] == "absent")
            self.assertEqual(failed["verdict"], "reject")
            self.assertIn("no source", failed["error"])
            succeeded = next(item for item in report["assets"] if item["id"] == "hero")
            self.assertIsNone(succeeded["error"])
            self.assertFalse(report["ok"])

    def test_writes_a_run_report_to_disk(self):
        with tempfile.TemporaryDirectory(dir=self.work) as temp:
            temp_path = Path(temp)
            catalog, contract = self._catalog(
                temp_path,
                [{"id": "hero", "lane": "A", "role": "large", "prompt": "a shotgun"}],
            )
            report = build_pack(
                self.config, catalog, contract,
                {"hero": self.source},
                temp_path / "out",
                validate=False,
            )
            written = Path(report["report_path"])
            self.assertTrue(written.is_file())
            self.assertEqual(
                json.loads(written.read_text(encoding="utf-8"))["pack_id"], "test_kit"
            )


if __name__ == "__main__":
    unittest.main()
