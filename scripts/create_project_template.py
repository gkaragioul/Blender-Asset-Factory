"""Create the canonical empty PS1 asset project template."""

from pathlib import Path

import bpy


# The factory root is the repository checkout that contains this script.
FACTORY_ROOT = Path(__file__).resolve().parents[1]
PROJECT_DIR = FACTORY_ROOT / "projects" / "PS1_Asset_Starter"
PROJECT_FILE = PROJECT_DIR / "PS1_Asset_Starter.blend"

bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)

scene = bpy.context.scene
scene.unit_settings.system = "METRIC"
scene.unit_settings.scale_length = 1.0
scene.render.engine = "BLENDER_EEVEE"
scene.render.resolution_x = 640
scene.render.resolution_y = 640

for name in ("ASSET", "COLLISION", "PREVIEW", "REFERENCES"):
    if name not in bpy.data.collections:
        collection = bpy.data.collections.new(name)
        scene.collection.children.link(collection)

scene["asset_factory_root"] = str(FACTORY_ROOT)
scene["assets_directory"] = str(FACTORY_ROOT / "assets")
scene["target_style"] = "PS1-era optimized Three.js"

PROJECT_DIR.mkdir(parents=True, exist_ok=True)
bpy.ops.wm.save_as_mainfile(filepath=str(PROJECT_FILE))
print(f"PROJECT_TEMPLATE_CREATED={PROJECT_FILE}")
