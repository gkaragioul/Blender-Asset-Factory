from __future__ import annotations

import json
import struct
from pathlib import Path


def triangle_glb_bytes() -> bytes:
    positions = struct.pack("<9f", -1.0, -1.0, 0.0, 1.0, -1.0, 0.0, 0.0, 1.0, 0.0)
    uvs = struct.pack("<6f", 0.0, 0.0, 1.0, 0.0, 0.5, 1.0)
    indices = struct.pack("<3H", 0, 1, 2)
    binary = positions + uvs + indices
    binary += b"\x00" * ((4 - len(binary) % 4) % 4)
    document = {
        "asset": {"version": "2.0", "generator": "BAF deterministic fixture"},
        "buffers": [{"byteLength": len(binary)}],
        "bufferViews": [
            {"buffer": 0, "byteOffset": 0, "byteLength": len(positions), "target": 34962},
            {"buffer": 0, "byteOffset": len(positions), "byteLength": len(uvs), "target": 34962},
            {"buffer": 0, "byteOffset": len(positions) + len(uvs), "byteLength": len(indices), "target": 34963},
        ],
        "accessors": [
            {"bufferView": 0, "componentType": 5126, "count": 3, "type": "VEC3", "min": [-1, -1, 0], "max": [1, 1, 0]},
            {"bufferView": 1, "componentType": 5126, "count": 3, "type": "VEC2", "min": [0, 0], "max": [1, 1]},
            {"bufferView": 2, "componentType": 5123, "count": 3, "type": "SCALAR", "min": [0], "max": [2]},
        ],
        "materials": [{"name": "FixtureMaterial", "pbrMetallicRoughness": {"baseColorFactor": [0.65, 0.32, 0.12, 1]}}],
        "meshes": [{"name": "FixtureTriangle", "primitives": [{"attributes": {"POSITION": 0, "TEXCOORD_0": 1}, "indices": 2, "material": 0}]}],
        "nodes": [{"mesh": 0}],
        "scenes": [{"nodes": [0]}],
        "scene": 0,
    }
    json_chunk = json.dumps(document, separators=(",", ":")).encode("utf-8")
    json_chunk += b" " * ((4 - len(json_chunk) % 4) % 4)
    total = 12 + 8 + len(json_chunk) + 8 + len(binary)
    return (
        struct.pack("<4sII", b"glTF", 2, total)
        + struct.pack("<I4s", len(json_chunk), b"JSON")
        + json_chunk
        + struct.pack("<I4s", len(binary), b"BIN\x00")
        + binary
    )


def write_triangle_glb(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(triangle_glb_bytes())
    return path
