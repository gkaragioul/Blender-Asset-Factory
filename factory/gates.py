from __future__ import annotations

import json
import struct

from .palette import conformance, load_palette
from .style_contract import StyleContract

GATE2_CATASTROPHE = 0.45

# glTF material keys that carry the maps we tell the pipeline to drop.
# normal/occlusion/emissive live as top-level keys directly on the
# material. roughness and metallic do NOT: they are both packed into a
# single nested pbrMetallicRoughness.metallicRoughnessTexture, which is why
# they are handled separately in gate1() rather than through this table.
_MAP_TEXTURES = {
    "normal": "normalTexture",
    "occlusion": "occlusionTexture",
    "emissive": "emissiveTexture",
}
_METALLIC_ROUGHNESS_MAPS = {"roughness", "metallic"}


def _glb_parts(data: bytes) -> tuple[dict, list[bytes]]:
    json_length = struct.unpack_from("<I", data, 12)[0]
    document = json.loads(data[20 : 20 + json_length].decode("utf-8"))
    binary_offset = 20 + json_length + 8
    images: list[bytes] = []
    for image in document.get("images", []):
        if "bufferView" not in image:
            continue
        view = document["bufferViews"][image["bufferView"]]
        start = binary_offset + view.get("byteOffset", 0)
        images.append(data[start : start + view["byteLength"]])
    return document, images


def gate1(
    glb_bytes: bytes,
    contract: StyleContract,
    role: str,
    triangles: int,
    validator_ok: bool,
    preview_ok: bool,
) -> dict:
    failures: list[str] = []
    details: dict = {}

    budget = contract.band_for(role)
    details["triangles"] = triangles
    details["budget"] = budget
    if triangles > budget:
        failures.append("triangle_budget")

    if not validator_ok:
        failures.append("gltf_validator")
    if not preview_ok:
        failures.append("runtime_preview")

    document, images = _glb_parts(glb_bytes)

    palette = load_palette(contract.palette)
    details["palette_colours"] = len(palette)
    if not images:
        failures.append("missing_texture")
    conformance_reports = []
    for image in images:
        result = conformance(image, palette)
        conformance_reports.append(result)
        if not result["ok"]:
            failures.append("palette_conformance")
            break
    details["palette_conformance"] = conformance_reports

    forbidden = [
        _MAP_TEXTURES[name]
        for name in contract.drop_maps
        if name in _MAP_TEXTURES
    ]
    check_metallic_roughness = any(
        name in _METALLIC_ROUGHNESS_MAPS for name in contract.drop_maps
    )

    offenders = [
        key
        for material in document.get("materials", [])
        for key in forbidden
        if key in material
    ]
    if check_metallic_roughness:
        for material in document.get("materials", []):
            pbr = material.get("pbrMetallicRoughness", {})
            if "metallicRoughnessTexture" in pbr:
                offenders.append("pbrMetallicRoughness.metallicRoughnessTexture")
    if offenders:
        failures.append("dropped_maps")
    details["forbidden_textures_present"] = sorted(set(offenders))

    return {
        "ok": not failures,
        "failures": sorted(set(failures)),
        "details": details,
    }


def gate2(comparison: dict) -> dict:
    """Detect catastrophic silhouette loss. NOT a quality score.

    Silhouette IoU between a high-poly source and its PS1 derivative is
    dominated by the decimation ratio, so it cannot rank quality. A measured
    good conversion (45,881 -> 2,470 triangles) scores 0.613. What IoU does
    discriminate is catastrophe: the Y-up double-rotation defect scored 0.03.
    Candidate selection is comparative -- see rank_candidates.
    """
    minimum = comparison["minimum"]
    result = "pass" if minimum >= GATE2_CATASTROPHE else "reject"
    return {
        "verdict": result,
        "minimum": minimum,
        "mean": comparison.get("mean"),
        "catastrophe_floor": GATE2_CATASTROPHE,
    }


def rank_candidates(comparisons: list[dict]) -> list[int]:
    """Order candidate indices best-first by minimum silhouette IoU.

    This is how a winner is chosen among N candidates for one asset. It needs
    no absolute threshold, which is why it is the primary selection mechanism
    and gate2 is only a floor.
    """
    if not comparisons:
        raise ValueError("rank_candidates needs at least one candidate")
    return sorted(
        range(len(comparisons)),
        key=lambda index: comparisons[index]["minimum"],
        reverse=True,
    )


def verdict(gate1_report: dict, gate2_report: dict) -> str:
    """Combine both gates into a single "pass" or "reject" verdict.

    There is no "flag" outcome: gate2 no longer measures against an
    absolute quality threshold (see gate2()'s docstring), so it only ever
    returns "pass" or "reject", and gate1 is a hard pass/fail on
    measurements. A three-way verdict would imply a middle judgement call
    that neither gate is designed to make.
    """
    if not gate1_report["ok"]:
        return "reject"
    return gate2_report["verdict"]
