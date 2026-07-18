from __future__ import annotations

import json
import subprocess
from pathlib import Path

from .config import FactoryConfig
from .gltf_inspection import inspect_glb
from .io import atomic_write_json, sha256_file


class GltfValidationError(ValueError):
    pass


def _release_runtime(config: FactoryConfig) -> dict:
    path = config.tooling_root / "release-runtime.json"
    if not path.is_file():
        raise GltfValidationError("release runtime unavailable; run bootstrap/setup-release.ps1")
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _require_factory_input(config: FactoryConfig, path: Path) -> Path:
    source = config.require_owned_path(path).resolve(strict=True)
    allowed = (config.root.resolve(strict=False), config.model_root.resolve(strict=False))
    if not any(source == root or source.is_relative_to(root) for root in allowed):
        raise GltfValidationError(f"input is outside factory and model roots: {source}")
    return source


def validate_glb(config: FactoryConfig, source: Path, report_path: Path) -> dict:
    input_path = _require_factory_input(config, source)
    output_path = config.require_owned_path(report_path)
    runtime = _release_runtime(config)
    node = Path(runtime.get("node", ""))
    node_modules = Path(runtime.get("node_modules", ""))
    adapter = config.root / "tools" / "release-node" / "validate-gltf.mjs"
    if not node.is_file() or not node_modules.is_dir():
        raise GltfValidationError("pinned Node validator dependencies are unavailable")
    if not adapter.is_file():
        raise GltfValidationError(f"validator adapter is unavailable: {adapter}")
    completed = subprocess.run(
        [str(node), str(adapter), str(input_path), str(node_modules)],
        cwd=config.root,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if completed.returncode != 0:
        raise GltfValidationError(
            f"validator process failed ({completed.returncode}): {completed.stderr.strip()}"
        )
    try:
        validator_report = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise GltfValidationError(f"validator returned invalid JSON: {error}") from error
    issues = validator_report.get("issues", {})
    errors = int(issues.get("numErrors", 0))
    report = {
        "schema_version": 1,
        "ok": errors == 0,
        "input": str(input_path),
        "input_sha256": sha256_file(input_path),
        "validator_version": validator_report.get("validatorVersion"),
        "issues": issues,
        "info": validator_report.get("info", {}),
        "inspection": inspect_glb(input_path),
    }
    atomic_write_json(output_path, report)
    if errors:
        raise GltfValidationError(f"glTF validation reported {errors} error(s)")
    return report
