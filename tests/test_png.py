import binascii
import struct
import unittest
import zlib

from factory.png import PngError, decode_rgba, encode_rgba

_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _chunk(kind: bytes, payload: bytes) -> bytes:
    return (
        struct.pack(">I", len(payload))
        + kind
        + payload
        + struct.pack(">I", binascii.crc32(kind + payload) & 0xFFFFFFFF)
    )


def _build_png(width: int, height: int, colour_type: int, raw: bytes) -> bytes:
    header = struct.pack(">IIBBBBB", width, height, 8, colour_type, 0, 0, 0)
    return (
        _SIGNATURE
        + _chunk(b"IHDR", header)
        + _chunk(b"IDAT", zlib.compress(raw, 9))
        + _chunk(b"IEND", b"")
    )


class PngRoundTripTest(unittest.TestCase):
    def test_round_trips_rgba_pixels(self):
        width, height = 3, 2
        rgba = bytes(
            [
                255, 0, 0, 255,   0, 255, 0, 255,   0, 0, 255, 255,
                10, 20, 30, 255,  40, 50, 60, 255,  70, 80, 90, 255,
            ]
        )
        encoded = encode_rgba(width, height, rgba)
        self.assertEqual(encoded[:8], b"\x89PNG\r\n\x1a\n")
        self.assertEqual(decode_rgba(encoded), (width, height, rgba))

    def test_rejects_non_png_data(self):
        with self.assertRaisesRegex(PngError, "signature"):
            decode_rgba(b"not a png at all")

    def test_rejects_wrong_pixel_buffer_length(self):
        with self.assertRaisesRegex(PngError, "length"):
            encode_rgba(2, 2, b"\x00\x00\x00")


class PngFilterReconstructionTest(unittest.TestCase):
    """encode_rgba only ever emits filter type 0 (None), so the round-trip
    test above never exercises the Sub/Up/Average/Paeth un-filtering code
    paths. Those filters are exactly what a real encoder (e.g. Blender's
    PNG export in Task 7) will use, so this test hand-builds a PNG whose
    scanlines use filter types 1-4 and asserts the decoder reconstructs
    the exact original pixel values.

    Image is 2x4 RGB (colour type 2, bpp/channels=3), with intended raw
    (unfiltered) pixel values per row:
        row0: (10,20,30) (40,50,60)
        row1: (15,25,35) (45,55,65)
        row2: (5,10,15)  (100,150,200)
        row3: (20,30,40) (60,70,80)

    Filtered bytes below were computed by hand per the PNG spec formulas:
      Sub:     filtered[i] = raw[i] - raw[i-bpp]            (row0, left=0 for i<bpp)
      Up:      filtered[i] = raw[i] - prevRaw[i]             (row1)
      Average: filtered[i] = raw[i] - floor((left+up)/2)     (row2)
      Paeth:   filtered[i] = raw[i] - Paeth(left,up,upperLeft) (row3)
    all mod 256.
    """

    def test_decodes_sub_up_average_and_paeth_filtered_scanlines(self):
        width, height, channels = 2, 4, 3
        row0 = bytes([1, 10, 20, 30, 30, 30, 30])  # Sub
        row1 = bytes([2, 5, 5, 5, 5, 5, 5])  # Up
        row2 = bytes([3, 254, 254, 254, 75, 118, 160])  # Average
        row3 = bytes([4, 15, 20, 25, 216, 176, 136])  # Paeth
        raw = row0 + row1 + row2 + row3
        png = _build_png(width, height, colour_type=2, raw=raw)

        expected_rgba = bytes(
            [
                10, 20, 30, 255, 40, 50, 60, 255,
                15, 25, 35, 255, 45, 55, 65, 255,
                5, 10, 15, 255, 100, 150, 200, 255,
                20, 30, 40, 255, 60, 70, 80, 255,
            ]
        )
        self.assertEqual(decode_rgba(png), (width, height, expected_rgba))
        self.assertEqual(channels, 3)


if __name__ == "__main__":
    unittest.main()
