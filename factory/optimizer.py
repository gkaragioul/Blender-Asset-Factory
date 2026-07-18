from __future__ import annotations

import json
import subprocess
from pathlib import Path

from .config import FactoryConfig
from .gltf_validation import GltfValidationError, _require_factory_input, validate_glb
from .io import atomic_write_json, sha256_file


class OptimizationError(ValueError):
    pass


def _uv_drift(source: dict, derivative: dict, required: bool) -> float:
    source_uv = source.get("texcoord_bounds", {})
    derivative_uv = derivative.get("texcoord_bounds", {})
    if required and (not source_uv or source_uv.keys() != derivative_uv.keys()):
        raise OptimizationError("pixel-atlas UV evidence is missing or changed channels")
    differences: list[float] = []
    for channel, source_bounds in source_uv.items():
        output_bounds = derivative_uv.get(channel)
        if not output_bounds:
            raise OptimizationError(f"optimized derivative dropped TEXCOORD_{channel}")
        if source_bounds["count"] != output_bounds["count"]:
            raise OptimizationError(f"optimized derivative changed TEXCOORD_{channel} count")
        for key in ("min", "max"):
            differences.extend(
                abs(float(left) - float(right))
                for left, right in zip(source_bounds[key], output_bounds[key])
            )
    return max(differences, default=0.0)


def optimize_glb(
    config: FactoryConfig,
    source: Path,
    destination: Path,
    report_path: Path,
    *,
    pixel_atlas: bool = False,
    uv_tolerance: float = 1e-6,
) -> dict:
    input_path = _require_factory_input(config, source)
    output_path = config.require_owned_path(destination).resolve(strict=False)
    report_output = config.require_owned_path(report_path).resolve(strict=False)
    if input_path == output_path:
        raise OptimizationError("authoritative source and derivative output must differ")
    root = config.root.resolve(strict=False)
    if not output_path.is_relative_to(root):
        raise OptimizationError("optimized derivatives must be written beneath the factory root")
    if output_path.exists():
        raise OptimizationError(f"refusing to overwrite existing derivative: {output_path}")
    runtime_path = config.tooling_root / "release-runtime.json"
    if not runtime_path.is_file():
        raise OptimizationError("release runtime unavailable")
    runtime = json.loads(runtime_path.read_text(encoding="utf-8-sig"))
    gltfpack = Path(runtime.get("gltfpack", ""))
    if not gltfpack.is_file():
        raise OptimizationError("pinned gltfpack executable is unavailable")

    report_output.parent.mkdir(parents=True, exist_ok=True)
    source_validation_path = report_output.with_name(report_output.stem + "-source-validation.json")
    derivative_validation_path = report_output.with_name(report_output.stem + "-derivative-validation.json")
    source_validation = validate_glb(config, input_path, source_validation_path)
    command = [str(gltfpack), "-i", str(input_path), "-o", str(output_path), "-ke"]
    if pixel_atlas:
        command.append("-vtf")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(command, cwd=config.root, capture_output=True, text=True, timeout=300)
    if completed.returncode != 0 or not output_path.is_file():
        if output_path.is_file():
            output_path.unlink()
        raise OptimizationError(
            f"gltfpack failed ({completed.returncode}): {(completed.stderr or completed.stdout).strip()}"
        )
    try:
        derivative_validation = validate_glb(config, output_path, derivative_validation_path)
        drift = _uv_drift(source_validation["inspection"], derivative_validation["inspection"], pixel_atlas)
        if drift > uv_tolerance:
            raise OptimizationError(f"optimized UV drift {drift} exceeds tolerance {uv_tolerance}")
    except (GltfValidationError, OptimizationError):
        output_path.unlink(missing_ok=True)
        raise

    report = {
        "schema_version": 1,
        "ok": True,
        "authoritative_source": str(input_path),
        "source_sha256": sha256_file(input_path),
        "derivative": str(output_path),
        "derivative_sha256": sha256_file(output_path),
        "gltfpack_version": runtime.get("gltfpack_version"),
        "command": command,
        "pixel_atlas": pixel_atlas,
        "uv_max_drift": drift,
        "uv_tolerance": uv_tolerance,
        "source_validation": source_validation,
        "derivative_validation": derivative_validation,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
    }
    atomic_write_json(report_output, report)
    return report
