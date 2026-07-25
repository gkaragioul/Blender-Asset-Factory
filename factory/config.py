from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parents[1]


class ConfigurationError(ValueError):
    pass


@dataclass(frozen=True)
class FactoryConfig:
    root: Path
    model_root: Path
    tooling_root: Path
    reports_root: Path
    bridge_url: str
    blender_candidates: tuple[Path, ...]

    @classmethod
    def load(cls, path: Path | None = None) -> "FactoryConfig":
        source = path or PACKAGE_ROOT / "factory" / "config.json"
        data = json.loads(source.read_text(encoding="utf-8-sig"))
        required = {
            "schema_version",
            "root",
            "model_root",
            "tooling_root",
            "reports_root",
            "bridge_url",
            "blender_candidates",
        }
        if data.keys() != required:
            raise ConfigurationError(
                f"configuration keys must be exactly {sorted(required)}"
            )
        if data["schema_version"] != 1:
            raise ConfigurationError("configuration schema_version must be 1")

        source_root = source.resolve().parents[1]

        def owned(value: str) -> Path:
            candidate = Path(value)
            return (
                candidate
                if candidate.is_absolute()
                else source_root / candidate
            ).resolve(strict=False)

        config = cls(
            root=owned(data["root"]),
            model_root=Path(data["model_root"]).resolve(strict=False),
            tooling_root=owned(data["tooling_root"]),
            reports_root=owned(data["reports_root"]),
            bridge_url=data["bridge_url"],
            blender_candidates=tuple(
                Path(item) for item in data["blender_candidates"]
            ),
        )
        canonical_root = source_root
        trusted_worktrees = canonical_root / ".worktrees"
        if (
            config.root != canonical_root
            and trusted_worktrees not in config.root.parents
        ):
            raise ConfigurationError(
                "root must be canonical or a trusted worktree beneath "
                f"{trusted_worktrees}"
            )
        for owned_path in (
            config.root,
            config.model_root,
            config.tooling_root,
            config.reports_root,
        ):
            config.require_owned_path(owned_path)
        if config.bridge_url != "http://127.0.0.1:9876":
            raise ConfigurationError("bridge must bind to loopback port 9876")
        return config

    def require_owned_path(self, path: Path) -> Path:
        resolved = path.resolve(strict=False)
        owned_roots = (self.root, self.model_root)
        if not any(resolved == root or root in resolved.parents for root in owned_roots):
            raise ConfigurationError(
                f"factory-owned path must be beneath the factory root or model root: {resolved}"
            )
        return resolved
