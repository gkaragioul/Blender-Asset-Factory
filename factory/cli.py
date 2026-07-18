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


def _handlers() -> dict[str, Handler]:
    return {"version": _version}


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
