from __future__ import annotations

import json
import struct
import binascii
import zlib


def _png_chunk(kind: bytes, payload: bytes) -> bytes:
    return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", binascii.crc32(kind + payload) & 0xFFFFFFFF)


def _fixture_png() -> bytes:
    width = height = 2
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    row = b"\x00" + bytes((178, 82, 32, 255, 122, 48, 24, 255))
    pixels = row + row
    return b"\x89PNG\r\n\x1a\n" + _png_chunk(b"IHDR", ihdr) + _png_chunk(b"IDAT", zlib.compress(pixels)) + _png_chunk(b"IEND", b"")
from pathlib import Path


def triangle_glb_bytes() -> bytes:
    positions = struct.pack("<9f", -1.0, -1.0, 0.0, 1.0, -1.0, 0.0, 0.0, 1.0, 0.0)
    uvs = struct.pack("<6f", 0.0, 0.0, 1.0, 0.0, 0.5, 1.0)
    indices = struct.pack("<3H", 0, 1, 2)
    png = _fixture_png()
    geometry_length = len(positions) + len(uvs) + len(indices)
    geometry_padding = (4 - geometry_length % 4) % 4
    image_offset = geometry_length + geometry_padding
    binary = positions + uvs + indices + b"\x00" * geometry_padding + png
    binary += b"\x00" * ((4 - len(binary) % 4) % 4)
    document = {
        "asset": {"version": "2.0", "generator": "BAF deterministic fixture"},
        "buffers": [{"byteLength": len(binary)}],
        "bufferViews": [
            {"buffer": 0, "byteOffset": 0, "byteLength": len(positions), "target": 34962},
            {"buffer": 0, "byteOffset": len(positions), "byteLength": len(uvs), "target": 34962},
            {"buffer": 0, "byteOffset": len(positions) + len(uvs), "byteLength": len(indices), "target": 34963},
            {"buffer": 0, "byteOffset": image_offset, "byteLength": len(png)},
        ],
        "accessors": [
            {"bufferView": 0, "componentType": 5126, "count": 3, "type": "VEC3", "min": [-1, -1, 0], "max": [1, 1, 0]},
            {"bufferView": 1, "componentType": 5126, "count": 3, "type": "VEC2", "min": [0, 0], "max": [1, 1]},
            {"bufferView": 2, "componentType": 5123, "count": 3, "type": "SCALAR", "min": [0], "max": [2]},
        ],
        "images": [{"name": "FixturePixel", "bufferView": 3, "mimeType": "image/png"}],
        "samplers": [{"magFilter": 9728, "minFilter": 9728, "wrapS": 33071, "wrapT": 33071}],
        "textures": [{"sampler": 0, "source": 0}],
        "materials": [{"name": "FixtureMaterial", "pbrMetallicRoughness": {"baseColorFactor": [0.65, 0.32, 0.12, 1], "baseColorTexture": {"index": 0}}}],
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


def _solid_png(width: int, height: int, colour: tuple[int, int, int]) -> bytes:
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    row = b"\x00" + bytes((*colour, 255)) * width
    return (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", ihdr)
        + _png_chunk(b"IDAT", zlib.compress(row * height))
        + _png_chunk(b"IEND", b"")
    )


def multi_texture_cube_glb_bytes() -> bytes:
    """A cube whose single material carries TWO textures.

    Exists for one purpose: the PS1 pass must export exactly one image no
    matter how many the source had. The trenchgun fixture only ever carries
    base colour / roughness / metallic / normal, and the contract's drop_maps
    names the last three, so it cannot distinguish "the pass enforces one
    texture" from "this source happened to have nothing else". The emissive
    map here is on a socket drop_maps does NOT name, so it survives every
    stage that works from a list of sockets.

    It is also fully metallic (see metallicFactor below), which covers a
    second real hazard the trenchgun cannot: a metallic surface has no
    diffuse component, so its albedo bake is black unless the pass
    neutralises metallic first.

    A cube rather than a triangle because retro_pass's floater removal
    discards anything whose bounding volume is negligible, and a flat
    triangle has zero thickness.
    """
    corners = (
        (-0.5, -0.5, -0.5), (0.5, -0.5, -0.5), (0.5, 0.5, -0.5), (-0.5, 0.5, -0.5),
        (-0.5, -0.5, 0.5), (0.5, -0.5, 0.5), (0.5, 0.5, 0.5), (-0.5, 0.5, 0.5),
    )
    positions = b"".join(struct.pack("<3f", *corner) for corner in corners)
    uvs = b"".join(
        struct.pack("<2f", (corner[0] + 0.5), (corner[1] + 0.5)) for corner in corners
    )
    faces = (
        (0, 1, 2), (0, 2, 3), (4, 6, 5), (4, 7, 6),
        (0, 3, 7), (0, 7, 4), (1, 5, 6), (1, 6, 2),
        (0, 4, 5), (0, 5, 1), (3, 2, 6), (3, 6, 7),
    )
    indices = b"".join(struct.pack("<3H", *face) for face in faces)
    base_png = _solid_png(4, 4, (146, 118, 82))
    emissive_png = _solid_png(4, 4, (17, 240, 61))

    geometry = positions + uvs + indices
    geometry += b"\x00" * ((4 - len(geometry) % 4) % 4)
    base_offset = len(geometry)
    after_base = base_offset + len(base_png)
    after_base_padded = after_base + ((4 - after_base % 4) % 4)
    binary = geometry + base_png + b"\x00" * (after_base_padded - after_base) + emissive_png
    binary += b"\x00" * ((4 - len(binary) % 4) % 4)

    document = {
        "asset": {"version": "2.0", "generator": "BAF multi-texture fixture"},
        "buffers": [{"byteLength": len(binary)}],
        "bufferViews": [
            {"buffer": 0, "byteOffset": 0, "byteLength": len(positions), "target": 34962},
            {"buffer": 0, "byteOffset": len(positions), "byteLength": len(uvs), "target": 34962},
            {"buffer": 0, "byteOffset": len(positions) + len(uvs), "byteLength": len(indices), "target": 34963},
            {"buffer": 0, "byteOffset": base_offset, "byteLength": len(base_png)},
            {"buffer": 0, "byteOffset": after_base_padded, "byteLength": len(emissive_png)},
        ],
        "accessors": [
            {"bufferView": 0, "componentType": 5126, "count": 8, "type": "VEC3", "min": [-0.5, -0.5, -0.5], "max": [0.5, 0.5, 0.5]},
            {"bufferView": 1, "componentType": 5126, "count": 8, "type": "VEC2", "min": [0, 0], "max": [1, 1]},
            {"bufferView": 2, "componentType": 5123, "count": 36, "type": "SCALAR", "min": [0], "max": [7]},
        ],
        "images": [
            {"name": "CubeBaseColor", "bufferView": 3, "mimeType": "image/png"},
            {"name": "CubeEmissive", "bufferView": 4, "mimeType": "image/png"},
        ],
        "samplers": [{"magFilter": 9728, "minFilter": 9728, "wrapS": 33071, "wrapT": 33071}],
        "textures": [{"sampler": 0, "source": 0}, {"sampler": 0, "source": 1}],
        "materials": [
            {
                "name": "MultiTextureMaterial",
                "pbrMetallicRoughness": {
                    "baseColorFactor": [1, 1, 1, 1],
                    "baseColorTexture": {"index": 0},
                    # Explicitly fully metallic, which is ALSO glTF's default
                    # when the field is omitted. A fully metallic surface has
                    # no diffuse component, so an albedo bake of it comes out
                    # black unless the pass neutralises metallic first. Metal
                    # is the normal case for the weapons this pack converts,
                    # so the fixture keeps that case covered.
                    "metallicFactor": 1.0,
                },
                # emissiveTexture is deliberately on a socket the contract's
                # drop_maps does not name, so only positive enforcement
                # removes it.
                "emissiveTexture": {"index": 1},
                "emissiveFactor": [1, 1, 1],
            }
        ],
        "meshes": [{"name": "MultiTextureCube", "primitives": [{"attributes": {"POSITION": 0, "TEXCOORD_0": 1}, "indices": 2, "material": 0}]}],
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


def write_multi_texture_cube_glb(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(multi_texture_cube_glb_bytes())
    return path
