from __future__ import annotations

import glob
import json
import re
import shutil
import subprocess
from pathlib import Path

from .config import FactoryConfig
from .io import atomic_write_json


class BlenderError(RuntimeError):
    pass


_VERSION = re.compile(r"(\d+)(?:\.(\d+))?")


def _version_key(path: Path) -> tuple[int, int]:
    match = _VERSION.search(path.parent.name) or _VERSION.search(path.name)
    if not match:
        return (0, 0)
    return (int(match.group(1)), int(match.group(2) or 0))


def discover_blender(config: FactoryConfig) -> Path | None:
    matches: list[Path] = []
    for candidate in config.blender_candidates:
        text = str(candidate)
        if any(character in text for character in "*?["):
            matches.extend(Path(item) for item in glob.glob(text))
        elif candidate.is_file():
            matches.append(candidate)
    if not matches:
        found = shutil.which("blender")
        if found:
            matches.append(Path(found))
    if not matches:
        return None
    return sorted(matches, key=_version_key, reverse=True)[0]


def run_blender_script(
    config: FactoryConfig,
    script: Path,
    payload: dict,
    report_path: Path,
    timeout_seconds: float = 600,
) -> dict:
    executable = discover_blender(config)
    if executable is None:
        raise BlenderError("no Blender executable was discovered")
    config.require_owned_path(report_path)
    payload_path = report_path.with_name(report_path.name + ".payload.json")
    atomic_write_json(payload_path, payload)
    command = [
        str(executable),
        "--background",
        "--factory-startup",
        "--python",
        str(script),
        "--",
        "--payload",
        str(payload_path),
        "--report",
        str(report_path),
    ]
    try:
        completed = subprocess.run(
            command, capture_output=True, text=True, timeout=timeout_seconds
        )
    except subprocess.TimeoutExpired as error:
        raise BlenderError(
            f"Blender script {script} timed out after {timeout_seconds} seconds"
        ) from error
    if not report_path.is_file():
        raise BlenderError(
            "Blender produced no report\n"
            f"exit={completed.returncode}\n"
            f"stdout={completed.stdout[-4000:]}\n"
            f"stderr={completed.stderr[-4000:]}"
        )
    return json.loads(report_path.read_text(encoding="utf-8"))
