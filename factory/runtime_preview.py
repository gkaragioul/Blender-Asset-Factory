from __future__ import annotations

import functools
import json
import shutil
import subprocess
import threading
import uuid
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .config import FactoryConfig
from .gltf_inspection import inspect_glb
from .gltf_validation import _require_factory_input
from .io import atomic_write_json, sha256_file


class PreviewError(ValueError):
    pass


class _QuietHandler(SimpleHTTPRequestHandler):
    extensions_map = {**SimpleHTTPRequestHandler.extensions_map, ".mjs": "text/javascript", ".js": "text/javascript", ".glb": "model/gltf-binary"}

    def log_message(self, _format: str, *_args) -> None:
        return


def _browser_path() -> Path:
    linux_browser = shutil.which("google-chrome") or shutil.which("chromium") or shutil.which("chromium-browser")
    candidates = tuple(Path(path) for path in (linux_browser,) if path) + (
        Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
        Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
        Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
    )
    browser = next((path for path in candidates if path.is_file()), None)
    if browser is None:
        raise PreviewError("Chrome or Edge is required for Three.js runtime preview")
    return browser


def _stage_viewer(config: FactoryConfig, source: Path) -> Path:
    runtime = json.loads((config.tooling_root / "release-runtime.json").read_text(encoding="utf-8-sig"))
    modules = Path(runtime["node_modules"])
    stage = config.root / "tmp" / "factory" / "preview" / uuid.uuid4().hex
    vendor = stage / "vendor"
    addons = vendor / "addons"
    (addons / "loaders").mkdir(parents=True)
    (addons / "utils").mkdir(parents=True)
    (addons / "libs").mkdir(parents=True)
    viewer_root = config.root / "tools" / "threejs-viewer"
    for name in ("index.html", "viewer.mjs"):
        shutil.copy2(viewer_root / name, stage / name)
    shutil.copy2(source, stage / "asset.glb")
    three = modules / "three"
    shutil.copy2(three / "build" / "three.module.js", vendor / "three.module.js")
    shutil.copy2(three / "build" / "three.core.js", vendor / "three.core.js")
    shutil.copy2(three / "examples" / "jsm" / "loaders" / "GLTFLoader.js", addons / "loaders" / "GLTFLoader.js")
    shutil.copy2(three / "examples" / "jsm" / "utils" / "BufferGeometryUtils.js", addons / "utils" / "BufferGeometryUtils.js")
    shutil.copy2(three / "examples" / "jsm" / "utils" / "SkeletonUtils.js", addons / "utils" / "SkeletonUtils.js")
    shutil.copy2(three / "examples" / "jsm" / "libs" / "meshopt_decoder.module.js", addons / "libs" / "meshopt_decoder.module.js")
    return stage


def preview_glb(config: FactoryConfig, source: Path, screenshot_path: Path, report_path: Path) -> dict:
    input_path = _require_factory_input(config, source)
    screenshot = config.require_owned_path(screenshot_path).resolve(strict=False)
    report_output = config.require_owned_path(report_path).resolve(strict=False)
    root = config.root.resolve(strict=False)
    if not screenshot.is_relative_to(root) or not report_output.is_relative_to(root):
        raise PreviewError("preview outputs must be beneath the factory root")
    runtime_path = config.tooling_root / "release-runtime.json"
    if not runtime_path.is_file():
        raise PreviewError("release runtime unavailable")
    runtime = json.loads(runtime_path.read_text(encoding="utf-8-sig"))
    node = Path(runtime.get("node", ""))
    node_modules = Path(runtime.get("node_modules", ""))
    capture = config.root / "tools" / "release-node" / "capture-viewer.mjs"
    if not node.is_file() or not node_modules.is_dir() or not capture.is_file():
        raise PreviewError("Three.js capture dependencies are unavailable")
    browser = _browser_path()
    stage = _stage_viewer(config, input_path)
    screenshot.parent.mkdir(parents=True, exist_ok=True)
    report_output.parent.mkdir(parents=True, exist_ok=True)
    raw_report = stage / "browser-report.json"
    handler = functools.partial(_QuietHandler, directory=str(stage))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}/index.html"
    completed = None
    timeout_error = None
    try:
        completed = subprocess.run(
            [str(node), str(capture), url, str(screenshot), str(raw_report), str(browser), str(node_modules)],
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
    return_code = completed.returncode if completed is not None else -1
    stdout = completed.stdout if completed is not None else ""
    stderr = completed.stderr if completed is not None else str(timeout_error or "")
    report = {
        "schema_version": 1,
        "ok": return_code == 0 and browser_report.get("viewer", {}).get("status") == "loaded",
        "source": str(input_path),
        "source_sha256": sha256_file(input_path),
        "screenshot": str(screenshot),
        "screenshot_sha256": sha256_file(screenshot) if screenshot.is_file() else None,
        "url": url,
        "browser": str(browser),
        "three_version": json.loads((node_modules / "three" / "package.json").read_text(encoding="utf-8"))["version"],
        "inspection": inspect_glb(input_path),
        "viewer": browser_report.get("viewer", {}),
        "console_errors": browser_report.get("console_errors", []),
        "phases": browser_report.get("phases", []),
        "stdout": stdout.strip(),
        "stderr": stderr.strip(),
    }
    atomic_write_json(report_output, report)
    if not report["ok"]:
        raise PreviewError(f"Three.js runtime preview failed: {report['viewer'].get('error') or report['console_errors'] or stderr}")
    return report
