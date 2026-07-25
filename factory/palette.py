from __future__ import annotations

from collections import Counter
from pathlib import Path

from .png import decode_rgba

Colour = tuple[int, int, int]
MAX_FOREIGN_COLOURS_REPORTED = 16


class PaletteError(ValueError):
    pass


def load_palette(path: Path) -> tuple[Colour, ...]:
    _width, _height, rgba = decode_rgba(path.read_bytes())
    colours = {
        (rgba[index], rgba[index + 1], rgba[index + 2])
        for index in range(0, len(rgba), 4)
        if rgba[index + 3] == 255
    }
    if not colours:
        raise PaletteError(f"palette {path} contains no opaque pixels")
    return tuple(sorted(colours))


def nearest(colour: Colour, palette: tuple[Colour, ...]) -> Colour:
    def distance(candidate: Colour) -> int:
        return sum((a - b) ** 2 for a, b in zip(colour, candidate))

    return min(palette, key=distance)


def conformance(png_bytes: bytes, palette: tuple[Colour, ...]) -> dict:
    _width, _height, rgba = decode_rgba(png_bytes)
    allowed = set(palette)
    foreign: Counter[Colour] = Counter()
    total = len(rgba) // 4
    for index in range(0, len(rgba), 4):
        colour = (rgba[index], rgba[index + 1], rgba[index + 2])
        if colour not in allowed:
            foreign[colour] += 1
    return {
        "ok": not foreign,
        "pixels": total,
        "foreign_pixels": sum(foreign.values()),
        "foreign_colours": [
            list(colour)
            for colour, _count in foreign.most_common(MAX_FOREIGN_COLOURS_REPORTED)
        ],
    }
