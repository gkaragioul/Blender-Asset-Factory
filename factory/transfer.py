from __future__ import annotations

import json
from pathlib import Path

from .config import FactoryConfig
from .io import sha256_file


class TransferError(ValueError):
    pass


def index_models(config: FactoryConfig, hash_files: bool = False) -> dict:
    root = config.model_root.resolve(strict=True)
    models = []
    for path in sorted(
        config.model_root.rglob("*"), key=lambda item: item.as_posix().lower()
    ):
        relative = path.relative_to(config.model_root)
        if relative.parts and relative.parts[0].lower() == "manifests":
            continue
        resolved = path.resolve(strict=True)
        if not resolved.is_relative_to(root):
            raise TransferError(
                f"model link escapes model root: {relative.as_posix()}"
            )
        if not path.is_file():
            continue
        entry = {
            "relative_path": relative.as_posix(),
            "size": path.stat().st_size,
            "sha256": sha256_file(path) if hash_files else None,
        }
        sidecar = path.with_suffix(path.suffix + ".json")
        entry["metadata"] = (
            json.loads(sidecar.read_text(encoding="utf-8-sig"))
            if sidecar.is_file()
            else None
        )
        models.append(entry)
    return {
        "schema_version": 1,
        "model_root": str(config.model_root),
        "models": models,
    }


def build_transfer_manifest(config: FactoryConfig) -> dict:
    runtime_path = config.tooling_root / "runtime.json"
    runtime = (
        json.loads(runtime_path.read_text(encoding="utf-8-sig"))
        if runtime_path.is_file()
        else {}
    )
    entries = []
    for name in ("python", "uv"):
        value = runtime.get(name)
        if not value:
            continue
        path = Path(value)
        entries.append(
            {
                "kind": "runtime",
                "name": name,
                "path": value,
                "version": runtime.get(name + "_version"),
                "source": None,
                "license": None,
                "size": path.stat().st_size if path.is_file() else None,
                "sha256": sha256_file(path) if path.is_file() else None,
            }
        )
    return {
        "schema_version": 1,
        "root": str(config.root),
        "model_root": str(config.model_root),
        "entries": entries,
    }
