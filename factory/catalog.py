from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .config import FactoryConfig
from .style_contract import StyleContract, StyleContractError

REQUIRED_KEYS = {
    "schema_version",
    "pack_id",
    "style_contract",
    "max_generations",
    "max_rerolls",
    "assets",
}
IDENTIFIER = "abcdefghijklmnopqrstuvwxyz0123456789_"


class CatalogError(ValueError):
    pass


@dataclass(frozen=True)
class CatalogEntry:
    id: str
    lane: str
    role: str
    prompt: str | None
    reference_brief: str | None


@dataclass(frozen=True)
class Catalog:
    pack_id: str
    style_contract: Path
    max_generations: int
    max_rerolls: int
    entries: tuple[CatalogEntry, ...]

    @classmethod
    def load(
        cls,
        config: FactoryConfig,
        path: Path,
        contract: StyleContract,
    ) -> "Catalog":
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        if data.keys() != REQUIRED_KEYS:
            raise CatalogError(f"catalog keys must be exactly {sorted(REQUIRED_KEYS)}")
        if data["schema_version"] != 1:
            raise CatalogError("catalog schema_version must be 1")
        if set(data["pack_id"]) - set(IDENTIFIER):
            raise CatalogError("pack_id must be lowercase alphanumeric with underscores")
        for field in ("max_generations", "max_rerolls"):
            if not isinstance(data[field], int) or data[field] < 1:
                raise CatalogError(f"{field} must be a positive integer")
        if not data["assets"]:
            raise CatalogError("catalog must declare at least one asset")

        entries: list[CatalogEntry] = []
        seen: set[str] = set()
        for asset in data["assets"]:
            identifier = asset.get("id", "")
            if not identifier or set(identifier) - set(IDENTIFIER):
                raise CatalogError(f"invalid asset id {identifier!r}")
            if identifier in seen:
                raise CatalogError(f"duplicate asset id {identifier!r}")
            seen.add(identifier)

            lane = asset.get("lane")
            if lane not in ("A", "B"):
                raise CatalogError(f"asset {identifier!r} lane must be 'A' or 'B'")

            role = asset.get("role", "")
            try:
                contract.band_for(role)
            except StyleContractError as error:
                raise CatalogError(
                    f"asset {identifier!r} role {role!r} is not in the style contract: {error}"
                ) from error

            prompt = asset.get("prompt")
            brief = asset.get("reference_brief")
            if lane == "A" and (not prompt or brief):
                raise CatalogError(
                    f"asset {identifier!r} is lane A and must declare 'prompt' "
                    "and must not declare 'reference_brief'"
                )
            if lane == "B" and (not brief or prompt):
                raise CatalogError(
                    f"asset {identifier!r} is lane B and must declare "
                    "'reference_brief' and must not declare 'prompt'"
                )

            unexpected = set(asset) - {"id", "lane", "role", "prompt", "reference_brief"}
            if unexpected:
                raise CatalogError(
                    f"asset {identifier!r} has unexpected keys {sorted(unexpected)}"
                )

            entries.append(
                CatalogEntry(
                    id=identifier,
                    lane=lane,
                    role=role,
                    prompt=prompt,
                    reference_brief=brief,
                )
            )

        return cls(
            pack_id=data["pack_id"],
            style_contract=(path.parent / data["style_contract"]).resolve(strict=False),
            max_generations=data["max_generations"],
            max_rerolls=data["max_rerolls"],
            entries=tuple(entries),
        )
