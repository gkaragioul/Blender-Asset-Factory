from __future__ import annotations

import json
import sys
from collections.abc import Callable
from pathlib import Path

from . import __version__
from .catalog import Catalog
from .pack import build_pack
from .style_contract import StyleContract


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
    return 0, envelope(
        "optimize",
        True,
        "Optimized derivative created and validated",
        {
            "authoritative_source": report["authoritative_source"],
            "derivative": report["derivative"],
            "source_sha256": report["source_sha256"],
            "derivative_sha256": report["derivative_sha256"],
            "uv_max_drift": report["uv_max_drift"],
            "report_path": str(report_path.resolve(strict=False)),
        },
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


def _report(args: list[str]) -> tuple[int, dict]:
    from datetime import datetime, timezone

    from .config import FactoryConfig
    from .contact_sheet import build_contact_sheet

    config = FactoryConfig.load()
    manifest = Path(_option(args, "--manifest"))
    output = Path(_option(args, "--output"))
    if "--qa-report" in args:
        report_path = Path(_option(args, "--qa-report"))
    else:
        run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
        report_path = config.reports_root / "runs" / run_id / "contact-sheet.json"
    report = build_contact_sheet(config, manifest, output, report_path)
    return 0, envelope(
        "report",
        True,
        "Deterministic QA contact sheet created",
        {"output": report["output"], "output_sha256": report["output_sha256"], "view_ids": report["view_ids"], "report_path": str(report_path.resolve(strict=False))},
    )


def _release(args: list[str]) -> tuple[int, dict]:
    from .config import FactoryConfig
    from .release import release_package

    result = release_package(FactoryConfig.load(), Path(_option(args, "--job")))
    return 0, envelope(
        "release",
        True,
        "Validated asset package published transactionally",
        result,
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


def _art(args: list[str]) -> tuple[int, dict]:
    from .art_runs import approve_concept, create_art_run, stage_concept_candidate
    from .config import FactoryConfig

    if not args:
        raise ValueError("art requires init, stage-concept, or approve-concept")
    config = FactoryConfig.load()
    action = args[0]
    action_args = args[1:]
    if action == "init":
        result = create_art_run(
            config,
            Path(_option(action_args, "--brief")),
            run_id=_option(action_args, "--run-id"),
        )
        summary = "Immutable art run initialized"
        data = result
    elif action == "stage-concept":
        result = stage_concept_candidate(
            config,
            _option(action_args, "--run-id"),
            _option(action_args, "--candidate-id"),
            Path(_option(action_args, "--image")),
            _json_input(config, action_args, "--metadata"),
        )
        summary = "Concept candidate staged immutably"
        data = result
    elif action == "approve-concept":
        result = approve_concept(
            config,
            _option(action_args, "--run-id"),
            _option(action_args, "--candidate-id"),
            approved_by=_option(action_args, "--approved-by"),
            evidence=_option(action_args, "--evidence"),
        )
        summary = "Concept approval gate recorded"
        data = {**result, "concept_approved": True}
    else:
        raise ValueError(f"unknown art action: {action}")
    return 0, envelope("art", True, summary, data)


def _pack(args: list[str]) -> tuple[int, dict]:
    from .config import FactoryConfig

    config = FactoryConfig.load()
    catalog_path = Path(_option(args, "--catalog")).resolve(strict=False)
    sources_path = Path(_option(args, "--sources")).resolve(strict=False)
    output_root = Path(_option(args, "--out")).resolve(strict=False)
    validate = "--skip-validate" not in args
    try:
        if not catalog_path.is_file():
            raise FileNotFoundError(f"catalog does not exist: {catalog_path}")
        if not sources_path.is_file():
            raise FileNotFoundError(f"sources map does not exist: {sources_path}")
        contract_hint = json.loads(catalog_path.read_text(encoding="utf-8-sig"))
        contract = StyleContract.load(
            config, catalog_path.parent / contract_hint["style_contract"]
        )
        catalog = Catalog.load(config, catalog_path, contract)
        sources = {
            key: Path(value)
            for key, value in json.loads(
                sources_path.read_text(encoding="utf-8-sig")
            ).items()
        }
        report = build_pack(
            config, catalog, contract, sources, output_root, validate=validate
        )
    except Exception as error:
        return 1, envelope(
            "pack",
            False,
            "Pack build could not start",
            errors=[{"type": type(error).__name__, "detail": str(error)}],
        )
    counts = report["counts"]
    summary = (
        f"{catalog.pack_id}: {counts['pass']} pass, {counts['reject']} reject"
    )
    return (
        0 if report["ok"] else 2,
        envelope("pack", report["ok"], summary, data=report),
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
        "Phase 2 verification passed"
        if ok
        else "Phase 2 verification failed",
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
        "art": _art,
        "doctor": _doctor,
        "index-models": _index_models,
        "learn": _learn,
        "optimize": _optimize,
        "pack": _pack,
        "preview": _preview,
        "report": _report,
        "release": _release,
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
