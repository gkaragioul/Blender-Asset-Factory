import json
import tempfile
import unittest
from pathlib import Path

from factory.config import FactoryConfig
from factory.style_contract import StyleContract, StyleContractError
from tests.temp_paths import temporary_root

CONTRACT = {
    "schema_version": 1,
    "palette": "palettes/ww2_field_48.png",
    "texture_size": 256,
    "filtering": "nearest",
    "polycount_bands": {"small": 400, "medium": 1000, "large": 2500},
    "grid_unit": 0.5,
    "up_axis": "Y",
    "drop_maps": ["normal", "roughness", "metallic"],
    "vertex_light_bake": True,
}


class StyleContractTest(unittest.TestCase):
    def setUp(self):
        self.config = FactoryConfig.load()

    def _write(self, temp: Path, overrides: dict | None = None) -> Path:
        data = dict(CONTRACT)
        data.update(overrides or {})
        palette = temp / "palettes" / "ww2_field_48.png"
        palette.parent.mkdir(parents=True, exist_ok=True)
        palette.write_bytes(b"\x89PNG\r\n\x1a\n")
        path = temp / "contract.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def test_resolves_band_for_role(self):
        with tempfile.TemporaryDirectory(dir=temporary_root()) as temp:
            contract = StyleContract.load(self.config, self._write(Path(temp)))
            self.assertEqual(contract.band_for("small"), 400)
            self.assertEqual(contract.band_for("medium"), 1000)
            self.assertEqual(contract.band_for("large"), 2500)

    def test_rejects_unknown_role(self):
        with tempfile.TemporaryDirectory(dir=temporary_root()) as temp:
            contract = StyleContract.load(self.config, self._write(Path(temp)))
            with self.assertRaisesRegex(StyleContractError, "unknown role"):
                contract.band_for("gigantic")

    def test_rejects_non_nearest_filtering(self):
        with tempfile.TemporaryDirectory(dir=temporary_root()) as temp:
            path = self._write(Path(temp), {"filtering": "linear"})
            with self.assertRaisesRegex(StyleContractError, "filtering"):
                StyleContract.load(self.config, path)

    def test_rejects_missing_palette_file(self):
        with tempfile.TemporaryDirectory(dir=temporary_root()) as temp:
            path = self._write(Path(temp), {"palette": "palettes/absent.png"})
            with self.assertRaisesRegex(StyleContractError, "palette"):
                StyleContract.load(self.config, path)

    def test_digest_is_stable_and_sensitive_to_content(self):
        with tempfile.TemporaryDirectory(dir=temporary_root()) as temp:
            temp_path = Path(temp)
            first = StyleContract.load(self.config, self._write(temp_path))
            second = StyleContract.load(self.config, self._write(temp_path))
            self.assertEqual(first.digest(), second.digest())
            self.assertEqual(len(first.digest()), 64)
            changed = StyleContract.load(
                self.config, self._write(temp_path, {"texture_size": 128})
            )
            self.assertNotEqual(first.digest(), changed.digest())


if __name__ == "__main__":
    unittest.main()
