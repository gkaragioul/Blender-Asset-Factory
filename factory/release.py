from __future__ import annotations

import json
import os
import re
import shutil
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .config import FactoryConfig
from .contact_sheet import build_contact_sheet
from .gltf_validation import _require_factory_input, validate_glb
from .io import atomic_write_json, sha256_file
from .optimizer import optimize_glb
from .runtime_preview import preview_glb


class ReleaseError(ValueError):
    pass


@dataclass(frozen=True)
class ReleaseAdapters:
    validate: Callable = validate_glb
    optimize: Callable = optimize_glb
    preview: Callable = preview_glb
    contact_sheet: Callable = build_contact_sheet


_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_JOB_KEYS = {
    "schema_version",
    "asset_id",
    "version",
    "authoritative_glb",
    "source_job_hash",
    "pixel_atlas",
    "uv_tolerance",
    "required_views",
    "views",
}


def _load_job(config: FactoryConfig, job_path: Path) -> tuple[Path, dict]:
    source = _require_factory_input(config, job_path)
    job = json.loads(source.read_text(encoding="utf-8-sig"))
    if set(job) != _JOB_KEYS or job.get("schema_version") != 1:
        raise ReleaseError(f"release job keys must be exactly {sorted(_JOB_KEYS)}")
    if not _IDENTIFIER.fullmatch(str(job.get("asset_id", ""))) or not _IDENTIFIER.fullmatch(str(job.get("version", ""))):
        raise ReleaseError("asset_id and version must be portable identifiers")
    source_hash = str(job.get("source_job_hash", ""))
    if len(source_hash) != 64 or any(character not in "0123456789abcdefABCDEF" for character in source_hash):
        raise ReleaseError("source_job_hash must be a 64-character SHA-256")
    if not isinstance(job.get("pixel_atlas"), bool) or not isinstance(job.get("uv_tolerance"), (int, float)) or job["uv_tolerance"] < 0:
        raise ReleaseError("pixel_atlas and a non-negative uv_tolerance are required")
    if not isinstance(job.get("required_views"), list) or not job["required_views"]:
        raise ReleaseError("required_views must be a non-empty list")
    if not isinstance(job.get("views"), list):
        raise ReleaseError("views must be a list")
    return source, job


def _inventory(root: Path) -> list[dict]:
    files = []
    for path in sorted((item for item in root.rglob("*") if item.is_file()), key=lambda item: item.relative_to(root).as_posix()):
        relative = path.relative_to(root).as_posix()
        if relative in {"package-manifest.json", "release.complete.json"}:
            continue
        files.append({"path": relative, "size": path.stat().st_size, "sha256": sha256_file(path)})
    return files


def _tool_versions(config: FactoryConfig) -> dict:
    runtime_path = config.tooling_root / "release-runtime.json"
    manifest_path = config.root / "tools" / "manifests" / "release-toolchain.json"
    runtime = json.loads(runtime_path.read_text(encoding="utf-8-sig")) if runtime_path.is_file() else {}
    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig")) if manifest_path.is_file() else {}
    return {
        "node": runtime.get("node_version") or manifest.get("node", {}).get("version"),
        "gltfpack": runtime.get("gltfpack_version") or manifest.get("gltfpack", {}).get("version"),
        "gltf_validator": manifest.get("gltf_validator", {}).get("version"),
        "three": manifest.get("three", {}).get("version"),
        "playwright_core": manifest.get("playwright_core", {}).get("version"),
    }


