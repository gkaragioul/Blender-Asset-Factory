from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime, timezone

from .config import FactoryConfig
from .doctor import probe
from .io import atomic_write_json
from .state import render_bootstrap, resume_action


def _git_commit(config: FactoryConfig) -> str | None:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=config.root,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip() if completed.returncode == 0 else None


def verify(config: FactoryConfig) -> tuple[bool, dict]:
    environment = os.environ.copy()
    environment["BAF_VERIFY_CHILD"] = "1"
    command = [
        sys.executable,
        "-m",
        "unittest",
        "discover",
        "-s",
        "tests",
        "-p",
        "test_*.py",
        "-v",
    ]
    completed = subprocess.run(
        command,
        cwd=config.root,
        capture_output=True,
        text=True,
        env=environment,
    )
    doctor_report = probe(config)
    resume = resume_action(config)
    checked_at = datetime.now(timezone.utc)
    run_id = checked_at.strftime("%Y%m%dT%H%M%S.%fZ")
    report_path = (
        config.reports_root
        / "runs"
        / run_id
        / "phase-1-verification.json"
    )
    mandatory = ("python", "uv", "blender", "model_root")
    mandatory_ok = all(
        doctor_report["capabilities"][name]["status"] == "available"
        for name in mandatory
    )
    start_path = config.root / "knowledge" / "START_HERE.md"
    bootstrap_fresh = (
        start_path.is_file()
        and start_path.read_text(encoding="utf-8") == render_bootstrap(config)
    )
    ok = (
        completed.returncode == 0
        and mandatory_ok
        and bool(resume.get("next_action"))
        and bootstrap_fresh
    )
    report = {
        "schema_version": 1,
        "ok": ok,
        "checked_at": checked_at.isoformat(),
        "git_commit": _git_commit(config),
        "command": command,
        "test_exit_code": completed.returncode,
        "stdout": completed.stdout[-12000:],
        "stderr": completed.stderr[-12000:],
        "doctor": doctor_report,
        "resume": resume,
        "bootstrap_fresh": bootstrap_fresh,
        "report_path": str(report_path),
    }
    atomic_write_json(report_path, report)
    return ok, report
