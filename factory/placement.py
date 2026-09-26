"""Placement and budget checks measured from the final runtime asset.

Conventions (adopted from the Muster WW2 archive's asset guide, MIT):
metres at 1:1 scale, +Y up, +Z forward, origin on the ground at the centre of
the footprint. Width is measured along X, height along Y, length along Z.

These checks read bounds measured in Three.js from the exported GLB, so they
see the file a buyer loads. gates._placement_failures polices the same idea
from retro_pass's own report, which only exists for retro conversions.

Every check that has an upper bound also has a lower bound: an empty asset
satisfies any ceiling, so zero triangles and zero draw calls always fail.
"""
from __future__ import annotations

import json
from pathlib import Path

DEFAULT_GROUND_TOLERANCE = 0.0005
DEFAULT_CENTRE_TOLERANCE = 0.005
DEFAULT_DIMENSION_TOLERANCE = 0.05
_AXES = {"width": 0, "height": 1, "length": 2}


class PlacementError(ValueError):
    pass


def resolve_expectations(root: Path, expectations: dict) -> dict:
    """Fill profile-derived defaults; explicit keys always win."""
    resolved = dict(expectations)
    profile_id = resolved.pop("profile", None)
    category = resolved.pop("category", None)
    if profile_id is None:
        return resolved
    profiles = (root / "profiles").resolve(strict=False)
    profile_path = (profiles / str(profile_id) / "profile.json").resolve(strict=False)
    if not profile_path.is_relative_to(profiles) or not profile_path.is_file():
        raise PlacementError(f"unknown profile: {profile_id}")
    profile = json.loads(profile_path.read_text(encoding="utf-8-sig"))
    placement = profile.get("placement", {})
    defaults = {
        "ground_tolerance": placement.get("ground_tolerance_m"),
        "centre_tolerance": placement.get("centre_tolerance_m"),
        "dimension_tolerance": placement.get("dimension_tolerance"),
    }
    if category is not None:
        band = profile.get("geometry", {}).get(f"{category}_triangles")
        if not (isinstance(band, list) and len(band) == 2):
            raise PlacementError(f"profile {profile_id} has no triangle band for category {category!r}")
        defaults["triangles"] = band
    for key, value in defaults.items():
        if value is not None:
            resolved.setdefault(key, value)
    return resolved


def check_measurements(measured: dict, expectations: dict) -> dict:
    failures: list[str] = []
    details: dict = {}
    bounds = measured.get("bounds") or {}
    minimum, maximum = bounds.get("min"), bounds.get("max")
    if not (isinstance(minimum, list) and isinstance(maximum, list) and len(minimum) == len(maximum) == 3):
        return {"passed": False, "failures": ["bounds_missing"], "details": details}

    size = {name: maximum[axis] - minimum[axis] for name, axis in _AXES.items()}
    details["size"] = size
    details["min_y"] = minimum[1]

    triangles = int(measured.get("triangle_count") or 0)
    draw_calls = int(measured.get("draw_calls") or 0)
    if triangles < 1:
        failures.append("no_geometry")
    if draw_calls < 1:
        failures.append("no_draw_calls")

    ground_tolerance = expectations.get("ground_tolerance", DEFAULT_GROUND_TOLERANCE)
    if abs(minimum[1]) > ground_tolerance:
        failures.append("not_grounded")

    centre_tolerance = expectations.get("centre_tolerance", DEFAULT_CENTRE_TOLERANCE)
    offset = {"x": (minimum[0] + maximum[0]) / 2, "z": (minimum[2] + maximum[2]) / 2}
    details["centre_offset"] = offset
    if centre_tolerance is not None and max(abs(offset["x"]), abs(offset["z"])) > centre_tolerance:
        failures.append("not_centred")

    band = expectations.get("triangles")
    if band is not None:
        low, high = band
        if triangles < low:
            failures.append("triangles_below_min")
        if triangles > high:
            failures.append("triangles_above_max")

    max_draw_calls = expectations.get("max_draw_calls")
    if max_draw_calls is not None and draw_calls > max_draw_calls:
        failures.append("draw_calls_above_max")

    tolerance = expectations.get("dimension_tolerance", DEFAULT_DIMENSION_TOLERANCE)
    for name, expected in (expectations.get("dimensions") or {}).items():
        if name not in _AXES:
            raise PlacementError(f"unknown dimension {name!r}; use width (X), height (Y) or length (Z)")
        if abs(size[name] - expected) > abs(expected) * tolerance:
            failures.append(f"{name}_out_of_range")

    return {"passed": not failures, "failures": failures, "details": details}
