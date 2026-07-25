"""Generate the first AI-only WW2 low-poly commercial batch in Blender.

Run:
  blender --background --factory-startup --python scripts/generate_ww2_pack.py -- \
    --job specs/jobs/ww2_lowpoly_frontline_pack.json
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector

OUTPUT_ROOT = "products/ww2_lowpoly_frontline_pack/generated"

ASSET_DEFINITIONS = {
    "ww2_pump_shotgun_01": {"type": "weapon", "budget": 1000, "length": 1.03},
    "ww2_double_barrel_shotgun_01": {"type": "weapon", "budget": 800, "length": 0.98},
    "ww2_bolt_rifle_01": {"type": "weapon", "budget": 1000, "length": 1.18},
    "ww2_smg_01": {"type": "weapon", "budget": 1100, "length": 0.66},
    "ww2_ammo_crate_01": {"type": "prop", "budget": 350},
    "ww2_sandbag_stack_01": {"type": "environment", "budget": 900},
}

PALETTE = {
    "walnut": (0.28, 0.12, 0.045, 1.0),
    "walnut_light": (0.55, 0.31, 0.14, 1.0),
    "steel": (0.08, 0.10, 0.115, 1.0),
    "steel_edge": (0.36, 0.42, 0.43, 1.0),
    "dark": (0.018, 0.020, 0.024, 1.0),
    "canvas": (0.42, 0.37, 0.22, 1.0),
    "canvas_light": (0.62, 0.55, 0.32, 1.0),
    "olive": (0.20, 0.26, 0.13, 1.0),
    "marking": (0.82, 0.76, 0.52, 1.0),
}


def parse_args() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--job", required=True)
    parser.add_argument("--only", action="append", default=[])
    return parser.parse_args(argv)


def reset_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()
    for collection in (bpy.data.meshes, bpy.data.materials, bpy.data.cameras, bpy.data.lights, bpy.data.images):
        for block in list(collection):
            if block.users == 0:
                collection.remove(block)


def mat(name: str, color: tuple[float, float, float, float], metallic: float = 0.0, roughness: float = 0.92) -> bpy.types.Material:
    material = bpy.data.materials.new(name)
    material.diffuse_color = color
    material.use_nodes = True
    node = material.node_tree.nodes.get("Principled BSDF")
    if node:
        node.inputs["Base Color"].default_value = color
        node.inputs["Metallic"].default_value = metallic
        node.inputs["Roughness"].default_value = roughness
    return material


def cube(name: str, loc, scale, material, rot=(0, 0, 0)) -> bpy.types.Object:
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc, rotation=rot)
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    obj.data.materials.append(material)
    for poly in obj.data.polygons:
        poly.use_smooth = False
    return obj


def cyl(name: str, loc, radius: float, depth: float, material, vertices: int = 8, rot=(0, math.pi / 2, 0)) -> bpy.types.Object:
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=depth, location=loc, rotation=rot)
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(material)
    for poly in obj.data.polygons:
        poly.use_smooth = False
    return obj


def add_label_blocks(prefix: str, x: float, y: float, z: float, material) -> list[bpy.types.Object]:
    return [
        cube(f"{prefix}_Pixel_Mark_A", (x, y, z), (0.035, 0.006, 0.018), material),
        cube(f"{prefix}_Pixel_Mark_B", (x + 0.05, y, z), (0.028, 0.006, 0.018), material),
        cube(f"{prefix}_Pixel_Mark_C", (x + 0.092, y, z), (0.014, 0.006, 0.018), material),
    ]


def weapon_common(asset_id: str, kind: str) -> list[bpy.types.Object]:
    wood = mat("MAT_Aged_Walnut", PALETTE["walnut"])
    wood_hi = mat("MAT_Walnut_Edge", PALETTE["walnut_light"])
    steel = mat("MAT_Blued_Steel", PALETTE["steel"], metallic=0.4)
    edge = mat("MAT_Worn_Steel_Edge", PALETTE["steel_edge"], metallic=0.2)
    dark = mat("MAT_Oil_Dark", PALETTE["dark"], metallic=0.3)
    parts: list[bpy.types.Object] = []

    if kind == "pump":
        parts += [
            cube("Stock_Angled_Walnut", (-0.42, 0, 0.02), (0.36, 0.105, 0.13), wood, rot=(0, 0.10, 0)),
            cube("Stock_Butt_Dark", (-0.62, 0, 0.015), (0.035, 0.12, 0.16), dark),
            cube("Receiver_Box", (-0.11, 0, 0.045), (0.25, 0.09, 0.105), steel),
            cyl("Barrel_Long", (0.27, 0, 0.095), 0.025, 0.68, steel, 10),
            cyl("Magazine_Tube", (0.24, 0, 0.015), 0.022, 0.56, dark, 8),
            cube("Pump_Foregrip_Wood", (0.10, 0, -0.005), (0.18, 0.105, 0.055), wood_hi),
            cube("Trigger_Guard", (-0.16, 0, -0.055), (0.11, 0.018, 0.028), dark),
            cube("Front_Sight", (0.58, 0, 0.13), (0.025, 0.018, 0.035), edge),
            cube("Rear_Sight", (-0.16, 0, 0.125), (0.055, 0.022, 0.026), edge),
        ]
    elif kind == "double":
        parts += [
            cube("Stock_Walnut", (-0.42, 0, 0.02), (0.38, 0.105, 0.13), wood, rot=(0, 0.08, 0)),
            cube("Break_Action_Receiver", (-0.12, 0, 0.055), (0.16, 0.088, 0.09), steel),
            cyl("Upper_Barrel", (0.24, 0.025, 0.095), 0.022, 0.72, steel, 10),
            cyl("Lower_Barrel", (0.24, -0.025, 0.095), 0.022, 0.72, steel, 10),
            cube("Fore_End_Walnut", (0.03, 0, 0.02), (0.22, 0.10, 0.05), wood_hi),
            cube("Break_Lever", (-0.16, 0, 0.125), (0.06, 0.025, 0.018), edge),
            cube("Trigger_Guard", (-0.20, 0, -0.052), (0.10, 0.018, 0.028), dark),
        ]
    elif kind == "rifle":
        parts += [
            cube("Full_Walnut_Stock", (-0.25, 0, 0.015), (0.74, 0.095, 0.105), wood, rot=(0, 0.035, 0)),
            cube("Receiver_Bolt", (-0.03, 0, 0.095), (0.18, 0.075, 0.07), steel),
            cyl("Long_Rifle_Barrel", (0.42, 0, 0.12), 0.018, 0.86, steel, 10),
            cube("Bolt_Handle", (-0.04, -0.065, 0.095), (0.055, 0.018, 0.038), edge),
            cube("Front_Sight", (0.82, 0, 0.15), (0.022, 0.018, 0.04), edge),
            cube("Rear_Sight", (0.10, 0, 0.15), (0.045, 0.018, 0.03), edge),
            cube("Trigger_Guard", (-0.12, 0, -0.055), (0.10, 0.018, 0.028), dark),
        ]
    elif kind == "smg":
        parts += [
            cube("Stamped_Receiver", (-0.04, 0, 0.05), (0.36, 0.08, 0.10), steel),
            cyl("Short_Barrel", (0.22, 0, 0.08), 0.023, 0.34, dark, 10),
            cube("Box_Magazine", (-0.03, 0, -0.09), (0.075, 0.07, 0.22), dark, rot=(0.08, 0, 0)),
            cube("Wire_Stock_Top", (-0.32, 0.04, 0.08), (0.32, 0.018, 0.022), edge),
            cube("Wire_Stock_Bottom", (-0.32, -0.04, 0.00), (0.32, 0.018, 0.022), edge),
            cube("Grip", (-0.13, 0, -0.08), (0.07, 0.07, 0.16), wood),
            cube("Front_Sight", (0.38, 0, 0.12), (0.025, 0.018, 0.035), edge),
        ]
    parts += add_label_blocks(asset_id, -0.08, -0.048, 0.105, edge)
    return parts


def ammo_crate(asset_id: str) -> list[bpy.types.Object]:
    wood = mat("MAT_Crate_Wood", PALETTE["walnut"])
    hi = mat("MAT_Crate_Edge", PALETTE["walnut_light"])
    mark = mat("MAT_Fictional_Stencil", PALETTE["marking"])
    parts = [cube("Crate_Core", (0, 0, 0.16), (0.46, 0.28, 0.24), wood)]
    for z in (0.035, 0.285):
        parts.append(cube("Crate_Band_X", (0, -0.145, z), (0.52, 0.035, 0.035), hi))
        parts.append(cube("Crate_Band_X", (0, 0.145, z), (0.52, 0.035, 0.035), hi))
    for x in (-0.24, 0.24):
        parts.append(cube("Crate_Side_Post", (x, -0.145, 0.16), (0.035, 0.035, 0.28), hi))
        parts.append(cube("Crate_Side_Post", (x, 0.145, 0.16), (0.035, 0.035, 0.28), hi))
    parts += add_label_blocks(asset_id, -0.12, -0.163, 0.19, mark)
    return parts


def sandbags(asset_id: str) -> list[bpy.types.Object]:
    canvas = mat("MAT_Canvas_Sandbag", PALETTE["canvas"])
    hi = mat("MAT_Canvas_Edge", PALETTE["canvas_light"])
    parts: list[bpy.types.Object] = []
    rows = [(0.0, 5, 0.06), (0.07, 4, 0.16), (0.0, 3, 0.26)]
    for row, (offset, count, z) in enumerate(rows):
        for i in range(count):
            x = (i - (count - 1) / 2) * 0.24 + offset
            bag = cube(f"Sandbag_R{row}_{i}", (x, 0, z), (0.22, 0.18, 0.09), canvas if (i + row) % 2 else hi, rot=(0, 0, (i % 3 - 1) * 0.06))
            parts.append(bag)
            parts.append(cube(f"Sandbag_Seam_R{row}_{i}", (x, -0.092, z + 0.01), (0.16, 0.01, 0.014), hi))
    return parts


def build_asset(asset_id: str) -> list[bpy.types.Object]:
    if asset_id == "ww2_pump_shotgun_01":
        return weapon_common(asset_id, "pump")
    if asset_id == "ww2_double_barrel_shotgun_01":
        return weapon_common(asset_id, "double")
    if asset_id == "ww2_bolt_rifle_01":
        return weapon_common(asset_id, "rifle")
    if asset_id == "ww2_smg_01":
        return weapon_common(asset_id, "smg")
    if asset_id == "ww2_ammo_crate_01":
        return ammo_crate(asset_id)
    if asset_id == "ww2_sandbag_stack_01":
        return sandbags(asset_id)
    raise ValueError(asset_id)


def triangulate(objects: list[bpy.types.Object]) -> None:
    for obj in objects:
        bpy.context.view_layer.objects.active = obj
        mod = obj.modifiers.new("Factory_Triangulate", "TRIANGULATE")
        mod.keep_custom_normals = True
        bpy.ops.object.select_all(action="DESELECT")
        obj.select_set(True)
        bpy.ops.object.modifier_apply(modifier=mod.name)


def triangle_count(objects: list[bpy.types.Object]) -> int:
    total = 0
    depsgraph = bpy.context.evaluated_depsgraph_get()
    for obj in objects:
        mesh = obj.evaluated_get(depsgraph).to_mesh()
        try:
            mesh.calc_loop_triangles()
            total += len(mesh.loop_triangles)
        finally:
            obj.evaluated_get(depsgraph).to_mesh_clear()
    return total


def frame_scene(objects: list[bpy.types.Object], asset_type: str) -> None:
    ground = mat("MAT_Preview_Dark_Ground", (0.025, 0.027, 0.030, 1.0))
    bpy.ops.mesh.primitive_plane_add(size=4.0, location=(0, 0, -0.01))
    plane = bpy.context.object
    plane.name = "PREVIEW_Ground"
    plane.data.materials.append(ground)
    bpy.ops.object.light_add(type="AREA", location=(-2.8, -3.8, 3.2))
    key = bpy.context.object
    key.name = "PREVIEW_Key"
    key.data.energy = 550
    key.data.size = 3.2
    bpy.ops.object.light_add(type="AREA", location=(2.5, 2.0, 2.4))
    rim = bpy.context.object
    rim.name = "PREVIEW_Rim"
    rim.data.energy = 180
    rim.data.size = 2.0
    camera_loc = (1.5, -2.2, 1.15) if asset_type != "weapon" else (1.55, -2.0, 0.75)
    bpy.ops.object.camera_add(location=camera_loc)
    camera = bpy.context.object
    target = Vector((0.02, 0, 0.08 if asset_type == "weapon" else 0.16))
    direction = target - camera.location
    camera.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    camera.data.lens = 58 if asset_type == "weapon" else 45
    bpy.context.scene.camera = camera
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = 960
    scene.render.resolution_y = 540
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.world.color = (0.02, 0.02, 0.024)


def export_asset(root: Path, pack_id: str, asset_id: str, definition: dict) -> dict:
    reset_scene()
    objects = build_asset(asset_id)
    triangulate(objects)
    for obj in objects:
        obj["asset_id"] = asset_id
        obj["pack_id"] = pack_id
        obj["style_profile"] = "ps1_ww2_frontline"
    frame_scene(objects, definition["type"])
    asset_dir = root / asset_id
    asset_dir.mkdir(parents=True, exist_ok=True)
    blend = asset_dir / f"{asset_id}.blend"
    glb = asset_dir / f"{asset_id}.glb"
    preview = asset_dir / f"{asset_id}_preview.png"
    manifest = asset_dir / "manifest.json"
    bpy.context.scene.render.filepath = str(preview)
    bpy.ops.render.render(write_still=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(blend))
    bpy.ops.object.select_all(action="DESELECT")
    for obj in objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]
    bpy.ops.export_scene.gltf(filepath=str(glb), export_format="GLB", use_selection=True, export_apply=True, export_yup=True)
    tris = triangle_count(objects)
    report = {
        "schema_version": 1,
        "asset_id": asset_id,
        "pack_id": pack_id,
        "display_name": asset_id.replace("_", " ").title(),
        "style_profile": "ps1_ww2_frontline",
        "type": definition["type"],
        "triangles": tris,
        "triangle_budget": definition["budget"],
        "within_budget": tris <= definition["budget"],
        "materials": sorted({slot.material.name for obj in objects for slot in obj.material_slots if slot.material}),
        "files": {"blend": str(blend), "glb": str(glb), "preview": str(preview), "manifest": str(manifest)},
        "sale_ready_gate": "generated_pending_validation",
    }
    if not report["within_budget"]:
        raise RuntimeError(f"{asset_id} triangle budget exceeded: {tris}>{definition['budget']}")
    manifest.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main() -> dict:
    parsed = parse_args()
    job_path = Path(parsed.job).resolve()
    job = json.loads(job_path.read_text(encoding="utf-8"))
    repo_root = job_path.parents[2]
    output_root = repo_root / OUTPUT_ROOT
    selected = parsed.only or job["first_batch"]
    reports = []
    for asset_id in selected:
        if asset_id not in ASSET_DEFINITIONS:
            raise ValueError(f"No asset definition for {asset_id}")
        reports.append(export_asset(output_root, job["pack_id"], asset_id, ASSET_DEFINITIONS[asset_id]))
    batch = {"schema_version": 1, "pack_id": job["pack_id"], "output_root": str(output_root), "assets": reports}
    (output_root / "batch-manifest.json").write_text(json.dumps(batch, indent=2), encoding="utf-8")
    print("ASSET_FACTORY_BATCH_RESULT=" + json.dumps(batch, sort_keys=True))
    return batch


__result__ = main()
