from __future__ import annotations

import json
from pathlib import Path

from .config import FactoryConfig
from .io import atomic_write_json, atomic_write_text


ACTIVE_KEYS = {
    "schema_version",
    "project_id",
    "status",
    "working_directory",
    "next_action",
    "required_reads",
    "blocked_by",
}


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def load_active_project(config: FactoryConfig) -> dict:
    state = _read_json(config.root / "knowledge" / "active-project.json")
    missing = ACTIVE_KEYS - state.keys()
    if missing:
        raise ValueError(f"active project missing keys: {sorted(missing)}")
    if state["schema_version"] != 1:
        raise ValueError("active project schema_version must be 1")
    return state


def save_factory_state(config: FactoryConfig, doctor_report: dict) -> None:
    atomic_write_json(
        config.root / "knowledge" / "factory-state.json", doctor_report
    )


def resume_action(config: FactoryConfig) -> dict:
    active = load_active_project(config)
    return {
        "project_id": active["project_id"],
        "summary": "No active project"
        if active["status"] == "idle"
        else f"Resume {active['project_id']}",
        "working_directory": active["working_directory"],
        "next_action": active["next_action"],
        "required_reads": active["required_reads"],
        "blocked_by": active["blocked_by"],
    }


def _display(value: object) -> str:
    return "none" if value is None else str(value)


def render_bootstrap(config: FactoryConfig) -> str:
    active = load_active_project(config)
    factory_state_path = config.root / "knowledge" / "factory-state.json"
    factory_state = (
        _read_json(factory_state_path)
        if factory_state_path.is_file()
        else {"capabilities": {}}
    )
    capabilities = factory_state.get("capabilities", {})
    lines = [
        "# Blender Asset Factory - Start Here",
        "",
        "## Mandatory startup",
        "",
        "Run `factory.ps1 doctor` before mutations.",
        "",
        "## Active project",
        "",
        f"- Project: `{_display(active['project_id'])}`",
        f"- Status: `{active['status']}`",
        f"- Working directory: `{_display(active['working_directory'])}`",
        f"- Next action: `{_display(active['next_action'])}`",
        "",
        "## Verified capabilities",
        "",
    ]
    if capabilities:
        lines.extend(
            f"- {name}: `{capabilities[name]['status']}`"
            for name in sorted(capabilities)
        )
    else:
        lines.append("- No saved doctor report; run `factory.ps1 doctor --save`.")
    lines.extend(["", "## Required reading", ""])
    if active["required_reads"]:
        lines.extend(f"- `{path}`" for path in active["required_reads"])
    else:
        lines.append("- None")
    lines.extend(
        [
            "",
            "## Completion discipline",
            "",
            "Run the required validations, record evidence, refresh memory, and preserve the next safe action.",
            "",
        ]
    )
    return "\n".join(lines)


def render_factory_state(config: FactoryConfig) -> str:
    state_path = config.root / "knowledge" / "factory-state.json"
    state = _read_json(state_path) if state_path.is_file() else {}
    lines = [
        "# Blender Asset Factory - Verified State",
        "",
        f"- Repository root: `{config.root}`",
        f"- Model root: `{config.model_root}`",
        f"- Last doctor check: `{_display(state.get('checked_at'))}`",
        "",
        "## Capabilities",
        "",
    ]
    capabilities = state.get("capabilities", {})
    lines.extend(
        f"- {name}: `{capabilities[name]['status']}`"
        for name in sorted(capabilities)
    )
    if not capabilities:
        lines.append("- No saved capability report")
    lines.append("")
    return "\n".join(lines)


def refresh_bootstrap(config: FactoryConfig) -> None:
    atomic_write_text(
        config.root / "knowledge" / "START_HERE.md",
        render_bootstrap(config),
    )
    atomic_write_text(
        config.root / "knowledge" / "FACTORY_STATE.md",
        render_factory_state(config),
    )
