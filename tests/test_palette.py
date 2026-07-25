import tempfile
import unittest
from pathlib import Path

from factory.palette import PaletteError, conformance, load_palette, nearest
from factory.png import encode_rgba
from tests.temp_paths import temporary_root

RED = (255, 0, 0)
GREEN = (0, 255, 0)
BLUE = (0, 0, 255)


def _png(colours: list[tuple[int, int, int]]) -> bytes:
    rgba = bytearray()
    for colour in colours:
        rgba.extend((*colour, 255))
    return encode_rgba(len(colours), 1, bytes(rgba))


class PaletteTest(unittest.TestCase):
    def test_loads_unique_colours_in_stable_order(self):
        with tempfile.TemporaryDirectory(dir=temporary_root()) as temp:
            path = Path(temp) / "palette.png"
            path.write_bytes(_png([RED, GREEN, BLUE, RED]))
            self.assertEqual(load_palette(path), (BLUE, GREEN, RED))

    def test_rejects_empty_palette(self):
        with tempfile.TemporaryDirectory(dir=temporary_root()) as temp:
            path = Path(temp) / "palette.png"
            path.write_bytes(encode_rgba(1, 1, bytes((0, 0, 0, 0))))
            with self.assertRaisesRegex(PaletteError, "opaque"):
                load_palette(path)

    def test_nearest_picks_closest_palette_colour(self):
        palette = (RED, GREEN, BLUE)
        self.assertEqual(nearest((250, 10, 10), palette), RED)
        self.assertEqual(nearest((10, 10, 240), palette), BLUE)

    def test_conformance_passes_for_in_palette_image(self):
        palette = (RED, GREEN, BLUE)
        report = conformance(_png([RED, GREEN, BLUE]), palette)
        self.assertTrue(report["ok"])
        self.assertEqual(report["foreign_pixels"], 0)
        self.assertEqual(report["pixels"], 3)

    def test_conformance_reports_foreign_colours(self):
        palette = (RED, GREEN)
        report = conformance(_png([RED, (7, 7, 7), (7, 7, 7)]), palette)
        self.assertFalse(report["ok"])
        self.assertEqual(report["foreign_pixels"], 2)
        self.assertEqual(report["foreign_colours"], [[7, 7, 7]])


if __name__ == "__main__":
    unittest.main()
