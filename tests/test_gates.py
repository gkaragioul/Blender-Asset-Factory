import json
import struct
import tempfile
import unittest
from pathlib import Path

from factory.config import FactoryConfig
from factory.gates import GATE2_CATASTROPHE, gate1, gate2, rank_candidates, verdict
from factory.png import encode_rgba
from factory.style_contract import StyleContract
from tests.temp_paths import temporary_root

PALETTE = ((20, 18, 16), (104, 82, 56), (188, 192, 186))
CONTRACT = {
    "schema_version": 1,
    "palette": "palette.png",
    "texture_size": 64,
    "filtering": "nearest",
    "polycount_bands": {"small": 400, "medium": 1000, "large": 2500},
    "grid_unit": 0.5,
    "up_axis": "Y",
    "drop_maps": ["normal", "roughness", "metallic"],
    "vertex_light_bake": True,
}


def _glb(texture: bytes, materials: list[dict]) -> bytes:
    document = {
        "asset": {"version": "2.0"},
        "images": [{"bufferView": 0, "mimeType": "image/png"}],
        "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": len(texture)}],
        "buffers": [{"byteLength": len(texture)}],
        "materials": materials,
    }
    body = json.dumps(document, separators=(",", ":")).encode("utf-8")
    body += b" " * ((4 - len(body) % 4) % 4)
    binary = texture + b"\x00" * ((4 - len(texture) % 4) % 4)
    total = 12 + 8 + len(body) + 8 + len(binary)
    return (
        struct.pack("<III", 0x46546C67, 2, total)
        + struct.pack("<II", len(body), 0x4E4F534A)
        + body
        + struct.pack("<II", len(binary), 0x004E4942)
        + binary
    )


def _texture(colours) -> bytes:
    rgba = bytearray()
    for index in range(16):
        rgba.extend((*colours[index % len(colours)], 255))
    return encode_rgba(4, 4, bytes(rgba))


class GateTest(unittest.TestCase):
    def setUp(self):
        self.config = FactoryConfig.load()
        self.temp = tempfile.TemporaryDirectory(dir=temporary_root())
        temp_path = Path(self.temp.name)
        rgba = bytearray()
        for colour in PALETTE:
            rgba.extend((*colour, 255))
        (temp_path / "palette.png").write_bytes(encode_rgba(len(PALETTE), 1, bytes(rgba)))
        path = temp_path / "contract.json"
        path.write_text(json.dumps(CONTRACT), encoding="utf-8")
        self.contract = StyleContract.load(self.config, path)

    def tearDown(self):
        self.temp.cleanup()

    def test_gate1_passes_a_conforming_asset(self):
        report = gate1(
            _glb(_texture(PALETTE), [{"name": "flat"}]),
            self.contract, "small", triangles=380,
            validator_ok=True, preview_ok=True,
        )
        self.assertTrue(report["ok"], report["failures"])

    def test_gate1_fails_over_budget_triangles(self):
        report = gate1(
            _glb(_texture(PALETTE), [{"name": "flat"}]),
            self.contract, "small", triangles=401,
            validator_ok=True, preview_ok=True,
        )
        self.assertFalse(report["ok"])
        self.assertIn("triangle_budget", report["failures"])

    def test_gate1_fails_off_palette_texture(self):
        report = gate1(
            _glb(_texture([(1, 2, 3)]), [{"name": "flat"}]),
            self.contract, "small", triangles=100,
            validator_ok=True, preview_ok=True,
        )
        self.assertFalse(report["ok"])
        self.assertIn("palette_conformance", report["failures"])

    def test_gate1_fails_forbidden_material_texture(self):
        report = gate1(
            _glb(_texture(PALETTE), [{"name": "flat", "normalTexture": {"index": 0}}]),
            self.contract, "small", triangles=100,
            validator_ok=True, preview_ok=True,
        )
        self.assertFalse(report["ok"])
        self.assertIn("dropped_maps", report["failures"])

    def test_gate1_fails_forbidden_metallic_roughness_texture(self):
        # drop_maps includes "roughness" and "metallic", but in glTF those
        # live nested at pbrMetallicRoughness.metallicRoughnessTexture, not
        # as a top-level material key like normalTexture/occlusionTexture/
        # emissiveTexture. A shipped metallic/roughness texture must still
        # be caught.
        report = gate1(
            _glb(
                _texture(PALETTE),
                [{
                    "name": "flat",
                    "pbrMetallicRoughness": {
                        "metallicRoughnessTexture": {"index": 0},
                    },
                }],
            ),
            self.contract, "small", triangles=100,
            validator_ok=True, preview_ok=True,
        )
        self.assertFalse(report["ok"])
        self.assertIn("dropped_maps", report["failures"])

    def test_gate1_fails_when_validator_or_preview_failed(self):
        report = gate1(
            _glb(_texture(PALETTE), [{"name": "flat"}]),
            self.contract, "small", triangles=100,
            validator_ok=False, preview_ok=True,
        )
        self.assertIn("gltf_validator", report["failures"])

    def test_gate2_uses_a_catastrophe_floor_not_a_quality_threshold(self):
        # 0.613 is a MEASURED good conversion (45,881 -> 2,470 triangles).
        # It must pass. The old 0.95 threshold would have rejected it.
        self.assertEqual(gate2({"minimum": 0.613, "mean": 0.637})["verdict"], "pass")
        self.assertEqual(gate2({"minimum": 0.46, "mean": 0.50})["verdict"], "pass")
        # 0.03 is the MEASURED Y-up double-rotation defect. It must be rejected.
        self.assertEqual(gate2({"minimum": 0.03, "mean": 0.05})["verdict"], "reject")
        self.assertEqual(gate2({"minimum": 0.44, "mean": 0.60})["verdict"], "reject")
        self.assertEqual(GATE2_CATASTROPHE, 0.45)

    def test_rank_candidates_orders_best_first(self):
        comparisons = [
            {"minimum": 0.58, "mean": 0.61},
            {"minimum": 0.71, "mean": 0.74},
            {"minimum": 0.63, "mean": 0.66},
        ]
        self.assertEqual(rank_candidates(comparisons), [1, 2, 0])

    def test_rank_candidates_rejects_an_empty_list(self):
        with self.assertRaisesRegex(ValueError, "at least one candidate"):
            rank_candidates([])

    def test_verdict_combines_both_gates(self):
        good = {"ok": True, "failures": []}
        bad = {"ok": False, "failures": ["triangle_budget"]}
        self.assertEqual(verdict(good, {"verdict": "pass"}), "pass")

        self.assertEqual(verdict(good, {"verdict": "reject"}), "reject")
        self.assertEqual(verdict(bad, {"verdict": "pass"}), "reject")


if __name__ == "__main__":
    unittest.main()
