from __future__ import annotations

import json
from pathlib import Path

from .blender import run_blender_script
from .config import FactoryConfig
from .png import decode_rgba

SCRIPT = Path(__file__).resolve().parent / "scripts" / "silhouette_render.py"
RESOLUTION = 256
LUMA_THRESHOLD = 32

# Gate render_masks output on 0%/100% coverage only (with a hair of
# tolerance for float roundoff), NOT on some larger "looks too thin/thick"
# floor. A legitimate silhouette can measure well under 1% coverage (the
# trenchgun's own azimuth-0 view does, at ~0.5% before the VIEWS offset fix,
# and ~2-5% after it) -- a floor tight enough to reject a broken render
# would also reject valid work. This only exists to catch the genuinely
# degenerate case: a scene-setup regression that renders nothing, or
# renders everything, for every mesh in a pack.
_DEGENERATE_COVERAGE = 0.001

# Eight fixed views: six around the equator (alternating level and slightly
# elevated, 45 degrees apart in azimuth) plus one steep top-down view. There
# is deliberately no view looking up from underneath -- see the report for
# why that blind spot is judged acceptable for this pipeline's assets.
#
# The azimuths are offset 22.5 degrees off the axes (22.5, 67.5, 112.5, ...)
# rather than starting at 0/45/90/... on purpose. Game assets are
# overwhelmingly modelled axis-aligned to their own local X/Y/Z, so a
# view set that starts exactly on an axis is the single worst choice for
# a *general* fixed-view rig: it is precisely the angle most likely to look
# straight down an asset's own length (measured on the trenchgun fixture,
# azimuth 0 looks almost directly down the barrel, giving under 1% visible
# coverage -- see task-9-report for the render). Offsetting by a constant
# keeps every view meaningfully oblique to any axis-aligned asset without
# changing the view count or spacing.
VIEWS: tuple[tuple[float, float], ...] = (
    (22.5, 0.0),
    (67.5, 20.0),
    (112.5, 0.0),
    (157.5, 20.0),
    (202.5, 0.0),
    (247.5, 20.0),
    (292.5, 0.0),
    (22.5, 89.0),
)


class SilhouetteError(RuntimeError):
    pass


