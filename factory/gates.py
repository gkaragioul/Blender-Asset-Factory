from __future__ import annotations

import json
import struct

from .palette import conformance, load_palette
from .png import decode_rgba
from .style_contract import StyleContract

GATE2_CATASTROPHE = 0.45

# ---------------------------------------------------------------------------
# LOWER BOUNDS -- why this section exists at all
#
# Five times on this branch an automated check has been proven blind, and they
# were all one defect. Gate 1 was composed entirely of UPPER BOUNDS
# (`triangles <= budget`) and SET-MEMBERSHIP TESTS (every texel is in the
# palette), and Gate 2 is a RELATIVE measure between an asset and itself. An
# upper bound is satisfied by zero. A membership test is satisfied by a
# constant -- one colour is trivially a subset of any palette. A relative
# measure is invariant to a defect present on both sides. So "nothing" passes
# all three families, and there is no fourth family to add.
#
# The escapes so far: a black texture passing palette conformance; flat
# per-part base colours passing the "carries detail" check; a solid slab
# replacing a cutout passing both gates; a wiped atlas passing conformance;
# and the per-material black bake that the aggregate `_bake_wrote_nothing`
# check missed.
#
# retro_pass already MEASURES everything needed to catch all of them and pack
#.py used to discard the report entirely. These constants close that. Every
# one is justified against the measured trenchgun conversion (45,881 -> 2,470
# triangles at 256px, reported in .superpowers/sdd/.../progress.md), and every
# one has a test proving it FAILS on the degenerate input.
# ---------------------------------------------------------------------------

# Measured: the smallest real part (Cartridge) claimed 187 atlas texels. A
# floor of 1 sits 187x below that, so it cannot reject a legitimately small
# part; what it does reject is a part shipping with NO texture at all, which
# is the per-material black bake the aggregate check cannot see.
MIN_PART_TEXELS = 1

# Measured: the real conversion used 8 distinct colours out of an 8-entry
# palette -- full utilisation. A black texture scores 1; a single flat colour
# scores 1 (or 2 with the untouched background). 3 is comfortably below the
# measurement and above every degenerate case. Clamped to the palette size so
# a deliberately tiny palette cannot fail by construction.
MIN_DISTINCT_COLOURS = 3

# Measured: atlas_coverage 0.0729 (4,779 of 65,536 texels). A wiped or
# never-built atlas scores exactly 0. 0.005 is a 14.6x margin below the
# measurement -- deliberately generous, because the job of a lower bound here
# is to catch NOTHING, not to grade layout efficiency.
MIN_ATLAS_COVERAGE = 0.005

# Measured: the grounded base sat at y = 1.66e-09 and both horizontal centres
# at exactly 0.0. 1e-4 is far above float noise and far below anything a real
# normalize regression produces -- the rotation defect put the grounded extent
# on an entirely different axis.
PLACEMENT_TOLERANCE = 1e-4

# glTF's sampler filter enum. The contract's `filtering: "nearest"` is what
# gives PS1 texels their hard edges; LINEAR (9729) or an absent sampler
# silently blurs the whole pack.
NEAREST_FILTER = 9728

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


def _placement_failures(retro_report: dict, contract: StyleContract, details: dict) -> list[str]:
    """Police grid alignment and grounding from retro_pass's own bounds.

    This is a PRIMARY quality claim of the pack: 30 assets sit together in one
    scene only because each one's base is on the ground plane and its
    horizontal footprint is centred on a `grid_unit` multiple. Nothing checked
    it. `grep grid_unit factory/gates.py factory/pack.py` returned nothing.

    It cannot be delegated to Gate 2. Silhouette IoU frames each render on its
    OWN bounding box -- deliberately, so the comparison is translation
    invariant -- which makes it structurally blind to pivot and grounding. The
    Y-up rotation defect broke grounding and Gate 2 saw only the shape change.
    So this has to be policed from the reported bounds or not at all, and "not
    at all" means a normalize regression ships 30 misaligned assets with both
    gates green.

    Note the frame: retro_pass rotates the scene into the contract's declared
    up axis BEFORE measuring, so for `up_axis: "Y"` the reported up axis is y
    and x/z are the horizontal pair -- the same frame the exported GLB
    carries.
    """
    bounds = retro_report.get("bounds") or {}
    minimum = bounds.get("min")
    maximum = bounds.get("max")
    if not isinstance(minimum, dict) or not isinstance(maximum, dict):
        details["placement"] = {"bounds": None}
        return ["bounds_missing"]

    up = "y" if contract.up_axis == "Y" else "z"
    horizontal = [axis for axis in ("x", "y", "z") if axis != up]
    failures: list[str] = []

    base = float(minimum[up])
    grounded = abs(base) <= PLACEMENT_TOLERANCE
    if not grounded:
        failures.append("grounding")

    centres = {}
    aligned = True
    for axis in horizontal:
        centre = (float(minimum[axis]) + float(maximum[axis])) / 2
        snapped = round(centre / contract.grid_unit) * contract.grid_unit
        centres[axis] = centre
        if abs(centre - snapped) > PLACEMENT_TOLERANCE:
            aligned = False
    if not aligned:
        failures.append("grid_alignment")

    details["placement"] = {
        "up_axis": up,
        "base": base,
        "grounded": grounded,
        "grid_unit": contract.grid_unit,
        "horizontal_centres": centres,
        "grid_aligned": aligned,
        "tolerance": PLACEMENT_TOLERANCE,
    }
    return failures


