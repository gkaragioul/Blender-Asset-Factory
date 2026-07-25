from __future__ import annotations

import unittest
import zipfile
from pathlib import Path

from factory.png import encode_rgba
from tests.temp_paths import temporary_root

# A small, deliberately PS1-ish ramp: two four-step ramps (warm wood, cool
# steel) which is the whole vocabulary a trenchgun needs. Shared by every
# test that runs retro_pass.py so the geometry and texture suites quantize
# against the same palette.
RETRO_PALETTE_COLOURS = (
    (20, 18, 16), (60, 52, 42), (104, 82, 56), (146, 118, 82),
    (44, 46, 44), (86, 92, 86), (132, 138, 130), (188, 192, 186),
)

ARCHIVE_CANDIDATES = (
    Path(__file__).resolve().parents[2] / ".hermes" / "desktop-attachments" / "m1897-trenchgun.zip",
    Path(__file__).resolve().parents[1] / ".hermes" / "desktop-attachments" / "m1897-trenchgun.zip",
)


class FixtureUnavailable(unittest.SkipTest):
    pass


def retro_palette_png(directory: Path) -> Path:
    """Write the shared test palette into `directory` and return its path."""
    rgba = bytearray()
    for colour in RETRO_PALETTE_COLOURS:
        rgba.extend((*colour, 255))
    path = directory / "palette.png"
    path.write_bytes(
        encode_rgba(len(RETRO_PALETTE_COLOURS), 1, bytes(rgba))
    )
    return path


def trenchgun_fbx() -> Path:
    destination = temporary_root() / "fixtures" / "m1897-trenchgun"
    target = destination / "source" / "trenchgun.fbx"
    if target.is_file():
        return target
    archive = next((path for path in ARCHIVE_CANDIDATES if path.is_file()), None)
    if archive is None:
        raise FixtureUnavailable(
            "m1897-trenchgun.zip was not found; looked in "
            + ", ".join(str(path) for path in ARCHIVE_CANDIDATES)
        )
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as bundle:
        bundle.extractall(destination)
    if not target.is_file():
        raise FixtureUnavailable(f"{archive} does not contain source/trenchgun.fbx")
    return target
