"""End-to-end MCP health check: Codex transport -> MCP server -> Blender bridge."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


FACTORY_ROOT = Path(__file__).resolve().parents[1]
# Path to the blender-mcp-server executable; defaults to the one on PATH.
SERVER = os.environ.get("BLENDER_MCP_SERVER", "blender-mcp-server")
BLENDER = os.environ.get(
    "BLENDER_BIN", r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe"
)


async def main() -> None:
    env = dict(os.environ)
    env["BLENDER_BIN"] = BLENDER
    parameters = StdioServerParameters(command=SERVER, args=[], env=env)
    async with stdio_client(parameters) as (reader, writer):
        async with ClientSession(reader, writer) as session:
            await session.initialize()
            tools = await session.list_tools()
            scene = await session.call_tool("blender_scene_get_info", {})
            security = await session.call_tool(
                "blender_python_exec",
                {
                    "script_path": str(FACTORY_ROOT / "scripts" / "mcp_root_probe.py"),
                    "args": {},
                    "timeout_seconds": 30,
                },
            )
            payload = {
                "tool_count": len(tools.tools),
                "has_python": any(tool.name == "blender_python_exec" for tool in tools.tools),
                "has_export": any(tool.name == "blender_export_gltf" for tool in tools.tools),
                "scene_response": [getattr(item, "text", str(item)) for item in scene.content],
                "security_response": [getattr(item, "text", str(item)) for item in security.content],
                "is_error": bool(scene.isError),
                "security_is_error": bool(security.isError),
            }
            print("MCP_HEALTHCHECK=" + json.dumps(payload, sort_keys=True))


if __name__ == "__main__":
    asyncio.run(main())
