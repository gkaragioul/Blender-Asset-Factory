from __future__ import annotations

import json
import struct
from pathlib import Path, PurePosixPath

from .io import sha256_file


class GlbInspectionError(ValueError):
    pass


def _unsafe_uri(uri: str) -> bool:
    if uri.startswith("data:"):
        return False
    normalized = uri.replace("\\", "/")
    path = PurePosixPath(normalized)
    return path.is_absolute() or ".." in path.parts or ":" in normalized


def _chunks(payload: bytes) -> tuple[dict, bytes | None]:
    if len(payload) < 12:
        raise GlbInspectionError("GLB header is truncated")
    magic, version, declared_length = struct.unpack_from("<4sII", payload)
    if magic != b"glTF":
        raise GlbInspectionError("invalid GLB magic")
    if version != 2:
        raise GlbInspectionError(f"unsupported GLB version: {version}")
    if declared_length != len(payload):
        raise GlbInspectionError(
            f"GLB declared length {declared_length} does not match {len(payload)}"
        )
    offset = 12
    json_document: dict | None = None
    binary: bytes | None = None
    while offset < len(payload):
        if offset + 8 > len(payload):
            raise GlbInspectionError("GLB chunk header is truncated")
        size, kind = struct.unpack_from("<I4s", payload, offset)
        offset += 8
        end = offset + size
        if end > len(payload):
            raise GlbInspectionError("GLB chunk length exceeds file length")
        content = payload[offset:end]
        offset = end
        if kind == b"JSON" and json_document is None:
            try:
                json_document = json.loads(content.decode("utf-8").rstrip(" \x00"))
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise GlbInspectionError(f"invalid JSON chunk: {error}") from error
        elif kind == b"BIN\x00" and binary is None:
            binary = content
    if json_document is None:
        raise GlbInspectionError("GLB has no JSON chunk")
    return json_document, binary


def _accessor_bounds(document: dict, binary: bytes | None, accessor: dict) -> tuple[list[float | int], list[float | int]]:
    if "min" in accessor and "max" in accessor:
        return accessor["min"], accessor["max"]
    if binary is None or "bufferView" not in accessor:
        raise GlbInspectionError("accessor bounds cannot be computed without an embedded buffer view")
    views = document.get("bufferViews", [])
    view_id = accessor["bufferView"]
    if not isinstance(view_id, int) or not 0 <= view_id < len(views):
        raise GlbInspectionError("accessor references an invalid buffer view")
    view = views[view_id]
    if view.get("buffer", 0) != 0:
        raise GlbInspectionError("accessor references an external buffer")
    component_formats = {5120: ("b", 1), 5121: ("B", 1), 5122: ("h", 2), 5123: ("H", 2), 5125: ("I", 4), 5126: ("f", 4)}
    dimensions = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}
    component = component_formats.get(accessor.get("componentType"))
    width = dimensions.get(accessor.get("type"))
    if component is None or width is None:
        raise GlbInspectionError("unsupported accessor component or vector type")
    code, component_size = component
    packed_size = component_size * width
    stride = int(view.get("byteStride", packed_size))
    start = int(view.get("byteOffset", 0)) + int(accessor.get("byteOffset", 0))
    count = int(accessor.get("count", 0))
    if count <= 0 or start < 0 or start + (count - 1) * stride + packed_size > len(binary):
        raise GlbInspectionError("accessor data exceeds the binary chunk")
    values = [struct.unpack_from("<" + code * width, binary, start + index * stride) for index in range(count)]
    minima = [min(value[index] for value in values) for index in range(width)]
    maxima = [max(value[index] for value in values) for index in range(width)]
    return minima, maxima


def inspect_glb(path: Path) -> dict:
    source = path.resolve(strict=True)
    if source.suffix.lower() != ".glb":
        raise GlbInspectionError("release inspection requires a .glb file")
    document, binary = _chunks(source.read_bytes())
    external_uris: list[str] = []
    for collection in (document.get("buffers", []), document.get("images", [])):
        for item in collection:
            uri = item.get("uri")
            if not uri or uri.startswith("data:"):
                continue
            if _unsafe_uri(uri):
                raise GlbInspectionError(f"unsafe external URI: {uri}")
            external_uris.append(uri)

    accessors = document.get("accessors", [])
    texcoord_bounds: dict[str, dict] = {}
    triangle_count = 0
    primitive_count = 0
    for mesh in document.get("meshes", []):
        for primitive in mesh.get("primitives", []):
            primitive_count += 1
            if primitive.get("mode", 4) == 4:
                index_id = primitive.get("indices")
                if index_id is not None and 0 <= index_id < len(accessors):
                    triangle_count += int(accessors[index_id].get("count", 0)) // 3
                else:
                    position_id = primitive.get("attributes", {}).get("POSITION")
                    if position_id is not None and 0 <= position_id < len(accessors):
                        triangle_count += int(accessors[position_id].get("count", 0)) // 3
            for semantic, accessor_id in primitive.get("attributes", {}).items():
                if not semantic.startswith("TEXCOORD_"):
                    continue
                if not isinstance(accessor_id, int) or not 0 <= accessor_id < len(accessors):
                    raise GlbInspectionError(f"invalid {semantic} accessor")
                accessor = accessors[accessor_id]
                if "sparse" in accessor:
                    raise GlbInspectionError(f"sparse {semantic} evidence is unsupported")
                minima, maxima = _accessor_bounds(document, binary, accessor)
                channel = semantic.split("_", 1)[1]
                evidence = {
                    "min": minima,
                    "max": maxima,
                    "count": accessor.get("count", 0),
                }
                previous = texcoord_bounds.get(channel)
                if previous:
                    evidence = {
                        "min": [min(a, b) for a, b in zip(previous["min"], evidence["min"])],
                        "max": [max(a, b) for a, b in zip(previous["max"], evidence["max"])],
                        "count": previous["count"] + evidence["count"],
                    }
                texcoord_bounds[channel] = evidence

    return {
        "schema_version": 1,
        "path": str(source),
        "sha256": sha256_file(source),
        "size": source.stat().st_size,
        "generator": document.get("asset", {}).get("generator"),
        "mesh_count": len(document.get("meshes", [])),
        "primitive_count": primitive_count,
        "triangle_count": triangle_count,
        "material_count": len(document.get("materials", [])),
        "texture_count": len(document.get("textures", [])),
        "image_count": len(document.get("images", [])),
        "extensions_used": sorted(document.get("extensionsUsed", [])),
        "extensions_required": sorted(document.get("extensionsRequired", [])),
        "texcoord_bounds": texcoord_bounds,
        "resources_embedded": not external_uris and all(
            "uri" not in item or str(item.get("uri", "")).startswith("data:")
            for item in document.get("buffers", []) + document.get("images", [])
        ),
        "external_uris": external_uris,
        "has_binary_chunk": binary is not None,
    }
