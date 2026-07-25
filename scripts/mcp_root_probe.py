"""Return the active Blender MCP security configuration."""

entry = bpy.context.preferences.addons.get("blender_mcp_bridge")
if entry is None:
    raise RuntimeError("Blender MCP Bridge is not enabled")

prefs = entry.preferences
__result__ = {
    "safe_mode": bool(prefs.safe_mode),
    "allow_inline_code": bool(prefs.allow_inline_code),
    "approved_script_roots": prefs.approved_script_roots,
    "port": int(prefs.port),
}