def release_package(
    config: FactoryConfig,
    job_path: Path,
    adapters: ReleaseAdapters | None = None,
    *,
    run_id: str | None = None,
) -> dict:
    job_source, job = _load_job(config, job_path)
    source = _require_factory_input(config, Path(job["authoritative_glb"]))
    active_adapters = adapters or ReleaseAdapters()
    identifier = run_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ-") + uuid.uuid4().hex[:8]
    if not _IDENTIFIER.fullmatch(identifier):
        raise ReleaseError("run_id must be a portable identifier")
    published = config.root / "assets" / "releases" / job["asset_id"] / job["version"]
    config.require_owned_path(published)
    if published.exists():
        raise ReleaseError(f"published release versions are immutable: {published}")
    stage = config.root / "tmp" / "factory" / identifier / "package"
    reports = stage / "reports"
    previews = stage / "previews"
    views_root = stage / "views"
    failure_report = config.reports_root / "runs" / identifier / "release-failure.json"
    success_report = config.reports_root / "runs" / identifier / "release-success.json"
    for directory in (stage, reports, previews, views_root):
        directory.mkdir(parents=True, exist_ok=True)

    try:
        authoritative = stage / "authoritative.glb"
        shutil.copy2(source, authoritative)
        shutil.copy2(job_source, stage / "release-job.json")
        authoritative_validation = active_adapters.validate(config, authoritative, reports / "authoritative-validation.json")
        if not authoritative_validation.get("ok"):
            raise ReleaseError("authoritative validator gate returned failure")

        derivative = stage / "optimized.glb"
        optimization = active_adapters.optimize(
            config,
            authoritative,
            derivative,
            reports / "optimization.json",
            pixel_atlas=job["pixel_atlas"],
            uv_tolerance=float(job["uv_tolerance"]),
        )
        if not optimization.get("ok"):
            raise ReleaseError("optimizer gate returned failure")

        engine_authoritative = previews / "engine-authoritative.png"
        preview_authoritative = active_adapters.preview(config, authoritative, engine_authoritative, reports / "preview-authoritative.json")
        engine_optimized = previews / "engine-optimized.png"
        preview_optimized = active_adapters.preview(config, derivative, engine_optimized, reports / "preview-optimized.json")
        if not preview_authoritative.get("ok") or not preview_optimized.get("ok"):
            raise ReleaseError("Three.js preview gate returned failure")

        contact_views: list[dict] = []
        portable_views: list[dict] = []
        seen: set[str] = set()
        for index, view in enumerate(job["views"]):
            view_id = str(view.get("id", ""))
            if not _IDENTIFIER.fullmatch(view_id) or view_id in seen or view_id == "engine":
                raise ReleaseError(f"view id must be unique, portable, and not reserved: {view_id}")
            source_view = _require_factory_input(config, Path(view.get("path", "")))
            name = f"{index:02d}-{view_id}{source_view.suffix.lower()}"
            packaged_view = views_root / name
            shutil.copy2(source_view, packaged_view)
            contact_views.append({"id": view_id, "label": str(view.get("label") or view_id), "path": str(packaged_view)})
            portable_views.append({"id": view_id, "label": str(view.get("label") or view_id), "path": f"views/{name}"})
            seen.add(view_id)
        contact_views.append({"id": "engine", "label": "Three.js Engine", "path": str(engine_authoritative)})
        portable_views.append({"id": "engine", "label": "Three.js Engine", "path": "previews/engine-authoritative.png"})
        runtime_contact_manifest = config.root / "tmp" / "factory" / identifier / "contact-input.json"
        atomic_write_json(runtime_contact_manifest, {"schema_version": 1, "title": f"{job['asset_id']} {job['version']}", "required_views": job["required_views"], "views": contact_views})
        atomic_write_json(reports / "contact-views.json", {"schema_version": 1, "title": f"{job['asset_id']} {job['version']}", "required_views": job["required_views"], "views": portable_views})
        contact = active_adapters.contact_sheet(config, runtime_contact_manifest, stage / "contact-sheet.png", reports / "contact-sheet.json")
        if not contact.get("ok"):
            raise ReleaseError("contact-sheet gate returned failure")

        manifest = {
            "schema_version": 1,
            "asset_id": job["asset_id"],
            "version": job["version"],
            "run_id": identifier,
            "source_job_hash": job["source_job_hash"].lower(),
            "release_job_sha256": sha256_file(job_source),
            "authority": {"authoritative": "authoritative.glb", "optimized_derivative": "optimized.glb"},
            "tools": _tool_versions(config),
            "gates": {"authoritative_validation": True, "derivative_validation": True, "uv_stability": True, "threejs_authoritative": True, "threejs_derivative": True, "contact_sheet": True},
            "files": _inventory(stage),
        }
        atomic_write_json(stage / "package-manifest.json", manifest)
        atomic_write_json(stage / "release.complete.json", {"schema_version": 1, "run_id": identifier, "package_manifest_sha256": sha256_file(stage / "package-manifest.json")})
        published.parent.mkdir(parents=True, exist_ok=True)
        os.replace(stage, published)
        result = {"schema_version": 1, "ok": True, "run_id": identifier, "asset_id": job["asset_id"], "version": job["version"], "published_path": str(published), "package_manifest": str(published / "package-manifest.json")}
        atomic_write_json(success_report, result)
        return result
    except Exception as error:
        failure = {"schema_version": 1, "ok": False, "run_id": identifier, "asset_id": job["asset_id"], "version": job["version"], "stage": str(stage), "published_path": str(published), "error": str(error)}
        atomic_write_json(failure_report, failure)
        raise ReleaseError(f"release failed: {error}; report={failure_report}") from error