def _lower_bound_failures(retro_report: dict, contract: StyleContract, details: dict) -> list[str]:
    """The lower bounds a degenerate asset cannot satisfy. See the constants."""
    stages = retro_report.get("stages") or {}
    texture = retro_report.get("texture") or {}
    failures: list[str] = []

    per_part = stages.get("uv_texels_per_part")
    smallest = min(per_part.values()) if isinstance(per_part, dict) and per_part else 0
    if smallest < MIN_PART_TEXELS:
        # Kills a part that shipped with no texture region at all -- the
        # per-material black bake that the aggregate _bake_wrote_nothing check
        # cannot see, because six healthy materials outvote one dead one.
        failures.append("empty_part_texture")

    texels = contract.texture_size * contract.texture_size
    covered = stages.get("uv_covered_cells")
    coverage = (covered / float(texels)) if isinstance(covered, int) else 0.0
    if coverage < MIN_ATLAS_COVERAGE:
        failures.append("atlas_coverage")

    # Converts the tracked "cutout mask lost, degrades silently to OPAQUE"
    # launch blocker into a hard failure. The source declared alpha sources;
    # if the shipped material does not declare MASK, the cutout became a solid
    # slab -- which is exactly what neither gate could previously detect.
    alpha_sources = stages.get("alpha_sources") or []
    alpha_mode = texture.get("alpha_mode")
    if alpha_sources and alpha_mode != "MASK":
        failures.append("alpha_mode")

    details["lower_bounds"] = {
        "smallest_part_texels": smallest,
        "min_part_texels": MIN_PART_TEXELS,
        "atlas_coverage": round(coverage, 6),
        "min_atlas_coverage": MIN_ATLAS_COVERAGE,
        "alpha_sources": sorted(alpha_sources),
        "alpha_mode": alpha_mode,
        "reported_distinct_colours": texture.get("distinct_colours"),
    }
    return failures


def gate1(
    glb_bytes: bytes,
    contract: StyleContract,
    role: str,
    triangles: int,
    validator_ok: bool,
    preview_ok: bool,
    retro_report: dict,
) -> dict:
    """Hard pass/fail on the shipped GLB plus retro_pass's measurements.

    `retro_report` is REQUIRED, not optional. Making it default to None would
    mean a caller that forgot it silently loses every lower bound below --
    which is precisely how the blind spots this gate now closes came about.
    """
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

    # The spec's Gate 1 requires "Texture is exactly texture_size, nearest
    # filtering". Only the drop_maps half of that sentence was implemented, so
    # nothing independently verified the SHIPPED texture -- its size and
    # filtering were asserted only inside the tests of the code that produces
    # it, which is the generator-grades-itself pattern this project exists to
    # avoid. Decoded from the GLB's own bytes here.
    #
    # Distinct colours are measured HERE too rather than read from the retro
    # report, for the same reason: a lower bound sourced from the generator is
    # only as trustworthy as the generator. The reported figure is kept in
    # details for cross-reference.
    dimensions: list[list[int]] = []
    distinct: set[tuple[int, int, int]] = set()
    for image in images:
        width, height, rgba = decode_rgba(image)
        dimensions.append([width, height])
        for index in range(0, len(rgba), 4):
            distinct.add((rgba[index], rgba[index + 1], rgba[index + 2]))
        if width != contract.texture_size or height != contract.texture_size:
            failures.append("texture_size")
    details["texture_dimensions"] = dimensions
    details["contract_texture_size"] = contract.texture_size

    # Clamped to the palette: a pack whose palette holds fewer entries than
    # the floor could otherwise never satisfy it.
    distinct_floor = min(MIN_DISTINCT_COLOURS, len(palette))
    details["distinct_colours"] = len(distinct)
    details["min_distinct_colours"] = distinct_floor
    if images and len(distinct) < distinct_floor:
        failures.append("texture_detail")

    # Every texture must sample NEAREST. An absent sampler is a failure, not a
    # pass: glTF leaves the default filter implementation-defined, and every
    # real runtime picks a linear one.
    samplers = document.get("samplers", [])
    filters: list = []
    for texture_entry in document.get("textures", []):
        index = texture_entry.get("sampler")
        sampler = samplers[index] if isinstance(index, int) and index < len(samplers) else {}
        filters.append(sampler.get("magFilter"))
    if not filters or any(value != NEAREST_FILTER for value in filters):
        failures.append("texture_filtering")
    details["mag_filters"] = filters
    details["required_mag_filter"] = NEAREST_FILTER

    failures.extend(_placement_failures(retro_report, contract, details))
    failures.extend(_lower_bound_failures(retro_report, contract, details))

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
