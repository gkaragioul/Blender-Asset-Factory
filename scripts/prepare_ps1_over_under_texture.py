"""Reduce the source-derived shotgun atlas to an authentic PS1-era texture.

Produces a small, hard-dithered, indexed-style palette texture instead of a
smooth modern PBR base color map.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image

TEXTURE_SIZE = 128
COLORS = 24


def prepare_ps1_texture(source_path: Path, output_path: Path) -> Path:
    image = Image.open(source_path).convert("RGB")
    image = image.resize((TEXTURE_SIZE, TEXTURE_SIZE), Image.Resampling.NEAREST)
    quantized = image.quantize(colors=COLORS, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.FLOYDSTEINBERG)
    final = quantized.convert("RGB")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    final.save(output_path, format="PNG")
    return output_path


def main() -> None:
    args = sys.argv[1:]
    if len(args) != 2:
        raise SystemExit("usage: prepare_ps1_over_under_texture.py SOURCE_PNG OUTPUT_PNG")
    source_path, output_path = Path(args[0]).resolve(), Path(args[1]).resolve()
    result = prepare_ps1_texture(source_path, output_path)
    print(f"PS1_TEXTURE_RESULT={result}")


if __name__ == "__main__":
    main()
