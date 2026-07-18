from __future__ import annotations

import json
import sys
from collections.abc import Callable
from pathlib import Path

from . import __version__


Handler = Callable[[list[str]], tuple[int, dict]]


def envelope(
    command: str,
    ok: bool,
    summary: str,
    data: dict | None = None,
    errors: list[dict] | None = None,
) -> dict:
    return {
        "schema_version": 1,
        "command": command,
        "ok": ok,
        "summary": summary,
        "data": data or {},
        "errors": errors or [],
    }


def _version(_args: list[str]) -> tuple[int, dict]:
    return 0, envelope(
        "version",
        True,
        f"Blender Asset Factory {__version__}",
        {"version": __version__},
    )


def _doctor(args: list[str]) -> tuple[int, dict]:
    from .config import FactoryConfig
    from .doctor import probe

    config = FactoryConfig.load()
    report = probe(config)
    if "--save" in args:
        from .state import refresh_bootstrap, save_factory_state

        save_factory_state(config, report)
        refresh_bootstrap(config)
    mandatory = ("python", "uv", "blender", "model_root")
    ok = all(
        report["capabilities"][name]["status"] == "available"
        for name in mandatory
    )
    errors = [] if ok else [
        {
            "code": "mandatory_capability_missing",
            "message": "One or more mandatory capabilities are unavailable",
        }
    ]
    return (0 if ok else 1), envelope(
        "doctor",
        ok,
        "Factory capabilities are healthy"
        if ok
        else "Factory capabilities need attention",
        report,
        errors,
    )


def _refresh_memory(_args: list[str]) -> tuple[int, dict]:
    from .config import FactoryConfig
    from .state import refresh_bootstrap

    config = FactoryConfig.load()
    refresh_bootstrap(config)
    return 0, envelope(
        "refresh-memory",
        True,
        "Durable factory memory refreshed",
        {"start_here": str(config.root / "knowledge" / "START_HERE.md")},
    )


def _resume(_args: list[str]) -> tuple[int, dict]:
    from .config import FactoryConfig
    from .state import resume_action

    action = resume_action(FactoryConfig.load())
    blocked = bool(action["blocked_by"])
    return (1 if blocked else 0), envelope(
        "resume",
        not blocked,
        action["summary"],
        action,
        [
            {
                "code": "active_project_blocked",
                "message": ", ".join(action["blocked_by"]),
            }
        ]
        if blocked
        else [],
    )


def _option(args: list[str], name: str) -> str:
    try:
        return args[args.index(name) + 1]
    except (ValueError, IndexError) as error:
        raise ValueError(f"required option missing: {name}") from error


def _json_input(config, args: list[str], option: str) -> dict:
    path = config.require_owned_path(Path(_option(args, option)))
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _learn(args: list[str]) -> tuple[int, dict]:
    from .config import FactoryConfig
    from .learning import closeout_project, promote_candidate, record_candidate

    if not args:
        raise ValueError("learn requires candidate, promote, or closeout")
    config = FactoryConfig.load()
    action = args[0]
    action_args = args[1:]
    if action == "candidate":
        path = record_candidate(config, _json_input(config, action_args, "--input"))
        data = {"path": str(path)}
    elif action == "promote":
        lesson_id = _option(action_args, "--lesson-id")
        evidence = _json_input(config, action_args, "--evidence")
        path = promote_candidate(config, lesson_id, evidence)
        data = {"path": str(path), "lesson_id": lesson_id}
    elif action == "closeout":
        data = closeout_project(
            config, _json_input(config, action_args, "--input")
        )
    else:
        raise ValueError(f"unknown learn action: {action}")
    return 0, envelope(
        "learn", True, f"Learning action completed: {action}", data
    )


def _index_models(args: list[str]) -> tuple[int, dict]:
    from .config import FactoryConfig
    from .io import atomic_write_json
    from .transfer import index_models

    config = FactoryConfig.load()
    index = index_models(config, hash_files="--hash" in args)
    path = config.model_root / "manifests" / "model-index.json"
    config.require_owned_path(path)
    atomic_write_json(path, index)
    return 0, envelope(
        "index-models",
        True,
        f"Indexed {len(index['models'])} model files",
        {"index_path": str(path), "model_count": len(index["models"])},
    )


def _transfer_manifest(_args: list[str]) -> tuple[int, dict]:
    from .config import FactoryConfig
    from .io import atomic_write_json
    from .transfer import build_transfer_manifest

    config = FactoryConfig.load()
    manifest = build_transfer_manifest(config)
    path = config.root / "tools" / "manifests" / "transfer.json"
    config.require_owned_path(path)
    atomic_write_json(path, manifest)
    return 0, envelope(
        "transfer-manifest",
        True,
        f"Inventoried {len(manifest['entries'])} runtime dependencies",
        {"manifest_path": str(path), "entry_count": len(manifest["entries"])},
    )


