from __future__ import annotations

import json
import sys
from collections.abc import Callable

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


def _handlers() -> dict[str, Handler]:
    return {
        "doctor": _doctor,
        "refresh-memory": _refresh_memory,
        "resume": _resume,
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
    code, result = handlers[command](args[1:])
    return code, result, json_output


def main(argv: list[str] | None = None) -> int:
    code, result, json_output = run(
        list(sys.argv[1:] if argv is None else argv)
    )
    print(json.dumps(result, indent=2) if json_output else result["summary"])
    return code
