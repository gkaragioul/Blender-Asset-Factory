from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from .config import FactoryConfig

ALLOWED_DROP_MAPS = ("normal", "roughness", "metallic", "emissive", "occlusion")
REQUIRED_KEYS = {
    "schema_version",
    "palette",
    "texture_size",
    "filtering",
    "polycount_bands",
    "grid_unit",
    "up_axis",
    "drop_maps",
    "vertex_light_bake",
}


class StyleContractError(ValueError):
    pass


@dataclass(frozen=True)
class StyleContract:
    palette: Path
    texture_size: int
    filtering: str
    polycount_bands: tuple[tuple[str, int], ...]
    grid_unit: float
    up_axis: str
    drop_maps: tuple[str, ...]
    vertex_light_bake: bool

    @classmethod
    def load(cls, config: FactoryConfig, path: Path) -> "StyleContract":
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        if data.keys() != REQUIRED_KEYS:
            raise StyleContractError(
                f"style contract keys must be exactly {sorted(REQUIRED_KEYS)}"
            )
        if data["schema_version"] != 1:
            raise StyleContractError("style contract schema_version must be 1")
        if data["filtering"] != "nearest":
            raise StyleContractError("filtering must be 'nearest' for PS1 packs")
        if data["up_axis"] not in ("Y", "Z"):
            raise StyleContractError("up_axis must be 'Y' or 'Z'")
        if data["texture_size"] not in (64, 128, 256, 512):
            raise StyleContractError("texture_size must be 64, 128, 256 or 512")
        if not isinstance(data["polycount_bands"], dict) or not data["polycount_bands"]:
            raise StyleContractError("polycount_bands must be a non-empty object")
        for role, budget in data["polycount_bands"].items():
            if not isinstance(budget, int) or budget < 1:
                raise StyleContractError(f"band for role {role!r} must be a positive integer")
        for name in data["drop_maps"]:
            if name not in ALLOWED_DROP_MAPS:
                raise StyleContractError(f"unknown drop map {name!r}")
        if float(data["grid_unit"]) <= 0:
            raise StyleContractError("grid_unit must be positive")

        palette = (path.parent / data["palette"]).resolve(strict=False)
        if not palette.is_file():
            raise StyleContractError(f"palette file does not exist: {palette}")

        return cls(
            palette=palette,
            texture_size=data["texture_size"],
            filtering=data["filtering"],
            polycount_bands=tuple(sorted(data["polycount_bands"].items())),
            grid_unit=float(data["grid_unit"]),
            up_axis=data["up_axis"],
            drop_maps=tuple(sorted(data["drop_maps"])),
            vertex_light_bake=bool(data["vertex_light_bake"]),
        )

    def band_for(self, role: str) -> int:
        for name, budget in self.polycount_bands:
            if name == role:
                return budget
        raise StyleContractError(
            f"unknown role {role!r}; known roles are "
            f"{[name for name, _ in self.polycount_bands]}"
        )

    def as_payload(self) -> dict:
        return {
            "texture_size": self.texture_size,
            "filtering": self.filtering,
            "polycount_bands": {name: budget for name, budget in self.polycount_bands},
            "grid_unit": self.grid_unit,
            "up_axis": self.up_axis,
            "drop_maps": list(self.drop_maps),
            "vertex_light_bake": self.vertex_light_bake,
        }

    def digest(self) -> str:
        material = json.dumps(self.as_payload(), sort_keys=True).encode("utf-8")
        palette_bytes = self.palette.read_bytes()
        return hashlib.sha256(material + palette_bytes).hexdigest()