def mask_from_png(data: bytes) -> tuple[int, bytes]:
    width, _height, rgba = decode_rgba(data)
    mask = bytearray(len(rgba) // 4)
    for index in range(0, len(rgba), 4):
        luma = (rgba[index] * 299 + rgba[index + 1] * 587 + rgba[index + 2] * 114) // 1000
        mask[index // 4] = 1 if luma >= LUMA_THRESHOLD else 0
    return width, bytes(mask)


def iou(first: bytes, second: bytes) -> float:
    if len(first) != len(second):
        raise ValueError(
            f"masks must be the same size: {len(first)} vs {len(second)} pixels"
        )
    intersection = 0
    union = 0
    for a, b in zip(first, second):
        if a and b:
            intersection += 1
        if a or b:
            union += 1
    if union == 0:
        # Two blank masks. This used to be defended by an assertion that
        # ONLY ran in a test, against ONLY the raw trenchgun -- i.e. not at
        # all in production. render_masks (below) now raises SilhouetteError
        # itself on any degenerate (all-blank or all-solid) render, using
        # the coverage silhouette_render.py measures at render time, so a
        # blank-vs-blank pair reaching compare() through the real
        # render_masks -> compare pipeline means that guard already fired
        # and stopped the pipeline before compare() was ever called. A
        # caller that builds masks some OTHER way (bypassing render_masks)
        # is not covered by that guard -- see task-9-report's Correctness
        # Question 2 for that residual risk.
        return 1.0
    return intersection / union


def _coverage(mask: bytes) -> float:
    return sum(mask) / len(mask) if mask else 0.0


def compare(raw_masks: list[bytes], ps1_masks: list[bytes]) -> dict:
    if len(raw_masks) != len(ps1_masks):
        raise ValueError(
            f"view count mismatch: {len(raw_masks)} raw vs {len(ps1_masks)} converted"
        )
    scores = [iou(raw, ps1) for raw, ps1 in zip(raw_masks, ps1_masks)]
    return {
        "per_view": scores,
        "minimum": min(scores),
        "mean": sum(scores) / len(scores),
        # Per-view coverage of the inputs actually compared, so a caller
        # (Gate 2) can tell a low IoU caused by real shape divergence apart
        # from one caused by a near-degenerate mask, without re-decoding
        # the source PNGs itself.
        "raw_coverage": [_coverage(mask) for mask in raw_masks],
        "ps1_coverage": [_coverage(mask) for mask in ps1_masks],
    }


def render_masks(
    config: FactoryConfig,
    source: Path,
    output_dir: Path,
    report_path: Path,
    *,
    radius: float | None = None,
) -> tuple[Path, ...]:
    """Render `source` from the 8 fixed VIEWS and return the PNG paths.

    `source` is imported fresh into a new Blender session -- for a converted
    asset this MUST be the exported GLB on disk, never the in-Blender scene
    that produced it, so the render reflects exactly what the pipeline
    shipped (see task-9-report for why this matters given the known
    invalid-mesh export defect).

    Each render is always centred on `source`'s OWN world-space bounds
    centre: the conversion pipeline's normalize stage repositions and
    reorients meshes (recentring on a grid-snapped origin, rotating to the
    contract's up axis), so a raw source and its converted output do not
    share a world-space position even when the shape is unchanged. Forcing
    a shared centre would frame one of the two renders off to the side for
    reasons that have nothing to do with silhouette quality.

    `radius` is the one framing quantity that IS meant to be shared: pass
    the radius read back from a prior render_masks() report (see
    `effective_radius`) to force both the raw and converted renders to use
    the same camera distance and orthographic scale. Without this, a
    converted mesh with slightly different bounds gets a slightly
    different zoom level, and IoU is depressed by a framing mismatch
    rather than by actual shape loss.
    """
    config.require_owned_path(output_dir)
    payload = {
        "source": str(source),
        "output_dir": str(output_dir),
        "resolution": RESOLUTION,
        "views": [list(view) for view in VIEWS],
        "radius_override": radius,
    }
    report = run_blender_script(config, SCRIPT, payload, report_path)
    if not report.get("ok"):
        raise SilhouetteError(f"silhouette render failed: {report.get('error')}")
    paths = tuple(Path(item) for item in report["renders"])
    if len(paths) != len(VIEWS):
        raise SilhouetteError(
            f"expected {len(VIEWS)} renders, got {len(paths)}"
        )
    coverage = report.get("coverage") or []
    if len(coverage) != len(paths):
        raise SilhouetteError(
            f"expected {len(paths)} per-view coverage readings, got {len(coverage)}"
        )
    degenerate = [
        (index, value)
        for index, value in enumerate(coverage)
        if value <= _DEGENERATE_COVERAGE or value >= 1.0 - _DEGENERATE_COVERAGE
    ]
    if degenerate:
        # A blank or fully-solid render is not a shape measurement, it is a
        # broken scene: wrong camera, missing geometry, a shading/world
        # setting that stopped painting the mesh white on black (see
        # silhouette_render.py's scene setup for what those settings are
        # pinned against). Left unguarded, EVERY blank-vs-blank or
        # solid-vs-solid pair scores compare()'s IoU as a perfect 1.0 (see
        # iou()'s union==0 branch, and the mirror-image solid case where
        # intersection == union == every pixel) -- silently certifying a
        # broken render as a flawless conversion. Raising here, at the one
        # place that has directly measured coverage, is what makes that
        # 1.0 trustworthy everywhere else.
        names = ", ".join(
            f"view {index} ({paths[index].name}): {value:.4%} lit"
            for index, value in degenerate
        )
        raise SilhouetteError(
            f"degenerate render(s) for {source}: {names} "
            f"(want strictly between {_DEGENERATE_COVERAGE:.3%} and "
            f"{1.0 - _DEGENERATE_COVERAGE:.3%} lit)"
        )
    return paths


def effective_radius(report_path: Path) -> float:
    """Read back the framing radius a prior render_masks() call used.

    Pass the result as `radius=` to a second render_masks() call so both
    renders share the same camera distance and orthographic scale.
    """
    data = json.loads(report_path.read_text(encoding="utf-8"))
    return float(data["radius"])
