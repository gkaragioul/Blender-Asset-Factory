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


TRANSLUCENT_ALPHA = 0.45
TRANSLUCENT_BASE_COLOUR = [0.35, 0.62, 0.28, TRANSLUCENT_ALPHA]


def multi_texture_cube_glb_bytes() -> bytes:
    """A cube with two material slots, covering three separate hazards.

    Slot 0 -- "MultiTextureMaterial": a base colour map AND an emissive map,
    fully metallic.

    * TWO textures. The PS1 pass must export exactly one image whatever the
      source had. The trenchgun fixture only carries base colour / roughness
      / metallic / normal and the contract's drop_maps names the last three,
      so on that fixture "the pass enforces one texture" and "this source
      happened to have nothing else" are indistinguishable. The emissive map
      sits on a socket drop_maps does NOT name, so it survives any stage
      that works from a list of sockets.
    * FULLY METALLIC (and glTF's `metallicFactor` defaults to 1.0 when
      omitted, so this is the common case, not an edge case). A metallic
      surface has no diffuse component, so its albedo bake comes out black
      unless the pass neutralises metallic before baking.

    Slot 1 -- "TranslucentMaterial": alpha below 1.0, alphaMode BLEND.

    * TRANSPARENCY MUST SURVIVE TO THE EXPORT. The bake needs opaque,
      non-metallic inputs to produce a usable albedo, but those are bake
      concerns and must not become export values. Forcing alpha to 1.0 turns
      an intentional cutout into a solid slab -- and no gate catches it:
      Gate 1 checks palette and triangle budget, Gate 2 compares silhouettes
      of the same geometry before and after. Alpha cutout is how PS1-era art
      renders barbed wire, chain-link, foliage and glass.

    Two material slots on one mesh also mirrors how the trenchgun really
    stores its parts, so it exercises the split-by-material path.

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
    # Split across two primitives so each can carry its own material. Each
    # half still spans the full bounding box, so neither is discarded as a
    # floater.
    faces_opaque = ((0, 1, 2), (0, 2, 3), (4, 6, 5), (4, 7, 6), (0, 3, 7), (0, 7, 4))
    faces_translucent = ((1, 5, 6), (1, 6, 2), (0, 4, 5), (0, 5, 1), (3, 2, 6), (3, 6, 7))
    indices_opaque = b"".join(struct.pack("<3H", *face) for face in faces_opaque)
    indices_translucent = b"".join(struct.pack("<3H", *face) for face in faces_translucent)
    base_png = _solid_png(4, 4, (146, 118, 82))
    emissive_png = _solid_png(4, 4, (17, 240, 61))

    uv_offset = len(positions)
    indices_opaque_offset = uv_offset + len(uvs)
    indices_translucent_offset = indices_opaque_offset + len(indices_opaque)
    geometry_length = indices_translucent_offset + len(indices_translucent)
    geometry = (
        positions + uvs + indices_opaque + indices_translucent
        + b"\x00" * ((4 - geometry_length % 4) % 4)
    )
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
            {"buffer": 0, "byteOffset": uv_offset, "byteLength": len(uvs), "target": 34962},
            {"buffer": 0, "byteOffset": indices_opaque_offset, "byteLength": len(indices_opaque), "target": 34963},
            {"buffer": 0, "byteOffset": indices_translucent_offset, "byteLength": len(indices_translucent), "target": 34963},
            {"buffer": 0, "byteOffset": base_offset, "byteLength": len(base_png)},
            {"buffer": 0, "byteOffset": after_base_padded, "byteLength": len(emissive_png)},
        ],
        "accessors": [
            {"bufferView": 0, "componentType": 5126, "count": 8, "type": "VEC3", "min": [-0.5, -0.5, -0.5], "max": [0.5, 0.5, 0.5]},
            {"bufferView": 1, "componentType": 5126, "count": 8, "type": "VEC2", "min": [0, 0], "max": [1, 1]},
            {"bufferView": 2, "componentType": 5123, "count": 18, "type": "SCALAR", "min": [0], "max": [7]},
            {"bufferView": 3, "componentType": 5123, "count": 18, "type": "SCALAR", "min": [0], "max": [7]},
        ],
        "images": [
            {"name": "CubeBaseColor", "bufferView": 4, "mimeType": "image/png"},
            {"name": "CubeEmissive", "bufferView": 5, "mimeType": "image/png"},
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
                    # when the field is omitted. See the docstring.
                    "metallicFactor": 1.0,
                },
                # emissiveTexture is deliberately on a socket the contract's
                # drop_maps does not name, so only positive enforcement
                # removes it.
                "emissiveTexture": {"index": 1},
                "emissiveFactor": [1, 1, 1],
            },
            {
                "name": "TranslucentMaterial",
                "alphaMode": "BLEND",
                "pbrMetallicRoughness": {
                    "baseColorFactor": TRANSLUCENT_BASE_COLOUR,
                    "metallicFactor": 0.0,
                    "roughnessFactor": 0.8,
                },
            },
        ],
        "meshes": [
            {
                "name": "MultiTextureCube",
                "primitives": [
                    {"attributes": {"POSITION": 0, "TEXCOORD_0": 1}, "indices": 2, "material": 0},
                    {"attributes": {"POSITION": 0, "TEXCOORD_0": 1}, "indices": 3, "material": 1},
                ],
            }
        ],
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


CUTOUT_MATERIAL_NAME = "CutoutMaterial"
CUTOUT_ALPHA_CUTOFF = 0.5
CUTOUT_OPAQUE_COLOUR = (146, 118, 82)
CUTOUT_HOLE_COLOUR = (60, 45, 30)


def _checker_cutout_png() -> bytes:
    """2x2 RGBA whose alpha is a checker: half the texels are fully cut out.

    A CHECKER rather than a half-and-half split because the cube's authored
    UVs are planar (u,v) = (x,y), so its four side faces collapse to a single
    UV line. A half-and-half mask would leave those faces sampling only the
    opaque half and the fixture would then only exercise cutout on two of
    twelve faces. A checker puts transparent texels on every line through the
    map.

    The two halves also carry DIFFERENT RGB, so the colour bake still
    produces more than one colour and `_bake_wrote_nothing` stays meaningful
    on this fixture.
    """
    width = height = 2
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    lower = b"\x00" + bytes((*CUTOUT_OPAQUE_COLOUR, 255, *CUTOUT_HOLE_COLOUR, 0))
    upper = b"\x00" + bytes((*CUTOUT_HOLE_COLOUR, 0, *CUTOUT_OPAQUE_COLOUR, 255))
    return (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", ihdr)
        + _png_chunk(b"IDAT", zlib.compress(lower + upper))
        + _png_chunk(b"IEND", b"")
    )


def cutout_cube_glb_bytes() -> bytes:
    """A cube whose ONE material carries a TEXTURE-DRIVEN alpha cutout.

    Distinct from `multi_texture_cube_glb_bytes`, whose TranslucentMaterial
    carries a SCALAR alpha factor. A scalar alpha is a property of the
    material and survives as long as the exporter writes the Principled
    Alpha socket's default_value; a cutout MASK lives in the base colour
    image's ALPHA CHANNEL, and the PS1 pass rebuilds that image from scratch
    by baking. So the mask only reaches the export if the pass deliberately
    bakes it and merges it into the quantized atlas -- there is no socket
    value to restore.

    Both failure modes are silent and neither is caught by a gate: Gate 1
    checks palette conformance and the triangle budget, Gate 2 compares
    silhouettes of the SAME geometry before and after. A barbed wire coil
    converted into a solid slab passes both.

    A cube rather than a plane because retro_pass's floater removal discards
    anything whose bounding volume is negligible.
    """
    corners = (
        (-0.5, -0.5, -0.5), (0.5, -0.5, -0.5), (0.5, 0.5, -0.5), (-0.5, 0.5, -0.5),
        (-0.5, -0.5, 0.5), (0.5, -0.5, 0.5), (0.5, 0.5, 0.5), (-0.5, 0.5, 0.5),
    )
    faces = (
        (0, 1, 2), (0, 2, 3), (4, 6, 5), (4, 7, 6), (0, 3, 7), (0, 7, 4),
        (1, 5, 6), (1, 6, 2), (0, 4, 5), (0, 5, 1), (3, 2, 6), (3, 6, 7),
    )
    positions = b"".join(struct.pack("<3f", *corner) for corner in corners)
    uvs = b"".join(
        struct.pack("<2f", (corner[0] + 0.5), (corner[1] + 0.5)) for corner in corners
    )
    indices = b"".join(struct.pack("<3H", *face) for face in faces)
    png = _checker_cutout_png()

    uv_offset = len(positions)
    indices_offset = uv_offset + len(uvs)
    geometry_length = indices_offset + len(indices)
    geometry = positions + uvs + indices + b"\x00" * ((4 - geometry_length % 4) % 4)
    image_offset = len(geometry)
    binary = geometry + png
    binary += b"\x00" * ((4 - len(binary) % 4) % 4)

    document = {
        "asset": {"version": "2.0", "generator": "BAF cutout fixture"},
        "buffers": [{"byteLength": len(binary)}],
        "bufferViews": [
            {"buffer": 0, "byteOffset": 0, "byteLength": len(positions), "target": 34962},
            {"buffer": 0, "byteOffset": uv_offset, "byteLength": len(uvs), "target": 34962},
            {"buffer": 0, "byteOffset": indices_offset, "byteLength": len(indices), "target": 34963},
            {"buffer": 0, "byteOffset": image_offset, "byteLength": len(png)},
        ],
        "accessors": [
            {"bufferView": 0, "componentType": 5126, "count": 8, "type": "VEC3", "min": [-0.5, -0.5, -0.5], "max": [0.5, 0.5, 0.5]},
            {"bufferView": 1, "componentType": 5126, "count": 8, "type": "VEC2", "min": [0, 0], "max": [1, 1]},
            {"bufferView": 2, "componentType": 5123, "count": 36, "type": "SCALAR", "min": [0], "max": [7]},
        ],
        "images": [{"name": "CutoutBaseColor", "bufferView": 3, "mimeType": "image/png"}],
        # NEAREST, so the importer gives the image node 'Closest'
        # interpolation and the mask stays binary through the bake.
        "samplers": [{"magFilter": 9728, "minFilter": 9728, "wrapS": 33071, "wrapT": 33071}],
        "textures": [{"sampler": 0, "source": 0}],
        "materials": [
            {
                "name": CUTOUT_MATERIAL_NAME,
                "alphaMode": "MASK",
                "alphaCutoff": CUTOUT_ALPHA_CUTOFF,
                "doubleSided": True,
                "pbrMetallicRoughness": {
                    "baseColorFactor": [1, 1, 1, 1],
                    "baseColorTexture": {"index": 0},
                    "metallicFactor": 0.0,
                    "roughnessFactor": 0.9,
                },
            }
        ],
        "meshes": [
            {
                "name": "CutoutCube",
                "primitives": [
                    {"attributes": {"POSITION": 0, "TEXCOORD_0": 1}, "indices": 2, "material": 0}
                ],
            }
        ],
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


def write_cutout_cube_glb(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(cutout_cube_glb_bytes())
    return path


THIN_PLANE_COLOUR = (146, 118, 82)


def thin_plane_glb_bytes() -> bytes:
    """A GENUINELY FLAT 1x1 card: two triangles, zero thickness.

    Every other fixture in this file is a cube, and the docstrings said why in
    as many words -- "a cube rather than a plane/triangle because retro_pass's
    floater removal discards it". That was a defect being worked around rather
    than filed. `_remove_floaters` compared an AABB VOLUME whose zero extent
    was floored at 1e-9 against `(diagonal * 0.001) ** 3`, so a 1x1 card on an
    asset of diagonal 1.414 scored 1e-9 against 2.8e-9 and was deleted.

    Cutout cards are not an exotic input for this pack. `barbed_wire_coil`,
    `barbed_wire_post`, foliage, chain-link and signpost lettering planes are
    all catalogued assets and all of them are flat. Every fixture being shaped
    to dodge the defect is exactly why nothing could catch it.

    The plane lies in the glTF XY plane (z == 0). The glTF importer maps
    glTF (x, y, z) to Blender (x, -z, y), so it arrives with zero extent on
    Blender Y; retro_pass's -90deg X rotation for `up_axis: "Y"` then stands it
    upright with the 0..1 extent on the up axis, which is how a real card is
    oriented.
    """
    corners = ((-0.5, 0.0, 0.0), (0.5, 0.0, 0.0), (0.5, 1.0, 0.0), (-0.5, 1.0, 0.0))
    positions = b"".join(struct.pack("<3f", *corner) for corner in corners)
    uvs = b"".join(
        struct.pack("<2f", corner[0] + 0.5, corner[1]) for corner in corners
    )
    indices = b"".join(struct.pack("<3H", *face) for face in ((0, 1, 2), (0, 2, 3)))
    png = _solid_png(4, 4, THIN_PLANE_COLOUR)

    uv_offset = len(positions)
    indices_offset = uv_offset + len(uvs)
    geometry_length = indices_offset + len(indices)
    geometry = positions + uvs + indices + b"\x00" * ((4 - geometry_length % 4) % 4)
    image_offset = len(geometry)
    binary = geometry + png
    binary += b"\x00" * ((4 - len(binary) % 4) % 4)

    document = {
        "asset": {"version": "2.0", "generator": "BAF thin plane fixture"},
        "buffers": [{"byteLength": len(binary)}],
        "bufferViews": [
            {"buffer": 0, "byteOffset": 0, "byteLength": len(positions), "target": 34962},
            {"buffer": 0, "byteOffset": uv_offset, "byteLength": len(uvs), "target": 34962},
            {"buffer": 0, "byteOffset": indices_offset, "byteLength": len(indices), "target": 34963},
            {"buffer": 0, "byteOffset": image_offset, "byteLength": len(png)},
        ],
        "accessors": [
            {"bufferView": 0, "componentType": 5126, "count": 4, "type": "VEC3", "min": [-0.5, 0, 0], "max": [0.5, 1, 0]},
            {"bufferView": 1, "componentType": 5126, "count": 4, "type": "VEC2", "min": [0, 0], "max": [1, 1]},
            {"bufferView": 2, "componentType": 5123, "count": 6, "type": "SCALAR", "min": [0], "max": [3]},
        ],
        "images": [{"name": "PlaneBaseColor", "bufferView": 3, "mimeType": "image/png"}],
        "samplers": [{"magFilter": 9728, "minFilter": 9728, "wrapS": 33071, "wrapT": 33071}],
        "textures": [{"sampler": 0, "source": 0}],
        "materials": [
            {
                "name": "PlaneMaterial",
                "doubleSided": True,
                "pbrMetallicRoughness": {
                    "baseColorFactor": [1, 1, 1, 1],
                    "baseColorTexture": {"index": 0},
                    "metallicFactor": 0.0,
                    "roughnessFactor": 0.9,
                },
            }
        ],
        "meshes": [
            {
                "name": "ThinPlane",
                "primitives": [
                    {"attributes": {"POSITION": 0, "TEXCOORD_0": 1}, "indices": 2, "material": 0}
                ],
            }
        ],
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


def write_thin_plane_glb(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(thin_plane_glb_bytes())
    return path


# ---------------------------------------------------------------------------
# ADVERSARIAL GATE FIXTURES
#
# Every one of these is a DEGENERATE asset that the pre-existing Gate 1 passed
# happily, because that gate was made entirely of upper bounds and
# set-membership tests and "nothing" satisfies both. They exist to prove the
# lower bounds in factory/gates.py fail on the trivially-conforming input --
# a check without a proof-of-failure test is how five blind spots happened.
#
# Each builder changes exactly ONE thing from the conforming pair
# (`gate_glb_bytes()` + `conforming_retro_report()`), so a rejection is
# attributable to that one thing and to nothing else.
# ---------------------------------------------------------------------------

GATE_PALETTE = ((20, 18, 16), (104, 82, 56), (188, 192, 186))
GATE_TEXTURE_SIZE = 64
NEAREST = 9728
LINEAR = 9729


def palette_texture_png(
    size: int = GATE_TEXTURE_SIZE, colours=GATE_PALETTE
) -> bytes:
    """A conforming atlas: every palette entry present, none foreign."""
    rgba = bytearray()
    for index in range(size * size):
        rgba.extend((*colours[index % len(colours)], 255))
    ihdr = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    stride = size * 4
    raw = b"".join(
        b"\x00" + bytes(rgba[row * stride : (row + 1) * stride]) for row in range(size)
    )
    return (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", ihdr)
        + _png_chunk(b"IDAT", zlib.compress(raw))
        + _png_chunk(b"IEND", b"")
    )


def black_texture_png(size: int = GATE_TEXTURE_SIZE) -> bytes:
    """A uniformly black atlas -- and a PERFECTLY palette-conforming one.

    The first blind spot found on this branch: a relink failure makes Cycles
    evaluate every source map as black, the quantizer snaps that to the
    darkest palette entry, and one colour is trivially a member of any
    palette. Nothing about the shipped file is off-palette; it simply carries
    no information.
    """
    return _solid_png(size, size, GATE_PALETTE[0])


def flat_part_colours_png(size: int = GATE_TEXTURE_SIZE) -> bytes:
    """Two flat regions -- the "bake fell back to flat base colours" case.

    Also fully palette-conforming, and it passes any `distinct_colours > 1`
    check, which is what the earlier "texture carries detail" assertion used.
    """
    rgba = bytearray()
    for row in range(size):
        colour = GATE_PALETTE[0] if row < size // 2 else GATE_PALETTE[2]
        for _column in range(size):
            rgba.extend((*colour, 255))
    ihdr = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    stride = size * 4
    raw = b"".join(
        b"\x00" + bytes(rgba[row * stride : (row + 1) * stride]) for row in range(size)
    )
    return (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", ihdr)
        + _png_chunk(b"IDAT", zlib.compress(raw))
        + _png_chunk(b"IEND", b"")
    )


def gate_glb_bytes(
    texture: bytes | None = None,
    *,
    materials: list[dict] | None = None,
    mag_filter: int | None = NEAREST,
) -> bytes:
    """A minimal GLB carrying one embedded texture, for Gate 1 to inspect.

    `mag_filter=None` omits the sampler entirely, which is the "glTF leaves
    the default filter implementation-defined" case -- every real runtime
    picks a linear one, so it must be rejected rather than assumed nearest.
    """
    texture = palette_texture_png() if texture is None else texture
    document: dict = {
        "asset": {"version": "2.0"},
        "images": [{"bufferView": 0, "mimeType": "image/png"}],
        "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": len(texture)}],
        "buffers": [{"byteLength": len(texture)}],
        "materials": materials if materials is not None else [{"name": "flat"}],
        "textures": [{"source": 0}],
    }
    if mag_filter is not None:
        document["samplers"] = [{"magFilter": mag_filter, "minFilter": mag_filter}]
        document["textures"][0]["sampler"] = 0
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


def conforming_retro_report(**overrides) -> dict:
    """The retro_pass measurements of a healthy asset, shaped like the real one.

    Numbers are scaled-down analogues of the measured trenchgun conversion
    (bounds grounded at ~0 with both horizontal centres on the grid; every
    part owning atlas texels; no alpha sources). Override exactly one key to
    build a degenerate case.
    """
    report = {
        "ok": True,
        "triangles_out": 100,
        "bounds": {
            "min": {"x": -0.25, "y": 1.66e-09, "z": -0.5},
            "max": {"x": 0.25, "y": 0.2, "z": 0.5},
            "origin": {"x": 0.0, "y": 0.0, "z": 0.0},
        },
        "stages": {
            "uv_texels_per_part": {"Barrel": 2109, "Stock": 890},
            "uv_covered_cells": 2999,
            "uv_overlap_cells": 0,
            "uv_regenerated": 2999,
            "alpha_sources": [],
        },
        "texture": {
            "size": GATE_TEXTURE_SIZE,
            "quantized": True,
            "palette_colours": len(GATE_PALETTE),
            "distinct_colours": len(GATE_PALETTE),
            "atlas_coverage": 0.7322,
            "alpha_mode": "OPAQUE",
            "alpha_cutoff": 0.5,
            "cutout_texels": 0,
        },
    }
    for key, value in overrides.items():
        if key in ("stages", "texture", "bounds") and isinstance(value, dict):
            report[key] = {**report[key], **value}
        else:
            report[key] = value
    return report


def wiped_atlas_retro_report() -> dict:
    """The atlas stage produced nothing: no covered texels, no part regions.

    Fourth instance of the blind spot -- a wiped atlas passes palette
    conformance because whatever single colour remains is trivially in the
    palette.
    """
    return conforming_retro_report(
        stages={
            "uv_texels_per_part": {"Barrel": 0, "Stock": 0},
            "uv_covered_cells": 0,
            "uv_regenerated": 0,
        }
    )


def untextured_part_retro_report() -> dict:
    """One part shipping with no atlas region at all.

    The per-material black bake: six healthy materials outvote one dead one,
    so the aggregate `_bake_wrote_nothing` check never fires.
    """
    return conforming_retro_report(
        stages={"uv_texels_per_part": {"Barrel": 2109, "Stock": 0}}
    )


def lost_cutout_retro_report() -> dict:
    """The source declared alpha sources and the export came out OPAQUE.

    The tracked launch blocker for `barbed_wire_coil`: a cutout mask that goes
    missing degrades silently to a solid slab, and neither gate could see it.
    """
    return conforming_retro_report(
        stages={"alpha_sources": ["CutoutMaterial"]},
        texture={"alpha_mode": "OPAQUE"},
    )


def misplaced_retro_report() -> dict:
    """A normalize regression: not grounded, and off the grid horizontally.

    This is what the Y-up rotation defect did, and Gate 2 is structurally
    blind to it -- silhouette IoU frames each render on its own bounding box.
    """
    return conforming_retro_report(
        bounds={
            "min": {"x": -0.13, "y": 0.42, "z": -0.5},
            "max": {"x": 0.37, "y": 0.62, "z": 0.5},
        }
    )
