import tempfile
import unittest
from pathlib import Path

from factory.gltf_inspection import GlbInspectionError, inspect_glb
from tests.glb_fixture import triangle_glb_bytes, write_triangle_glb
from tests.temp_paths import temporary_root


class GltfInspectionTest(unittest.TestCase):
    def test_inspects_embedded_triangle_and_uv_evidence(self):
        with tempfile.TemporaryDirectory(dir=temporary_root()) as temp:
            report = inspect_glb(write_triangle_glb(Path(temp) / "triangle.glb"))
        self.assertEqual(report["triangle_count"], 1)
        self.assertEqual(report["mesh_count"], 1)
        self.assertEqual(report["material_count"], 1)
        self.assertTrue(report["resources_embedded"])
        self.assertEqual(report["texcoord_bounds"]["0"], {"min": [0, 0], "max": [1, 1], "count": 3})

    def test_rejects_invalid_magic_and_length(self):
        with tempfile.TemporaryDirectory(dir=temporary_root()) as temp:
            path = Path(temp) / "bad.glb"
            path.write_bytes(b"BAD!" + triangle_glb_bytes()[4:])
            with self.assertRaisesRegex(GlbInspectionError, "magic"):
                inspect_glb(path)
            path.write_bytes(triangle_glb_bytes()[:-1])
            with self.assertRaisesRegex(GlbInspectionError, "length"):
                inspect_glb(path)

    def test_rejects_external_uri_traversal(self):
        import json
        import struct

        doc = {"asset": {"version": "2.0"}, "buffers": [{"byteLength": 1, "uri": "../escape.bin"}]}
        chunk = json.dumps(doc).encode()
        chunk += b" " * ((4 - len(chunk) % 4) % 4)
        payload = struct.pack("<4sII", b"glTF", 2, 20 + len(chunk)) + struct.pack("<I4s", len(chunk), b"JSON") + chunk
        with tempfile.TemporaryDirectory(dir=temporary_root()) as temp:
            path = Path(temp) / "external.glb"
            path.write_bytes(payload)
            with self.assertRaisesRegex(GlbInspectionError, "unsafe external URI"):
                inspect_glb(path)


if __name__ == "__main__":
    unittest.main()
