"""Multi-view Three.js review sheet with measured placement and budget checks.

Renders the exported GLB from standard angles in the pinned Three.js viewer,
optionally beside a 1.80 m scale figure, and checks the measured bounds,
triangles and draw calls with factory.placement. The same sheet serves as QA
evidence and as a starting point for storefront preview images.
"""
from __future__ import annotations

import functools
import json
import subprocess
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlencode

from .config import FactoryConfig
from .gltf_inspection import inspect_glb
from .gltf_validation import _require_factory_input
from .io import atomic_write_json, sha256_file
from .placement import check_measurements, resolve_expectations
from .runtime_preview import _QuietHandler, _browser_path, _stage_viewer

KNOWN_VIEWS = ("q-front", "q-front-r", "front", "left", "right", "rear", "q-rear", "q-rear-l", "top", "bottom", "ground", "high")
DEFAULT_VIEWS = ("q-front", "left", "front", "q-rear", "top", "ground")


class ReviewError(ValueError):
    pass


def review_glb(
    config: FactoryConfig,
    source: Path,
    output_path: Path,
    report_path: Path,
    *,
    views: tuple[str, ...] = DEFAULT_VIEWS,
    scale_figure: bool = False,
    width: int = 1800,
    height: int = 1200,
    expectations: dict | None = None,
) -> dict:
    unknown = [view for view in views if view not in KNOWN_VIEWS]
    if unknown or not views:
        raise ReviewError(f"unknown view: {', '.join(unknown) or '(none given)'}; known views are {', '.join(KNOWN_VIEWS)}")
    input_path = _require_factory_input(config, source)
    output = config.require_owned_path(output_path).resolve(strict=False)
    report_output = config.require_owned_path(report_path).resolve(strict=False)
    root = config.root.resolve(strict=False)
    if not output.is_relative_to(root) or not report_output.is_relative_to(root):
        raise ReviewError("review outputs must be beneath the factory root")
    resolved = resolve_expectations(config.root, expectations or {})
    runtime_path = config.tooling_root / "release-runtime.json"
    if not runtime_path.is_file():
        raise ReviewError("release runtime unavailable")
    runtime = json.loads(runtime_path.read_text(encoding="utf-8-sig"))
    node = Path(runtime.get("node", ""))
    node_modules = Path(runtime.get("node_modules", ""))
    capture = config.root / "tools" / "release-node" / "capture-viewer.mjs"
    if not node.is_file() or not node_modules.is_dir() or not capture.is_file():
        raise ReviewError("Three.js capture dependencies are unavailable")
    browser = _browser_path()
    stage = _stage_viewer(config, input_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    report_output.parent.mkdir(parents=True, exist_ok=True)
    raw_report = stage / "browser-report.json"
    handler = functools.partial(_QuietHandler, directory=str(stage))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    query = urlencode({"views": ",".join(views), "ref": "1" if scale_figure else "0", "w": width, "h": height})
    url = f"http://127.0.0.1:{server.server_port}/index.html?{query}"
    completed = None
    timeout_error = None
    try:
        completed = subprocess.run(
            [str(node), str(capture), url, str(output), str(raw_report), str(browser), str(node_modules), str(width), str(height)],
            cwd=config.root,
            capture_output=True,
            text=True,
            timeout=300,
        )
    except subprocess.TimeoutExpired as error:
        timeout_error = error
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
    browser_report = json.loads(raw_report.read_text(encoding="utf-8")) if raw_report.is_file() else {"viewer": {"status": "error", "error": str(timeout_error or "capture produced no report")}, "console_errors": [], "phases": []}
    viewer = browser_report.get("viewer", {})
    rendered = completed is not None and completed.returncode == 0 and viewer.get("status") == "loaded" and output.is_file()
    measured = {
        "bounds": viewer.get("bounds"),
        "triangle_count": viewer.get("triangle_count", 0),
        "draw_calls": viewer.get("review", {}).get("draw_calls", 0),
        "mesh_count": viewer.get("mesh_count", 0),
        "material_count": viewer.get("material_count", 0),
        "texture_count": viewer.get("texture_count", 0),
    }
    checks = check_measurements(measured, resolved) if rendered else {"passed": False, "failures": ["not_rendered"], "details": {}}
    report = {
        "schema_version": 1,
        "rendered": rendered,
        "ok": rendered and checks["passed"],
        "source": str(input_path),
        "source_sha256": sha256_file(input_path),
        "output": str(output),
        "output_sha256": sha256_file(output) if output.is_file() else None,
        "views": list(views),
        "scale_figure": scale_figure,
        "url": url,
        "browser": str(browser),
        "three_version": json.loads((node_modules / "three" / "package.json").read_text(encoding="utf-8"))["version"],
        "inspection": inspect_glb(input_path),
        "measured": measured,
        "expectations": resolved,
        "checks": checks,
        "viewer": viewer,
        "console_errors": browser_report.get("console_errors", []),
        "phases": browser_report.get("phases", []),
        "stdout": completed.stdout.strip() if completed is not None else "",
        "stderr": completed.stderr.strip() if completed is not None else str(timeout_error or ""),
    }
    atomic_write_json(report_output, report)
    if not rendered:
        raise ReviewError(f"Three.js review render failed: {viewer.get('error') or report['console_errors'] or report['stderr']}")
    return report
