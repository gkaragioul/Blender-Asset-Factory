from __future__ import annotations

import functools
import html
import json
import shutil
import subprocess
import threading
import uuid
from http.server import ThreadingHTTPServer
from pathlib import Path

from .config import FactoryConfig
from .gltf_validation import _require_factory_input
from .io import atomic_write_json, sha256_file
from .runtime_preview import _QuietHandler, _browser_path


class ContactSheetError(ValueError):
    pass


def _html_document(title: str, staged_views: list[dict]) -> str:
    cards = "\n".join(
        f'<article><div class="image"><img src="{html.escape(view["file"])}" alt="{html.escape(view["label"])}"></div><h2>{html.escape(view["label"])}</h2><code>{html.escape(view["id"])}</code></article>'
        for view in staged_views
    )
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>{html.escape(title)}</title><link rel="icon" href="data:,">
<style>
*{{box-sizing:border-box}} html,body{{margin:0;background:#111417;color:#eef1f4;font-family:Arial,sans-serif}}
.sheet{{width:1440px;padding:52px}} header{{display:flex;justify-content:space-between;align-items:end;margin-bottom:32px;border-bottom:1px solid #394047;padding-bottom:20px}}
h1{{font-size:34px;margin:0;letter-spacing:.02em}} .meta{{color:#9da7b1;font-size:14px}} main{{display:grid;grid-template-columns:repeat(3,1fr);gap:22px}}
article{{background:#1a1f24;border:1px solid #343c44;padding:12px}} .image{{height:260px;background:#0b0d0f;display:flex;align-items:center;justify-content:center}}
img{{width:100%;height:100%;object-fit:contain;image-rendering:auto}} h2{{font-size:17px;margin:13px 0 5px}} code{{color:#94a6b8;font-size:12px}}
</style></head><body><div class="sheet"><header><h1>{html.escape(title)}</h1><div class="meta">Blender Asset Factory · QA contact sheet</div></header><main>{cards}</main></div></body></html>"""


def build_contact_sheet(config: FactoryConfig, manifest_path: Path, output_path: Path, report_path: Path) -> dict:
    manifest_source = _require_factory_input(config, manifest_path)
    output = config.require_owned_path(output_path).resolve(strict=False)
    report_output = config.require_owned_path(report_path).resolve(strict=False)
    root = config.root.resolve(strict=False)
    if not output.is_relative_to(root) or not report_output.is_relative_to(root):
        raise ContactSheetError("contact-sheet outputs must be beneath the factory root")
    manifest = json.loads(manifest_source.read_text(encoding="utf-8-sig"))
    if manifest.get("schema_version") != 1 or not isinstance(manifest.get("views"), list):
        raise ContactSheetError("view manifest schema_version 1 and views are required")
    required = manifest.get("required_views")
    if not isinstance(required, list) or not required:
        raise ContactSheetError("required_views must be a non-empty list")
    by_id = {view.get("id"): view for view in manifest["views"]}
    if len(by_id) != len(manifest["views"]) or None in by_id:
        raise ContactSheetError("view ids must be present and unique")
    missing = [view_id for view_id in required if view_id not in by_id]
    if missing:
        raise ContactSheetError(f"missing required views: {', '.join(missing)}")

    runtime_path = config.tooling_root / "release-runtime.json"
    if not runtime_path.is_file():
        raise ContactSheetError("release runtime unavailable")
    runtime = json.loads(runtime_path.read_text(encoding="utf-8-sig"))
    node = Path(runtime["node"])
    node_modules = Path(runtime["node_modules"])
    capture = config.root / "tools" / "release-node" / "capture-contact-sheet.mjs"
    if not node.is_file() or not node_modules.is_dir() or not capture.is_file():
        raise ContactSheetError("contact-sheet capture dependencies are unavailable")

    stage = config.root / "tmp" / "factory" / "contact-sheets" / uuid.uuid4().hex
    stage.mkdir(parents=True)
    staged_views = []
    evidence = []
    for index, view in enumerate(manifest["views"]):
        image = _require_factory_input(config, Path(view.get("path", "")))
        if image.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
            raise ContactSheetError(f"unsupported view image: {image}")
        name = f"view-{index:02d}{image.suffix.lower()}"
        shutil.copy2(image, stage / name)
        staged_views.append({"id": str(view["id"]), "label": str(view.get("label") or view["id"]), "file": name})
        evidence.append({"id": str(view["id"]), "source": str(image), "sha256": sha256_file(image)})
    (stage / "index.html").write_text(_html_document(str(manifest.get("title") or "Asset QA"), staged_views), encoding="utf-8", newline="\n")

    output.parent.mkdir(parents=True, exist_ok=True)
    report_output.parent.mkdir(parents=True, exist_ok=True)
    raw_report = stage / "browser-report.json"
    handler = functools.partial(_QuietHandler, directory=str(stage))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}/index.html"
    try:
        completed = subprocess.run([str(node), str(capture), url, str(output), str(raw_report), str(_browser_path()), str(node_modules)], cwd=config.root, capture_output=True, text=True, timeout=300)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
    browser_report = json.loads(raw_report.read_text(encoding="utf-8")) if raw_report.is_file() else {"ok": False, "error": completed.stderr}
    report = {
        "schema_version": 1,
        "ok": completed.returncode == 0 and bool(browser_report.get("ok")) and output.is_file(),
        "title": str(manifest.get("title") or "Asset QA"),
        "manifest": str(manifest_source),
        "manifest_sha256": sha256_file(manifest_source),
        "output": str(output),
        "output_sha256": sha256_file(output) if output.is_file() else None,
        "view_ids": [str(view["id"]) for view in manifest["views"]],
        "required_views": required,
        "views": evidence,
        "url": url,
        "browser": browser_report,
    }
    atomic_write_json(report_output, report)
    if not report["ok"]:
        raise ContactSheetError(f"contact-sheet browser capture failed: {browser_report}")
    return report
