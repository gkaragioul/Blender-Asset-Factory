from __future__ import annotations

import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

from .config import FactoryConfig
from .io import atomic_write_json, sha256_file


class ArtRunError(ValueError):
    pass


_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_BRIEF_KEYS = {
    "schema_version",
    "asset_id",
    "style_profile",
    "intended_use",
    "required_parts",
    "forbidden_details",
    "budgets",
    "cameras",
    "retry_budget",
    "references",
}
_REFERENCE_KEYS = {
    "id",
    "kind",
    "source_url",
    "creator",
    "license",
    "license_url",
    "license_snapshot_path",
    "local_path",
}


def _require_identifier(value: object, field: str) -> str:
    text = str(value)
    if not _IDENTIFIER.fullmatch(text):
        raise ArtRunError(f"{field} must be a portable identifier")
    return text


def _load_brief(config: FactoryConfig, brief_path: Path) -> tuple[Path, dict]:
    source = config.require_owned_path(brief_path)
    if not source.is_file():
        raise ArtRunError(f"asset brief does not exist: {source}")
    brief = json.loads(source.read_text(encoding="utf-8-sig"))
    if set(brief) != _BRIEF_KEYS or brief.get("schema_version") != 1:
        raise ArtRunError(f"asset brief keys must be exactly {sorted(_BRIEF_KEYS)}")
    _require_identifier(brief.get("asset_id"), "asset_id")
    _require_identifier(brief.get("style_profile"), "style_profile")
    if not isinstance(brief.get("required_parts"), list) or not brief["required_parts"]:
        raise ArtRunError("required_parts must be a non-empty list")
    if not isinstance(brief.get("cameras"), list) or not brief["cameras"]:
        raise ArtRunError("cameras must be a non-empty list")
    if not isinstance(brief.get("references"), list) or not brief["references"]:
        raise ArtRunError("references must be a non-empty list")
    return source, brief


def create_art_run(
    config: FactoryConfig,
    brief_path: Path,
    *,
    run_id: str,
) -> dict:
    identifier = _require_identifier(run_id, "run_id")
    brief_source, brief = _load_brief(config, brief_path)
    run_root = config.require_owned_path(
        config.reports_root / "art-runs" / identifier
    )
    if run_root.exists():
        raise ArtRunError(f"art runs are immutable and already exist: {run_root}")

    references_root = run_root / "references"
    licenses_root = run_root / "licenses"
    references_root.mkdir(parents=True)
    licenses_root.mkdir(parents=True)
    provenance_references: list[dict] = []
    seen: set[str] = set()
    try:
        shutil.copy2(brief_source, run_root / "brief.json")
        for reference in brief["references"]:
            if not isinstance(reference, dict) or set(reference) != _REFERENCE_KEYS:
                raise ArtRunError(
                    f"reference keys must be exactly {sorted(_REFERENCE_KEYS)}"
                )
            reference_id = _require_identifier(reference.get("id"), "reference id")
            if reference_id in seen:
                raise ArtRunError(f"duplicate reference id: {reference_id}")
            seen.add(reference_id)
            if not str(reference.get("license", "")).strip():
                raise ArtRunError(f"reference license is required: {reference_id}")
            if not str(reference.get("license_url", "")).strip():
                raise ArtRunError(f"reference license URL is required: {reference_id}")
            source = config.require_owned_path(Path(reference["local_path"]))
            if not source.is_file():
                raise ArtRunError(f"reference file does not exist: {source}")
            license_source = config.require_owned_path(
                Path(reference["license_snapshot_path"])
            )
            if not license_source.is_file():
                raise ArtRunError(
                    f"reference license snapshot does not exist: {license_source}"
                )
            suffix = source.suffix.lower() or ".bin"
            destination = references_root / f"{reference_id}{suffix}"
            shutil.copy2(source, destination)
            license_suffix = license_source.suffix.lower() or ".txt"
            license_destination = licenses_root / f"{reference_id}{license_suffix}"
            shutil.copy2(license_source, license_destination)
            provenance_references.append(
                {
                    "id": reference_id,
                    "kind": reference["kind"],
                    "source_url": reference["source_url"],
                    "creator": reference["creator"],
                    "license": reference["license"],
                    "license_url": reference["license_url"],
                    "path": destination.relative_to(run_root).as_posix(),
                    "sha256": sha256_file(destination),
                    "license_snapshot_path": license_destination.relative_to(
                        run_root
                    ).as_posix(),
                    "license_snapshot_sha256": sha256_file(license_destination),
                }
            )

        atomic_write_json(
            run_root / "provenance.json",
            {
                "schema_version": 1,
                "run_id": identifier,
                "asset_id": brief["asset_id"],
                "brief_sha256": sha256_file(run_root / "brief.json"),
                "references": provenance_references,
            },
        )
        atomic_write_json(
            run_root / "state.json",
            {
                "schema_version": 1,
                "run_id": identifier,
                "asset_id": brief["asset_id"],
                "created_at": datetime.now(timezone.utc).isoformat(),
                "stage": "awaiting_concept_candidates",
                "gates": {
                    "references_frozen": True,
                    "concept_approved": False,
                    "high_poly_approved": False,
                    "runtime_approved": False,
                },
            },
        )
    except Exception:
        shutil.rmtree(run_root, ignore_errors=True)
        raise

    return {
        "schema_version": 1,
        "ok": True,
        "run_id": identifier,
        "asset_id": brief["asset_id"],
        "run_root": str(run_root),
        "brief_sha256": sha256_file(run_root / "brief.json"),
        "reference_count": len(provenance_references),
        "stage": "awaiting_concept_candidates",
    }


