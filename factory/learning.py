from __future__ import annotations

import json
from pathlib import Path

from .config import FactoryConfig
from .io import atomic_write_json
from .state import refresh_bootstrap


REQUIRED = {"lesson_id", "scope", "title", "statement", "source_projects"}
SCOPES = {"asset", "profile", "universal"}
EVIDENCE = {
    "regression",
    "repeated_success",
    "user_approval",
    "asset_exception",
}


class LearningPolicyError(ValueError):
    pass


def record_candidate(config: FactoryConfig, candidate: dict) -> Path:
    missing = REQUIRED - candidate.keys()
    if missing or candidate.get("scope") not in SCOPES:
        raise LearningPolicyError(
            f"invalid candidate: missing={sorted(missing)} "
            f"scope={candidate.get('scope')}"
        )
    if not candidate["source_projects"]:
        raise LearningPolicyError("candidate requires a source project")
    path = (
        config.root
        / "knowledge"
        / "lessons"
        / "candidates"
        / f"{candidate['lesson_id']}.json"
    )
    if path.exists():
        raise LearningPolicyError(
            f"duplicate lesson id: {candidate['lesson_id']}"
        )
    atomic_write_json(
        path, {**candidate, "status": "candidate", "evidence": []}
    )
    return path


def promote_candidate(
    config: FactoryConfig, lesson_id: str, evidence: dict
) -> Path:
    source = (
        config.root
        / "knowledge"
        / "lessons"
        / "candidates"
        / f"{lesson_id}.json"
    )
    if not source.is_file():
        raise LearningPolicyError(f"unknown lesson: {lesson_id}")
    candidate = json.loads(source.read_text(encoding="utf-8-sig"))
    evidence_type = evidence.get("type")
    if evidence_type not in EVIDENCE or not evidence.get("reference"):
        raise LearningPolicyError(
            "accepted evidence type and reference are required"
        )
    if (
        candidate["scope"] == "universal"
        and evidence_type == "repeated_success"
        and len(set(candidate["source_projects"])) < 2
    ):
        raise LearningPolicyError(
            "universal repeated_success requires two source projects"
        )
    if evidence_type == "asset_exception" and candidate["scope"] != "asset":
        raise LearningPolicyError("asset_exception can promote only asset lessons")
    promoted = {
        **candidate,
        "status": "promoted",
        "evidence": [evidence],
    }
    destination = (
        config.root
        / "knowledge"
        / "lessons"
        / candidate["scope"]
        / f"{lesson_id}.json"
    )
    atomic_write_json(destination, promoted)
    atomic_write_json(source, promoted)
    return destination


def closeout_project(config: FactoryConfig, summary: dict) -> dict:
    required = {"project_id", "status", "next_action", "candidate_lessons"}
    missing = required - summary.keys()
    if missing:
        raise LearningPolicyError(f"closeout missing keys: {sorted(missing)}")
    atomic_write_json(
        config.root
        / "knowledge"
        / "project-summaries"
        / f"{summary['project_id']}.json",
        summary,
    )
    for candidate in summary["candidate_lessons"]:
        record_candidate(config, candidate)
    active_path = config.root / "knowledge" / "active-project.json"
    active = json.loads(active_path.read_text(encoding="utf-8-sig"))
    active.update(
        {"status": summary["status"], "next_action": summary["next_action"]}
    )
    atomic_write_json(active_path, active)
    refresh_bootstrap(config)
    return {
        "project_id": summary["project_id"],
        "status": summary["status"],
        "candidate_count": len(summary["candidate_lessons"]),
    }
