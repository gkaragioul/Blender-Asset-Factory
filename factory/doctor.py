from __future__ import annotations

import json
import shutil
import socket
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from .config import FactoryConfig


def _cap(
    status: str,
    path: Path | None = None,
    version: str | None = None,
    detail: str = "",
) -> dict:
    return {
        "status": status,
        "path": str(path) if path else None,
        "version": version,
        "detail": detail,
    }


def _run_version(path: Path, *args: str) -> str:
    completed = subprocess.run(
        [str(path), *args],
        capture_output=True,
        text=True,
        timeout=5,
        check=True,
    )
    return (completed.stdout or completed.stderr).splitlines()[0].strip()


def _probe_bridge(url: str) -> tuple[bool, str]:
    try:
        parsed = urlparse(url)
        request = {
            "id": "factory-doctor",
            "command": "scene.get_info",
            "params": {},
        }
        with socket.create_connection(
            (parsed.hostname or "127.0.0.1", parsed.port or 9876), timeout=1
        ) as connection:
            connection.sendall((json.dumps(request) + "\n").encode("utf-8"))
            buffer = b""
            while b"\n" not in buffer:
                chunk = connection.recv(65536)
                if not chunk:
                    raise ConnectionError("bridge closed before a full response")
                buffer += chunk
        response = json.loads(buffer.split(b"\n", 1)[0].decode("utf-8"))
        if response.get("success"):
            return True, "scene.get_info succeeded"
        return False, str(response.get("error", "bridge request failed"))
    except Exception as error:
        return False, str(error)


def probe(config: FactoryConfig) -> dict:
    capabilities: dict[str, dict] = {}
    blender = next(
        (path for path in config.blender_candidates if path.is_file()), None
    )
    if blender:
        try:
            capabilities["blender"] = _cap(
                "available", blender, _run_version(blender, "--version")
            )
        except Exception as error:
            capabilities["blender"] = _cap(
                "degraded", blender, detail=str(error)
            )
    else:
        capabilities["blender"] = _cap(
            "unavailable", detail="No configured Blender executable exists"
        )

    bridge_ok, bridge_detail = _probe_bridge(config.bridge_url)
    capabilities["bridge"] = _cap(
        "available" if bridge_ok else "unavailable", detail=bridge_detail
    )

    runtime_path = config.tooling_root / "runtime.json"
    runtime = (
        json.loads(runtime_path.read_text(encoding="utf-8-sig"))
        if runtime_path.is_file()
        else {}
    )
    for name in ("uv", "python"):
        path = Path(runtime[name]) if runtime.get(name) else None
        capabilities[name] = (
            _cap("available", path, runtime.get(name + "_version"))
            if path and path.is_file()
            else _cap("unavailable")
        )

    if config.model_root.is_dir():
        free = shutil.disk_usage(config.model_root).free
        capabilities["model_root"] = _cap(
            "available", config.model_root, detail=f"free_bytes={free}"
        )
    else:
        capabilities["model_root"] = _cap(
            "unavailable",
            config.model_root,
            detail="Model root does not exist",
        )

    optional = {
        "armorpaint": config.tooling_root / "armorpaint" / "ArmorPaint.exe",
        "comfyui": config.tooling_root / "comfyui" / "main.py",
        "gltf_validator": config.tooling_root
        / "gltf-validator"
        / "gltf_validator.exe",
        "gltfpack": config.tooling_root / "gltfpack" / "gltfpack.exe",
        "material_maker": config.tooling_root
        / "material-maker"
        / "material_maker.exe",
        "threejs_viewer": config.root
        / "tools"
        / "threejs-viewer"
        / "package.json",
    }
    for name, path in optional.items():
        capabilities[name] = _cap(
            "available" if path.is_file() else "unavailable", path
        )
    backend = config.tooling_root / "comfyui" / "backend.json"
    if (
        capabilities["comfyui"]["status"] == "available"
        and not backend.is_file()
    ):
        capabilities["comfyui"] = _cap(
            "degraded",
            optional["comfyui"],
            detail="AMD backend not verified",
        )

    return {
        "schema_version": 1,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "capabilities": {
            name: capabilities[name] for name in sorted(capabilities)
        },
    }