def _validate(args: list[str]) -> tuple[int, dict]:
    from datetime import datetime, timezone

    from .config import FactoryConfig
    from .gltf_validation import validate_glb

    config = FactoryConfig.load()
    source = Path(_option(args, "--input"))
    if "--report" in args:
        report_path = Path(_option(args, "--report"))
    else:
        run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
        report_path = config.reports_root / "runs" / run_id / "gltf-validation.json"
    report = validate_glb(config, source, report_path)
    return 0, envelope(
        "validate",
        True,
        "Authoritative GLB passed Khronos validation",
        {
            "input": report["input"],
            "input_sha256": report["input_sha256"],
            "report_path": str(report_path.resolve(strict=False)),
            "errors": report["issues"].get("numErrors", 0),
            "warnings": report["issues"].get("numWarnings", 0),
        },
    )


def _optimize(args: list[str]) -> tuple[int, dict]:
    from datetime import datetime, timezone

    from .config import FactoryConfig
    from .optimizer import optimize_glb

    config = FactoryConfig.load()
    source = Path(_option(args, "--input"))
    destination = Path(_option(args, "--output"))
    if "--report" in args:
        report_path = Path(_option(args, "--report"))
    else:
        run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
        report_path = config.reports_root / "runs" / run_id / "optimization.json"
    report = optimize_glb(
        config,
        source,
        destination,
        report_path,
        pixel_atlas="--pixel-atlas" in args,
    )


def _preview(args: list[str]) -> tuple[int, dict]:
    from datetime import datetime, timezone

    from .config import FactoryConfig
    from .runtime_preview import preview_glb

    config = FactoryConfig.load()
    source = Path(_option(args, "--input"))
    screenshot = Path(_option(args, "--output"))
    if "--report" in args:
        report_path = Path(_option(args, "--report"))
    else:
        run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
        report_path = config.reports_root / "runs" / run_id / "threejs-preview.json"
    report = preview_glb(config, source, screenshot, report_path)
    return 0, envelope(
        "preview",
        True,
        "GLB loaded and rendered in the pinned Three.js viewer",
        {
            "source": report["source"],
            "screenshot": report["screenshot"],
            "mesh_count": report["viewer"]["mesh_count"],
            "triangle_count": report["viewer"]["triangle_count"],
            "report_path": str(report_path.resolve(strict=False)),
        },
    )
    return 0, envelope(
        "optimize",
        True,
        "Verified non-authoritative GLB derivative created",
        {
            "authoritative_source": report["authoritative_source"],
            "derivative": report["derivative"],
            "derivative_sha256": report["derivative_sha256"],
            "uv_max_drift": report["uv_max_drift"],
            "report_path": str(report_path.resolve(strict=False)),
        },
    )


def _verify(args: list[str]) -> tuple[int, dict]:
    from .config import FactoryConfig
    from .verification import verify

    config = FactoryConfig.load()
    ok, report = verify(config)
    if ok and "--save" in args:
        from .state import record_verification, refresh_bootstrap

        record_verification(config, report)
        refresh_bootstrap(config)
    result = envelope(
        "verify",
        ok,
        "Phase 1 verification passed"
        if ok
        else "Phase 1 verification failed",
        {
            "report_path": report["report_path"],
            "test_exit_code": report["test_exit_code"],
        },
        []
        if ok
        else [
            {
                "code": "verification_failed",
                "message": "Inspect the verification report",
            }
        ],
    )
    return (0 if ok else 1), result


def _handlers() -> dict[str, Handler]:
    return {
        "doctor": _doctor,
        "index-models": _index_models,
        "learn": _learn,
        "optimize": _optimize,
        "preview": _preview,
        "refresh-memory": _refresh_memory,
        "resume": _resume,
        "transfer-manifest": _transfer_manifest,
        "validate": _validate,
        "verify": _verify,
        "version": _version,
    }


def run(argv: list[str]) -> tuple[int, dict, bool]:
    json_output = "--json" in argv
    args = [item for item in argv if item != "--json"]
    command = args[0] if args else ""
    handlers = _handlers()
    if command not in handlers:
        result = envelope(
            command or "unknown",
            False,
            "Unknown factory command",
            errors=[
                {
                    "code": "unknown_command",
                    "message": command or "command required",
                }
            ],
        )
        return 2, result, json_output
    try:
        code, result = handlers[command](args[1:])
        return code, result, json_output
    except Exception as error:
        result = envelope(
            command,
            False,
            f"Command failed: {command}",
            errors=[{"code": "command_failed", "message": str(error)}],
        )
        return 1, result, json_output


def main(argv: list[str] | None = None) -> int:
    code, result, json_output = run(
        list(sys.argv[1:] if argv is None else argv)
    )
    print(json.dumps(result, indent=2) if json_output else result["summary"])
    return code
