import json
import tempfile
import unittest
from pathlib import Path

from factory.blender import discover_blender
from factory.config import FactoryConfig
from factory.png import encode_rgba
from factory.retro import RetroError, canonical_glb_bytes, retro_pass
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


class RetroPassTest(unittest.TestCase):
    def setUp(self):
        self.config = FactoryConfig.load()
        if discover_blender(self.config) is None:
            self.skipTest("Blender is not available on this host")
        try:
            self.source = trenchgun_fbx()
        except FixtureUnavailable as error:
            self.skipTest(str(error))
        self.work = self.config.root / "tmp" / "factory" / "tests" / "retro"
        self.work.mkdir(parents=True, exist_ok=True)

    def _contract(self, temp: Path) -> StyleContract:
        rgba = bytearray()
        for colour in ((20, 18, 16), (104, 82, 56), (132, 138, 130), (188, 192, 186)):
            rgba.extend((*colour, 255))
        (temp / "palette.png").write_bytes(encode_rgba(4, 1, bytes(rgba)))
        path = temp / "contract.json"
        path.write_text(json.dumps(CONTRACT), encoding="utf-8")
        return StyleContract.load(self.config, path)

    def test_produces_byte_identical_output_for_identical_inputs(self):
        with tempfile.TemporaryDirectory(dir=self.work) as temp:
            temp_path = Path(temp)
            contract = self._contract(temp_path)
            first = temp_path / "first.glb"
            second = temp_path / "second.glb"
            retro_pass(
                self.config, self.source, contract, "large", first,
                temp_path / "first.json",
            )
            retro_pass(
                self.config, self.source, contract, "large", second,
                temp_path / "second.json",
            )
            self.assertEqual(canonical_glb_bytes(first), canonical_glb_bytes(second))

    def test_raises_on_blender_side_failure(self):
        with tempfile.TemporaryDirectory(dir=self.work) as temp:
            temp_path = Path(temp)
            contract = self._contract(temp_path)
            with self.assertRaisesRegex(RetroError, "colossal"):
                retro_pass(
                    self.config, self.source, contract, "colossal",
                    temp_path / "out.glb", temp_path / "report.json",
                )


if __name__ == "__main__":
    unittest.main()
