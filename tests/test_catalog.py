import json
import tempfile
import unittest
from pathlib import Path

from factory.catalog import Catalog, CatalogError
from factory.config import FactoryConfig
from factory.style_contract import StyleContract
from tests.temp_paths import temporary_root

CONTRACT = {
    "schema_version": 1,
    "palette": "palettes/p.png",
    "texture_size": 256,
    "filtering": "nearest",
    "polycount_bands": {"small": 400, "medium": 1000, "large": 2500},
    "grid_unit": 0.5,
    "up_axis": "Y",
    "drop_maps": ["normal", "roughness", "metallic"],
    "vertex_light_bake": True,
}


class CatalogTest(unittest.TestCase):
    def setUp(self):
        self.config = FactoryConfig.load()

    def _contract(self, temp: Path) -> StyleContract:
        palette = temp / "palettes" / "p.png"
        palette.parent.mkdir(parents=True, exist_ok=True)
        palette.write_bytes(b"\x89PNG\r\n\x1a\n")
        path = temp / "contract.json"
        path.write_text(json.dumps(CONTRACT), encoding="utf-8")
        return StyleContract.load(self.config, path)

    def _write(self, temp: Path, assets: list[dict]) -> Path:
        path = temp / "catalog.json"
        path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "pack_id": "ww2_diorama_kit_01",
                    "style_contract": "contract.json",
                    "max_generations": 200,
                    "max_rerolls": 3,
                    "assets": assets,
                }
            ),
            encoding="utf-8",
        )
        return path

    def test_loads_lane_a_and_lane_b_entries(self):
        with tempfile.TemporaryDirectory(dir=temporary_root()) as temp:
            temp_path = Path(temp)
            contract = self._contract(temp_path)
            path = self._write(
                temp_path,
                [
                    {
                        "id": "ammo_crate_closed",
                        "lane": "A",
                        "role": "small",
                        "prompt": "wooden military ammunition crate closed lid",
                    },
                    {
                        "id": "stahlhelm",
                        "lane": "B",
                        "role": "medium",
                        "reference_brief": "German M35 Stahlhelm, three-quarter view",
                    },
                ],
            )
            catalog = Catalog.load(self.config, path, contract)
            self.assertEqual(catalog.pack_id, "ww2_diorama_kit_01")
            self.assertEqual(catalog.max_rerolls, 3)
            self.assertEqual(len(catalog.entries), 2)
            self.assertEqual(catalog.entries[0].prompt.split()[0], "wooden")
            self.assertIsNone(catalog.entries[1].prompt)

    def test_rejects_lane_a_without_prompt(self):
        with tempfile.TemporaryDirectory(dir=temporary_root()) as temp:
            temp_path = Path(temp)
            contract = self._contract(temp_path)
            path = self._write(
                temp_path,
                [{"id": "crate", "lane": "A", "role": "small",
                  "reference_brief": "wrong field for lane A"}],
            )
            with self.assertRaisesRegex(CatalogError, "lane A"):
                Catalog.load(self.config, path, contract)

    def test_rejects_lane_b_without_reference_brief(self):
        with tempfile.TemporaryDirectory(dir=temporary_root()) as temp:
            temp_path = Path(temp)
            contract = self._contract(temp_path)
            path = self._write(
                temp_path,
                [{"id": "helmet", "lane": "B", "role": "medium",
                  "prompt": "wrong field for lane B"}],
            )
            with self.assertRaisesRegex(CatalogError, "lane B"):
                Catalog.load(self.config, path, contract)

    def test_rejects_role_absent_from_contract(self):
        with tempfile.TemporaryDirectory(dir=temporary_root()) as temp:
            temp_path = Path(temp)
            contract = self._contract(temp_path)
            path = self._write(
                temp_path,
                [{"id": "crate", "lane": "A", "role": "colossal", "prompt": "a crate"}],
            )
            with self.assertRaisesRegex(CatalogError, "colossal"):
                Catalog.load(self.config, path, contract)

    def test_rejects_duplicate_asset_ids(self):
        with tempfile.TemporaryDirectory(dir=temporary_root()) as temp:
            temp_path = Path(temp)
            contract = self._contract(temp_path)
            path = self._write(
                temp_path,
                [
                    {"id": "crate", "lane": "A", "role": "small", "prompt": "a crate"},
                    {"id": "crate", "lane": "A", "role": "small", "prompt": "a crate"},
                ],
            )
            with self.assertRaisesRegex(CatalogError, "duplicate"):
                Catalog.load(self.config, path, contract)


if __name__ == "__main__":
    unittest.main()
