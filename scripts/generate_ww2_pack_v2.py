"""Polish pass 2 generator for the AI-only WW2 low-poly pack.

This pass writes to a separate folder and adds richer silhouettes, lumpy props,
embedded low-res texture atlases, and manifest visual-score estimates.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
from pathlib import Path

import bpy
from mathutils import Vector

OUTPUT_ROOT = "products/ww2_lowpoly_frontline_pack/polish-pass-2"
STYLE_PASS = "polish_pass_2"

ASSET_DEFINITIONS = {
    "ww2_pump_shotgun_01": {"type": "weapon", "budget": 1200, "kind": "pump"},
    "ww2_double_barrel_shotgun_01": {"type": "weapon", "budget": 1000, "kind": "double"},
    "ww2_bolt_rifle_01": {"type": "weapon", "budget": 1200, "kind": "rifle"},
    "ww2_smg_01": {"type": "weapon", "budget": 1200, "kind": "smg"},
    "ww2_ammo_crate_01": {"type": "prop", "budget": 600, "kind": "crate"},
    "ww2_sandbag_stack_01": {"type": "environment", "budget": 1200, "kind": "sandbags"},
}

COLORS = {
    "wood": [(42, 19, 8), (78, 37, 16), (118, 70, 31), (178, 124, 67)],
    "steel": [(14, 18, 21), (32, 39, 45), (75, 84, 88), (158, 164, 160)],
    "canvas": [(63, 58, 38), (92, 83, 51), (132, 120, 72), (188, 177, 111)],
    "olive": [(31, 40, 22), (58, 72, 37), (94, 106, 56), (150, 154, 94)],
    "marking": [(196, 181, 112), (235, 225, 169), (96, 88, 52), (38, 34, 23)],
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


def create_pixel_atlas(asset_dir: Path, asset_id: str, theme: str, size: int = 64) -> tuple[bpy.types.Image, Path]:
    rng = random.Random(asset_id + theme + STYLE_PASS)
    palette = COLORS[theme]
    image = bpy.data.images.new(f"{asset_id}_{theme}_atlas", size, size, alpha=True)
    pixels: list[float] = []
    for y in range(size):
        for x in range(size):
            band = min(3, x * 4 // size)
            base = palette[(band + (y // 13) + (x // 17)) % len(palette)]
            noise = rng.randint(-16, 16)
            if (x + y) % 19 == 0:
                noise += 28
            if (x * 3 + y * 5) % 31 == 0:
                noise -= 26
            color = [max(0, min(255, channel + noise)) / 255.0 for channel in base]
            pixels.extend([color[0], color[1], color[2], 1.0])
    image.pixels.foreach_set(pixels)
    image.file_format = "PNG"
    atlas_path = asset_dir / f"{asset_id}_{theme}_atlas.png"
    image.filepath_raw = str(atlas_path)
    image.save()
    return image, atlas_path


def textured_mat(name: str, image: bpy.types.Image, tint: tuple[float, float, float, float], metallic: float = 0.0) -> bpy.types.Material:
    material = bpy.data.materials.new(name)
    material.diffuse_color = tint
    material.use_nodes = True
    nodes = material.node_tree.nodes
    bsdf = nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Metallic"].default_value = metallic
        bsdf.inputs["Roughness"].default_value = 0.94
        bsdf.inputs["Base Color"].default_value = tint
        tex = nodes.new(type="ShaderNodeTexImage")
        tex.image = image
        tex.interpolation = "Closest"
        material.node_tree.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    return material


def ensure_uv(obj: bpy.types.Object) -> None:
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    if not obj.data.uv_layers:
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="SELECT")
        bpy.ops.uv.smart_project(angle_limit=1.15192, island_margin=0.03)
        bpy.ops.object.mode_set(mode="OBJECT")


def cube(name: str, loc, scale, material, rot=(0, 0, 0)) -> bpy.types.Object:
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc, rotation=rot)
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    obj.data.materials.append(material)
    for poly in obj.data.polygons:
        poly.use_smooth = False
    ensure_uv(obj)
    return obj


def cyl(name: str, loc, radius: float, depth: float, material, vertices: int = 10, rot=(0, math.pi / 2, 0)) -> bpy.types.Object:
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=depth, location=loc, rotation=rot)
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(material)
    for poly in obj.data.polygons:
        poly.use_smooth = False
    ensure_uv(obj)
    return obj


def mesh_prism(name: str, loc, length: float, width: float, front_height: float, back_height: float, material) -> bpy.types.Object:
    hx = length / 2
    hy = width / 2
    verts = [
        (-hx, -hy, -back_height / 2), (-hx, hy, -back_height / 2), (-hx, -hy, back_height / 2), (-hx, hy, back_height / 2),
        (hx, -hy, -front_height / 2), (hx, hy, -front_height / 2), (hx, -hy, front_height / 2), (hx, hy, front_height / 2),
    ]
    faces = [(0, 4, 5, 1), (2, 3, 7, 6), (0, 1, 3, 2), (4, 6, 7, 5), (0, 2, 6, 4), (1, 5, 7, 3)]
    mesh = bpy.data.meshes.new(f"{name}_Mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    obj.location = loc
    obj.data.materials.append(material)
    ensure_uv(obj)
    return obj


def make_lumpy_bag(name: str, loc, scale, material, rot=(0, 0, 0)) -> bpy.types.Object:
    bpy.ops.mesh.primitive_uv_sphere_add(segments=8, ring_count=4, radius=1.0, location=loc, rotation=rot)
    obj = bpy.context.object
    obj.name = name
    obj.scale = scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    obj.data.materials.append(material)
    for vertex in obj.data.vertices:
        vertex.co.z *= 0.72 + 0.10 * math.sin(vertex.co.x * 7.0)
        vertex.co.x *= 1.0 + 0.08 * math.sin(vertex.co.y * 9.0)
    for poly in obj.data.polygons:
        poly.use_smooth = False
    ensure_uv(obj)
    return obj


def add_scratch_blocks(prefix: str, material, y: float = -0.052) -> list[bpy.types.Object]:
    return [
        cube(f"{prefix}_EdgeWear_1", (-0.04, y, 0.124), (0.052, 0.006, 0.010), material),
        cube(f"{prefix}_EdgeWear_2", (0.07, y, 0.112), (0.032, 0.006, 0.010), material),
        cube(f"{prefix}_Stencil_1", (-0.135, y, 0.070), (0.020, 0.006, 0.020), material),
        cube(f"{prefix}_Stencil_2", (-0.102, y, 0.070), (0.020, 0.006, 0.020), material),
    ]


def build_weapon(asset_id: str, kind: str, mats: dict[str, bpy.types.Material]) -> list[bpy.types.Object]:
    wood, wood_hi, steel, edge, dark, marking = mats["wood"], mats["wood_hi"], mats["steel"], mats["edge"], mats["dark"], mats["marking"]
    parts: list[bpy.types.Object] = []
    if kind == "pump":
        parts += [
            mesh_prism("Tapered_Walnut_Stock", (-0.44, 0, 0.02), 0.42, 0.115, 0.105, 0.165, wood),
            cube("Rubber_Buttplate", (-0.665, 0, 0.018), (0.035, 0.13, 0.18), dark),
            cube("Beveled_Receiver", (-0.12, 0, 0.052), (0.255, 0.095, 0.115), steel),
            cyl("Blued_Barrel", (0.31, 0, 0.105), 0.026, 0.77, steel, 12),
            cyl("Dark_Magazine_Tube", (0.27, 0, 0.020), 0.022, 0.62, dark, 10),
            cube("Ribbed_Pump_Core", (0.095, 0, 0.000), (0.20, 0.112, 0.060), wood_hi),
            cube("Pump_Ridge_A", (0.035, -0.058, 0.006), (0.020, 0.012, 0.068), wood),
            cube("Pump_Ridge_B", (0.095, -0.058, 0.006), (0.020, 0.012, 0.068), wood),
            cube("Trigger_Guard_Bow", (-0.165, 0, -0.058), (0.125, 0.020, 0.030), dark),
            cube("Trigger", (-0.145, -0.010, -0.072), (0.018, 0.016, 0.048), dark),
            cube("Muzzle_Cap", (0.705, 0, 0.105), (0.026, 0.060, 0.060), edge),
            cube("Front_Bead", (0.645, 0, 0.145), (0.020, 0.018, 0.032), edge),
            cube("Rear_Notch", (-0.185, 0, 0.135), (0.060, 0.024, 0.026), edge),
        ]
    elif kind == "double":
        parts += [
            mesh_prism("Curved_Walnut_Stock", (-0.43, 0, 0.015), 0.43, 0.115, 0.100, 0.165, wood),
            cube("Buttplate", (-0.665, 0, 0.014), (0.032, 0.13, 0.18), dark),
            cube("Break_Action_Block", (-0.135, 0, 0.060), (0.175, 0.095, 0.095), steel),
            cyl("Upper_Barrel_Muzzle", (0.29, 0.028, 0.105), 0.023, 0.78, steel, 12),
            cyl("Lower_Barrel_Muzzle", (0.29, -0.028, 0.105), 0.023, 0.78, steel, 12),
            cube("Hinge_Pin", (-0.060, 0, 0.055), (0.030, 0.13, 0.030), edge),
            cube("Break_Lever", (-0.170, 0, 0.136), (0.080, 0.028, 0.018), edge),
            mesh_prism("Splinter_Foreend", (0.060, 0, 0.025), 0.260, 0.108, 0.045, 0.065, wood_hi),
            cube("Twin_Muzzle_Cap", (0.700, 0, 0.105), (0.030, 0.095, 0.058), edge),
            cube("Trigger_Guard_Bow", (-0.205, 0, -0.057), (0.112, 0.020, 0.030), dark),
        ]
    elif kind == "rifle":
        parts += [
            mesh_prism("Long_Tapered_Stock", (-0.315, 0, 0.020), 0.74, 0.105, 0.080, 0.145, wood),
            cube("Buttplate", (-0.710, 0, 0.018), (0.030, 0.120, 0.165), dark),
            cube("Receiver_With_Ejection_Port", (-0.040, 0, 0.105), (0.190, 0.080, 0.074), steel),
            cube("Ejection_Port_Highlight", (0.010, -0.045, 0.118), (0.060, 0.006, 0.026), edge),
            cyl("Long_Barrel", (0.470, 0, 0.125), 0.018, 0.92, steel, 12),
            cube("Front_Barrel_Band", (0.310, 0, 0.102), (0.035, 0.090, 0.055), edge),
            cube("Bolt_Handle_Ball", (-0.035, -0.070, 0.105), (0.050, 0.024, 0.048), edge),
            cube("Ladder_Rear_Sight", (0.130, 0, 0.160), (0.055, 0.020, 0.038), edge),
            cube("Front_Sight_Post", (0.875, 0, 0.160), (0.022, 0.018, 0.042), edge),
            cube("Trigger_Guard", (-0.140, 0, -0.055), (0.112, 0.020, 0.030), dark),
        ]
    elif kind == "smg":
        parts += [
            cube("Pressed_Steel_Receiver", (-0.040, 0, 0.060), (0.390, 0.085, 0.108), steel),
            cyl("Short_Barrel_Shroud", (0.260, 0, 0.083), 0.027, 0.380, dark, 12),
            cube("Muzzle_Nut", (0.465, 0, 0.083), (0.036, 0.065, 0.065), edge),
            cube("Angled_Box_Magazine", (-0.020, 0, -0.095), (0.080, 0.073, 0.235), dark, rot=(0.12, 0, 0)),
            cube("Pistol_Grip_Shaped", (-0.155, 0, -0.090), (0.076, 0.075, 0.175), wood, rot=(0.18, 0, 0)),
            cube("Receiver_Slot_A", (0.035, -0.047, 0.075), (0.090, 0.006, 0.016), edge),
            cube("Receiver_Slot_B", (0.142, -0.047, 0.075), (0.055, 0.006, 0.016), edge),
            cube("Wire_Stock_Top", (-0.345, 0.046, 0.100), (0.360, 0.018, 0.022), edge),
            cube("Wire_Stock_Bottom", (-0.345, -0.046, 0.005), (0.360, 0.018, 0.022), edge),
            cube("Stock_Butt_Wire", (-0.545, 0, 0.052), (0.030, 0.116, 0.115), edge),
            cube("Front_Sight", (0.392, 0, 0.130), (0.025, 0.020, 0.038), edge),
        ]
    parts += add_scratch_blocks(asset_id, marking)
    return parts


def build_crate(asset_id: str, mats: dict[str, bpy.types.Material]) -> list[bpy.types.Object]:
    wood, hi, dark, marking = mats["wood"], mats["wood_hi"], mats["dark"], mats["marking"]
    parts = [cube("Inset_Crate_Core", (0, 0, 0.18), (0.50, 0.30, 0.25), wood)]
    for y in (-0.165, 0.165):
        parts += [
            cube("Top_Rail", (0, y, 0.325), (0.56, 0.038, 0.040), hi), cube("Bottom_Rail", (0, y, 0.035), (0.56, 0.038, 0.040), hi),
            cube("Left_Post", (-0.265, y, 0.180), (0.038, 0.038, 0.285), hi), cube("Right_Post", (0.265, y, 0.180), (0.038, 0.038, 0.285), hi),
            cube("Diagonal_Brace", (0, y, 0.180), (0.045, 0.030, 0.56), hi, rot=(0, math.radians(52), 0)),
            cube("Stencil_Block_A", (-0.115, y * 1.03, 0.210), (0.030, 0.006, 0.035), marking),
            cube("Stencil_Block_B", (-0.070, y * 1.03, 0.210), (0.020, 0.006, 0.035), marking),
            cube("Metal_Latch", (0.150, y * 1.04, 0.230), (0.055, 0.010, 0.038), dark),
        ]
    return parts


def build_sandbags(_asset_id: str, mats: dict[str, bpy.types.Material]) -> list[bpy.types.Object]:
    canvas, hi, dark = mats["canvas"], mats["canvas_hi"], mats["dark"]
    parts: list[bpy.types.Object] = []
    rows = [(0.0, 5, 0.070), (0.055, 4, 0.185), (-0.020, 3, 0.300)]
    for row, (offset, count, z) in enumerate(rows):
        for i in range(count):
            x = (i - (count - 1) / 2) * 0.235 + offset
            material = canvas if (i + row) % 2 else hi
            parts.append(make_lumpy_bag(f"Lumpy_Sandbag_R{row}_{i}", (x, 0, z), (0.125, 0.090, 0.050), material, rot=(0.02 * i, 0.04 * row, (i % 3 - 1) * 0.12)))
            parts.append(cube(f"Dark_Seam_R{row}_{i}", (x, -0.084, z + 0.005), (0.130, 0.008, 0.012), dark))
    return parts


def score_asset_candidate(asset_id: str, definition: dict, triangles: int, object_count: int, texture_count: int) -> dict:
    silhouette = 0.80 + min(0.10, object_count / 160)
    texture = 0.84 if texture_count >= 3 else 0.70
    lightweight = 0.92 if triangles <= definition["budget"] else 0.50
    material = 0.85 if object_count >= 10 else 0.72
    appeal = 0.80 if definition["type"] == "weapon" else 0.82
    total = round(silhouette * 0.22 + texture * 0.18 + lightweight * 0.14 + material * 0.18 + appeal * 0.28, 3)
    return {"total": total, "minimum": 0.82, "passed": total >= 0.82, "criteria": {"silhouette": round(silhouette, 3), "texture": texture, "lightweight": lightweight, "material_separation": material, "storefront_appeal": appeal}}


def build_asset(asset_id: str, definition: dict, mats: dict[str, bpy.types.Material]) -> list[bpy.types.Object]:
    kind = definition["kind"]
    if definition["type"] == "weapon":
        return build_weapon(asset_id, kind, mats)
    if kind == "crate":
        return build_crate(asset_id, mats)
    if kind == "sandbags":
        return build_sandbags(asset_id, mats)
    raise ValueError(asset_id)


def triangulate(objects: list[bpy.types.Object]) -> None:
    for obj in objects:
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.select_all(action="DESELECT")
        obj.select_set(True)
        mod = obj.modifiers.new("Factory_Triangulate", "TRIANGULATE")
        mod.keep_custom_normals = True
        bpy.ops.object.modifier_apply(modifier=mod.name)


def triangle_count(objects: list[bpy.types.Object]) -> int:
    depsgraph = bpy.context.evaluated_depsgraph_get()
    total = 0
    for obj in objects:
        evaluated = obj.evaluated_get(depsgraph)
        mesh = evaluated.to_mesh()
        try:
            mesh.calc_loop_triangles()
            total += len(mesh.loop_triangles)
        finally:
            evaluated.to_mesh_clear()
    return total


def frame_scene(asset_type: str) -> None:
    ground = bpy.data.materials.new("MAT_Preview_Ground")
    ground.diffuse_color = (0.025, 0.027, 0.030, 1)
    bpy.ops.mesh.primitive_plane_add(size=4.0, location=(0, 0, -0.015))
    plane = bpy.context.object
    plane.name = "PREVIEW_Ground"
    plane.data.materials.append(ground)
    for name, loc, energy, size in (("PREVIEW_Key", (-2.6, -3.2, 3.0), 620, 3.2), ("PREVIEW_Rim", (2.4, 1.8, 2.2), 240, 2.0)):
        bpy.ops.object.light_add(type="AREA", location=loc)
        light = bpy.context.object
        light.name = name
        light.data.energy = energy
        light.data.size = size
    camera_loc = (1.45, -2.1, 0.78) if asset_type == "weapon" else (1.35, -1.95, 1.05)
    bpy.ops.object.camera_add(location=camera_loc)
    camera = bpy.context.object
    target = Vector((0.02, 0, 0.09 if asset_type == "weapon" else 0.17))
    camera.rotation_euler = (target - camera.location).to_track_quat("-Z", "Y").to_euler()
    camera.data.lens = 60 if asset_type == "weapon" else 48
    bpy.context.scene.camera = camera
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.eevee.taa_render_samples = 64
    scene.render.resolution_x = 960
    scene.render.resolution_y = 540
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.world.color = (0.018, 0.019, 0.022)


def material_set(asset_dir: Path, asset_id: str) -> tuple[dict[str, bpy.types.Material], list[str]]:
    atlases = {}
    atlas_paths = []
    for theme in ("wood", "steel", "canvas", "olive", "marking"):
        image, path = create_pixel_atlas(asset_dir, asset_id, theme)
        atlases[theme] = image
        atlas_paths.append(str(path))
    mats = {
        "wood": textured_mat("MAT_Aged_Walnut_Atlas", atlases["wood"], (0.38, 0.18, 0.08, 1)),
        "wood_hi": textured_mat("MAT_Worn_Walnut_Edge_Atlas", atlases["wood"], (0.65, 0.39, 0.18, 1)),
        "steel": textured_mat("MAT_Blued_Steel_Atlas", atlases["steel"], (0.08, 0.10, 0.12, 1), 0.35),
        "edge": textured_mat("MAT_Bright_Worn_Edge_Atlas", atlases["steel"], (0.50, 0.55, 0.55, 1), 0.25),
        "dark": textured_mat("MAT_Oil_Dark_Atlas", atlases["steel"], (0.025, 0.027, 0.030, 1), 0.20),
        "canvas": textured_mat("MAT_Muddy_Canvas_Atlas", atlases["canvas"], (0.42, 0.37, 0.22, 1)),
        "canvas_hi": textured_mat("MAT_Worn_Canvas_Edge_Atlas", atlases["canvas"], (0.62, 0.55, 0.32, 1)),
        "olive": textured_mat("MAT_Olive_Drab_Atlas", atlases["olive"], (0.23, 0.29, 0.15, 1)),
        "marking": textured_mat("MAT_Fictional_Stencil_Atlas", atlases["marking"], (0.78, 0.71, 0.45, 1)),
    }
    return mats, atlas_paths


def export_asset(root: Path, pack_id: str, asset_id: str, definition: dict) -> dict:
    reset_scene()
    asset_dir = root / asset_id
    asset_dir.mkdir(parents=True, exist_ok=True)
    mats, atlas_paths = material_set(asset_dir, asset_id)
    objects = build_asset(asset_id, definition, mats)
    triangulate(objects)
    for obj in objects:
        obj["asset_id"] = asset_id
        obj["pack_id"] = pack_id
        obj["style_profile"] = "ps1_ww2_frontline"
        obj["style_pass"] = STYLE_PASS
    frame_scene(definition["type"])
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
    score = score_asset_candidate(asset_id, definition, tris, len(objects), len(atlas_paths))
    report = {
        "schema_version": 1,
        "asset_id": asset_id,
        "pack_id": pack_id,
        "display_name": asset_id.replace("_", " ").title(),
        "style_profile": "ps1_ww2_frontline",
        "style_pass": STYLE_PASS,
        "type": definition["type"],
        "triangles": tris,
        "triangle_budget": definition["budget"],
        "within_budget": tris <= definition["budget"],
        "materials": sorted({slot.material.name for obj in objects for slot in obj.material_slots if slot.material}),
        "texture_atlases": atlas_paths,
        "visual_score": score,
        "files": {"blend": str(blend), "glb": str(glb), "preview": str(preview), "manifest": str(manifest)},
        "sale_ready_gate": "polish_pass_2_generated_pending_validation",
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
    reports = [export_asset(output_root, job["pack_id"], asset_id, ASSET_DEFINITIONS[asset_id]) for asset_id in selected]
    batch = {"schema_version": 1, "pack_id": job["pack_id"], "style_pass": STYLE_PASS, "output_root": str(output_root), "assets": reports}
    output_root.mkdir(parents=True, exist_ok=True)
    (output_root / "batch-manifest.json").write_text(json.dumps(batch, indent=2), encoding="utf-8")
    print("ASSET_FACTORY_POLISH_PASS_2_RESULT=" + json.dumps(batch, sort_keys=True))
    return batch


__result__ = main()
