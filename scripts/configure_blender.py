from pathlib import Path

import bpy


ADDON_MODULE = "blender_mcp_bridge"
# The factory root is the repository checkout that contains this script.
FACTORY_ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    bpy.ops.preferences.addon_enable(module=ADDON_MODULE)
    entry = bpy.context.preferences.addons.get(ADDON_MODULE)
    if entry is None:
        raise RuntimeError(f"Blender add-on did not enable: {ADDON_MODULE}")

    prefs = entry.preferences
    prefs.safe_mode = True
    prefs.port = 9876
    prefs.allow_inline_code = False
    prefs.approved_script_roots = str(FACTORY_ROOT)
    bpy.ops.wm.save_userpref()

    print(
        "BLENDER_MCP_CONFIGURED "
        f"module={ADDON_MODULE} safe_mode={prefs.safe_mode} "
        f"inline={prefs.allow_inline_code} port={prefs.port} "
        f"root={prefs.approved_script_roots}"
    )


if __name__ == "__main__":
    main()