_CONCEPT_METADATA_KEYS = {
    "provider",
    "model",
    "prompt_sha256",
    "workflow_sha256",
    "seed",
    "license_snapshot",
}


def _require_sha256(value: object, field: str) -> str:
    text = str(value).lower()
    if len(text) != 64 or any(character not in "0123456789abcdef" for character in text):
        raise ArtRunError(f"{field} must be a 64-character SHA-256")
    return text


def _run_root(config: FactoryConfig, run_id: str) -> Path:
    identifier = _require_identifier(run_id, "run_id")
    root = config.require_owned_path(config.reports_root / "art-runs" / identifier)
    if not (root / "state.json").is_file():
        raise ArtRunError(f"unknown art run: {identifier}")
    return root


def stage_concept_candidate(
    config: FactoryConfig,
    run_id: str,
    candidate_id: str,
    image_path: Path,
    metadata: dict,
) -> dict:
    run_root = _run_root(config, run_id)
    identifier = _require_identifier(candidate_id, "candidate_id")
    if not isinstance(metadata, dict) or set(metadata) != _CONCEPT_METADATA_KEYS:
        raise ArtRunError(
            f"concept metadata keys must be exactly {sorted(_CONCEPT_METADATA_KEYS)}"
        )
    _require_sha256(metadata["prompt_sha256"], "prompt_sha256")
    _require_sha256(metadata["workflow_sha256"], "workflow_sha256")
    if not isinstance(metadata["seed"], int):
        raise ArtRunError("concept seed must be an integer")
    for field in ("provider", "model", "license_snapshot"):
        if not str(metadata[field]).strip():
            raise ArtRunError(f"concept metadata field is required: {field}")

    source = config.require_owned_path(image_path)
    if not source.is_file():
        raise ArtRunError(f"concept image does not exist: {source}")
    if source.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
        raise ArtRunError("concept image must be PNG, JPEG, or WebP")

    concepts_root = run_root / "concepts"
    index_path = concepts_root / "index.json"
    index = (
        json.loads(index_path.read_text(encoding="utf-8-sig"))
        if index_path.is_file()
        else {"schema_version": 1, "candidates": []}
    )
    if any(item["candidate_id"] == identifier for item in index["candidates"]):
        raise ArtRunError(f"duplicate concept candidate: {identifier}")

    destination = concepts_root / "candidates" / f"{identifier}{source.suffix.lower()}"
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    record = {
        "candidate_id": identifier,
        "path": destination.relative_to(run_root).as_posix(),
        "sha256": sha256_file(destination),
        "metadata": dict(metadata),
    }
    index["candidates"].append(record)
    atomic_write_json(index_path, index)
    return {
        "schema_version": 1,
        "ok": True,
        "run_id": run_id,
        "candidate_id": identifier,
        "path": str(destination),
        "sha256": record["sha256"],
    }


def approve_concept(
    config: FactoryConfig,
    run_id: str,
    candidate_id: str,
    *,
    approved_by: str,
    evidence: str,
) -> dict:
    run_root = _run_root(config, run_id)
    identifier = _require_identifier(candidate_id, "candidate_id")
    index_path = run_root / "concepts" / "index.json"
    candidates = (
        json.loads(index_path.read_text(encoding="utf-8-sig"))["candidates"]
        if index_path.is_file()
        else []
    )
    candidate = next(
        (item for item in candidates if item["candidate_id"] == identifier), None
    )
    if candidate is None:
        raise ArtRunError(f"unknown concept candidate: {identifier}")
    if not str(approved_by).strip() or not str(evidence).strip():
        raise ArtRunError("concept approval requires approver and evidence")

    gate_path = run_root / "gates" / "concept-approval.json"
    if gate_path.exists():
        raise ArtRunError("concept approval is immutable and already exists")
    approval = {
        "schema_version": 1,
        "run_id": run_id,
        "candidate_id": identifier,
        "candidate_sha256": candidate["sha256"],
        "approved_by": approved_by,
        "evidence": evidence,
        "approved_at": datetime.now(timezone.utc).isoformat(),
    }
    atomic_write_json(gate_path, approval)

    state_path = run_root / "state.json"
    state = json.loads(state_path.read_text(encoding="utf-8-sig"))
    state["stage"] = "concept_approved"
    state["gates"]["concept_approved"] = True
    atomic_write_json(state_path, state)
    return {"ok": True, **approval}
