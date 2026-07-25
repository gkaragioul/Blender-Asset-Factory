"""Clean-sheet side-by-side double-barrel shotgun generator.

The design is silhouette-first: a sculpted walnut shoulder stock, narrow wrist,
recognizable break-action receiver, two uninterrupted parallel barrels, fore-end,
trigger guard, two triggers, top rib, bead sight, hinge pin, and muzzle openings.
No noisy procedural texture atlas is used; form and material separation do the work.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import bpy
from mathutils import Vector

ASSET_ID = "ww2_double_barrel_shotgun_clean_sheet_01"
OUTPUT_RELATIVE = "products/ww2_lowpoly_frontline_pack/clean-sheet-shotgun-v3"


def reset_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for collection in (bpy.data.meshes, bpy.data.curves, bpy.data.materials, bpy.data.cameras, bpy.data.lights):
        for block in list(collection):
            if block.users == 0:
                collection.remove(block)


def material(name: str, color, metallic: float = 0.0, roughness: float = 0.7) -> bpy.types.Material:
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = (*color, 1.0)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = (*color, 1.0)
        bsdf.inputs["Metallic"].default_value = metallic
        bsdf.inputs["Roughness"].default_value = roughness
    return mat


def extruded_profile(name: str, profile: list[tuple[float, float]], width: float, mat: bpy.types.Material, y_offset: float = 0.0) -> bpy.types.Object:
    """Extrude an X/Z side silhouette symmetrically along Y."""
    half = width / 2
    vertices = [(x, y_offset - half, z) for x, z in profile] + [(x, y_offset + half, z) for x, z in profile]
    n = len(profile)
    faces = []
    faces.append(tuple(range(n - 1, -1, -1)))
    faces.append(tuple(range(n, 2 * n)))
    for i in range(n):
        j = (i + 1) % n
        faces.append((i, j, n + j, n + i))
    mesh = bpy.data.meshes.new(f"{name}_Mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(mat)
    for polygon in obj.data.polygons:
        polygon.use_smooth = False
    return obj


def box(name: str, location, dimensions, mat, rotation=(0.0, 0.0, 0.0), bevel: float = 0.0) -> bpy.types.Object:
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=location, rotation=rotation)
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = dimensions
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    obj.data.materials.append(mat)
    if bevel > 0:
        modifier = obj.modifiers.new("LowPolyChamfer", "BEVEL")
        modifier.width = bevel
        modifier.segments = 1
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.modifier_apply(modifier=modifier.name)
    for polygon in obj.data.polygons:
        polygon.use_smooth = False
    return obj


def create_barrel(name: str, y: float, mat: bpy.types.Material, muzzle_mat: bpy.types.Material) -> list[bpy.types.Object]:
    """Create one uninterrupted barrel and a contrasting muzzle ring/opening."""
    start_x = 0.10
    end_x = 1.05
    length = end_x - start_x
    bpy.ops.mesh.primitive_cylinder_add(vertices=12, radius=0.027, depth=length, location=((start_x + end_x) / 2, y, 0.115), rotation=(0.0, math.pi / 2, 0.0))
    barrel = bpy.context.object
    barrel.name = name
    barrel.data.materials.append(mat)
    for polygon in barrel.data.polygons:
        polygon.use_smooth = False

    bpy.ops.mesh.primitive_torus_add(major_segments=12, minor_segments=4, location=(end_x, y, 0.115), major_radius=0.022, minor_radius=0.006, rotation=(0.0, math.pi / 2, 0.0))
    ring = bpy.context.object
    ring.name = f"{name}_Muzzle_Ring"
    ring.data.materials.append(muzzle_mat)
    for polygon in ring.data.polygons:
        polygon.use_smooth = False
    return [barrel, ring]


def curve_tube(name: str, points: list[tuple[float, float, float]], radius: float, mat: bpy.types.Material) -> bpy.types.Object:
    curve = bpy.data.curves.new(f"{name}_Curve", "CURVE")
    curve.dimensions = "3D"
    curve.resolution_u = 1
    curve.bevel_depth = radius
    curve.bevel_resolution = 0
    curve.resolution_u = 1
    spline = curve.splines.new("POLY")
    spline.points.add(len(points) - 1)
    for point, co in zip(spline.points, points):
        point.co = (*co, 1.0)
    obj = bpy.data.objects.new(name, curve)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(mat)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.convert(target="MESH")
    obj = bpy.context.object
    obj.name = name
    for polygon in obj.data.polygons:
        polygon.use_smooth = False
    return obj


def create_trigger_guard(mat: bpy.types.Material) -> bpy.types.Object:
    points = [
        (-0.145, -0.078, -0.015),
        (-0.125, -0.078, -0.080),
        (-0.050, -0.078, -0.105),
        (0.035, -0.078, -0.085),
        (0.070, -0.078, -0.025),
    ]
    return curve_tube("Trigger_Guard", points, 0.009, mat)


def create_trigger(name: str, x: float, mat: bpy.types.Material) -> bpy.types.Object:
    points = [(x, -0.076, -0.018), (x - 0.008, -0.077, -0.052), (x + 0.004, -0.077, -0.070)]
    return curve_tube(name, points, 0.006, mat)


def create_y_cylinder(name: str, location, radius: float, depth: float, mat, vertices: int = 12) -> bpy.types.Object:
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=depth, location=location, rotation=(math.pi / 2, 0.0, 0.0))
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(mat)
    for polygon in obj.data.polygons:
        polygon.use_smooth = False
    return obj


def build_shotgun() -> tuple[list[bpy.types.Object], dict[str, bpy.types.Material]]:
    walnut = material("Walnut_Main", (0.20, 0.055, 0.018), roughness=0.58)
    walnut_light = material("Walnut_Highlight", (0.34, 0.115, 0.030), roughness=0.55)
    walnut_dark = material("Walnut_Shadow", (0.075, 0.018, 0.008), roughness=0.62)
    blued_steel = material("Blued_Steel", (0.035, 0.050, 0.064), metallic=0.72, roughness=0.33)
    receiver_steel = material("Case_Hardened_Receiver", (0.16, 0.19, 0.20), metallic=0.62, roughness=0.40)
    polished = material("Polished_Edges", (0.50, 0.55, 0.56), metallic=0.85, roughness=0.22)
    black = material("Muzzle_Black", (0.006, 0.008, 0.010), metallic=0.25, roughness=0.45)
    brass = material("Brass_Controls", (0.48, 0.30, 0.055), metallic=0.72, roughness=0.30)
    rubber = material("Buttplate_Rubber", (0.025, 0.018, 0.014), roughness=0.90)

    parts: list[bpy.types.Object] = []

    # A clear shoulder-stock silhouette: tall butt, tapered comb, narrow neck.
    buttstock_profile = [
        (-0.88, 0.185), (-0.73, 0.195), (-0.50, 0.155), (-0.31, 0.105),
        (-0.205, 0.082), (-0.180, 0.035), (-0.245, -0.005), (-0.46, -0.050),
        (-0.70, -0.075), (-0.88, -0.055),
    ]
    buttstock = extruded_profile("Buttstock", buttstock_profile, 0.125, walnut)
    parts.append(buttstock)

    # The pistol-grip wrist is a distinct downward hook, not a disconnected cube.
    grip_profile = [
        (-0.34, 0.095), (-0.18, 0.075), (-0.145, 0.018), (-0.205, -0.165),
        (-0.300, -0.155), (-0.345, -0.035),
    ]
    parts.append(extruded_profile("Pistol_Grip_Wrist", grip_profile, 0.118, walnut_dark))

    # Raised cheek panel and clean wood grain accents as geometry, not noisy pixels.
    cheek_profile = [(-0.72, 0.135), (-0.50, 0.115), (-0.31, 0.075), (-0.43, 0.005), (-0.68, 0.005)]
    parts.append(extruded_profile("Walnut_Cheek_Panel", cheek_profile, 0.006, walnut_light, y_offset=-0.066))
    parts.append(box("Buttstock_Grain_Line_A", (-0.58, -0.070, 0.065), (0.30, 0.006, 0.012), walnut_dark, rotation=(0.0, -0.08, 0.0)))
    parts.append(box("Buttstock_Grain_Line_B", (-0.57, -0.070, 0.105), (0.22, 0.006, 0.009), walnut_light, rotation=(0.0, -0.04, 0.0)))
    parts.append(box("Rubber_Buttplate", (-0.895, 0.0, 0.062), (0.032, 0.138, 0.265), rubber, bevel=0.006))

    # Break-action receiver with a chamfered, visually substantial silhouette.
    receiver_profile = [
        (-0.18, 0.115), (-0.135, 0.165), (0.095, 0.165), (0.145, 0.120),
        (0.125, -0.010), (0.060, -0.050), (-0.120, -0.045), (-0.180, 0.005),
    ]
    parts.append(extruded_profile("Break_Action_Receiver", receiver_profile, 0.145, receiver_steel))
    parts.append(extruded_profile("Receiver_Side_Plate", [(-0.145, 0.120), (0.090, 0.120), (0.105, 0.010), (-0.105, -0.010)], 0.006, polished, y_offset=-0.076))
    parts.append(create_y_cylinder("Hinge_Pin", (0.075, 0.0, 0.015), 0.030, 0.165, polished))
    parts.append(box("Top_Lever", (-0.080, 0.0, 0.170), (0.095, 0.034, 0.014), polished, rotation=(0.0, 0.0, -0.10), bevel=0.004))
    parts.append(box("Safety_Button", (-0.160, 0.0, 0.138), (0.040, 0.036, 0.010), black, bevel=0.003))
    parts.append(box("Receiver_Engraving_A", (-0.030, -0.077, 0.075), (0.105, 0.006, 0.010), brass, rotation=(0.0, 0.10, 0.0)))
    parts.append(box("Receiver_Engraving_B", (-0.030, -0.077, 0.045), (0.075, 0.006, 0.008), brass, rotation=(0.0, -0.10, 0.0)))

    # Twin side-by-side barrels remain uninterrupted from receiver to muzzle.
    parts.extend(create_barrel("Left_Barrel", -0.036, blued_steel, black))
    parts.extend(create_barrel("Right_Barrel", 0.036, blued_steel, black))
    parts.append(box("Top_Rib", (0.575, 0.0, 0.147), (0.900, 0.028, 0.014), blued_steel, bevel=0.003))
    parts.append(box("Rib_Rear_Ramp", (0.145, 0.0, 0.150), (0.105, 0.045, 0.018), polished, rotation=(0.0, 0.04, 0.0), bevel=0.004))
    parts.append(create_y_cylinder("Front_Bead_Sight", (0.995, 0.0, 0.166), 0.009, 0.024, brass, vertices=10))

    # Sculpted fore-end bridges receiver and barrels as a familiar shotgun form.
    fore_profile = [
        (0.105, 0.045), (0.170, 0.080), (0.470, 0.073), (0.525, 0.040),
        (0.500, -0.005), (0.180, -0.015), (0.115, 0.010),
    ]
    parts.append(extruded_profile("Fore_End", fore_profile, 0.122, walnut))
    parts.append(extruded_profile("Fore_End_Checkering", [(0.210, 0.058), (0.440, 0.055), (0.465, 0.015), (0.220, 0.010)], 0.006, walnut_dark, y_offset=-0.065))
    for x in (0.245, 0.295, 0.345, 0.395):
        parts.append(box(f"Fore_End_Ridge_{x:.3f}", (x, -0.069, 0.035), (0.010, 0.006, 0.055), walnut_light, rotation=(0.0, 0.08, 0.0)))

    parts.append(create_trigger_guard(blued_steel))
    parts.append(create_trigger("Front_Trigger", -0.020, brass))
    parts.append(create_trigger("Rear_Trigger", -0.075, brass))

    materials = {
        "walnut": walnut, "walnut_light": walnut_light, "walnut_dark": walnut_dark,
        "blued_steel": blued_steel, "receiver_steel": receiver_steel, "polished": polished,
        "black": black, "brass": brass, "rubber": rubber,
    }
    return parts, materials


def triangulate(parts: list[bpy.types.Object]) -> None:
    for obj in parts:
        if obj.type != "MESH":
            continue
        bpy.ops.object.select_all(action="DESELECT")
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        modifier = obj.modifiers.new("Triangulate", "TRIANGULATE")
        bpy.ops.object.modifier_apply(modifier=modifier.name)


def triangle_count(parts: list[bpy.types.Object]) -> int:
    total = 0
    depsgraph = bpy.context.evaluated_depsgraph_get()
    for obj in parts:
        if obj.type != "MESH":
            continue
        evaluated = obj.evaluated_get(depsgraph)
        mesh = evaluated.to_mesh()
        try:
            mesh.calc_loop_triangles()
            total += len(mesh.loop_triangles)
        finally:
            evaluated.to_mesh_clear()
    return total


def setup_preview() -> None:
    ground_mat = material("Preview_Ground", (0.035, 0.038, 0.042), roughness=0.95)
    bpy.ops.mesh.primitive_plane_add(size=5.0, location=(0.05, 0.0, -0.19))
    ground = bpy.context.object
    ground.name = "PREVIEW_Ground"
    ground.data.materials.append(ground_mat)

    for name, location, energy, size, color in (
        ("PREVIEW_Key", (-2.5, -3.5, 3.4), 850, 3.5, (1.0, 0.79, 0.60)),
        ("PREVIEW_Fill", (2.5, -2.0, 1.8), 500, 3.0, (0.58, 0.72, 1.0)),
        ("PREVIEW_Rim", (1.5, 2.0, 2.5), 650, 2.2, (0.72, 0.82, 1.0)),
    ):
        bpy.ops.object.light_add(type="AREA", location=location)
        light = bpy.context.object
        light.name = name
        light.data.energy = energy
        light.data.size = size
        light.data.color = color

    bpy.ops.object.camera_add(location=(1.55, -5.3, 1.10))
    camera = bpy.context.object
    camera.name = "PREVIEW_Camera"
    target = Vector((0.06, 0.0, 0.045))
    camera.rotation_euler = (target - camera.location).to_track_quat("-Z", "Y").to_euler()
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = 2.18
    bpy.context.scene.camera = camera

    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.eevee.taa_render_samples = 96
    scene.render.resolution_x = 1200
    scene.render.resolution_y = 700
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False
    scene.world.color = (0.018, 0.020, 0.024)
    scene.view_settings.look = "AgX - Medium High Contrast"


def export_asset(repo_root: Path, parts: list[bpy.types.Object]) -> dict:
    output = repo_root / OUTPUT_RELATIVE
    output.mkdir(parents=True, exist_ok=True)
    blend_path = output / f"{ASSET_ID}.blend"
    glb_path = output / f"{ASSET_ID}.glb"
    preview_path = output / f"{ASSET_ID}_preview.png"
    preview_side = output / f"{ASSET_ID}_preview_side.png"
    preview_muzzle = output / f"{ASSET_ID}_preview_muzzle.png"
    manifest_path = output / "manifest.json"

    setup_preview()
    bpy.context.scene.render.filepath = str(preview_path)
    bpy.ops.render.render(write_still=True)

    camera = bpy.context.scene.camera
    target = Vector((0.06, 0.0, 0.035))
    camera.location = (0.06, -5.5, 0.72)
    camera.rotation_euler = (target - camera.location).to_track_quat("-Z", "Y").to_euler()
    camera.data.ortho_scale = 2.12
    bpy.context.scene.render.filepath = str(preview_side)
    bpy.ops.render.render(write_still=True)

    camera.location = (2.35, -2.30, 0.63)
    target = Vector((0.35, 0.0, 0.075))
    camera.rotation_euler = (target - camera.location).to_track_quat("-Z", "Y").to_euler()
    camera.data.ortho_scale = 2.30
    bpy.context.scene.render.filepath = str(preview_muzzle)
    bpy.ops.render.render(write_still=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))

    bpy.ops.object.select_all(action="DESELECT")
    for obj in parts:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = parts[0]
    bpy.ops.export_scene.gltf(filepath=str(glb_path), export_format="GLB", use_selection=True, export_apply=True, export_yup=True)

    triangles = triangle_count(parts)
    manifest = {
        "schema_version": 1,
        "asset_id": ASSET_ID,
        "design": "clean_sheet_v3_side_by_side_break_action_shotgun",
        "status": "candidate_pending_visual_and_runtime_validation",
        "triangles": triangles,
        "triangle_budget": 1800,
        "within_budget": triangles <= 1800,
        "semantic_parts": [obj.name for obj in parts],
        "materials": sorted({slot.material.name for obj in parts if obj.type == "MESH" for slot in obj.material_slots if slot.material}),
        "files": {
            "blend": str(blend_path),
            "glb": str(glb_path),
            "preview": str(preview_path),
            "preview_side": str(preview_side),
            "preview_muzzle": str(preview_muzzle),
            "manifest": str(manifest_path),
        },
    }
    if not manifest["within_budget"]:
        raise RuntimeError(f"Triangle budget exceeded: {triangles}")
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def main() -> dict:
    repo_root = Path(__file__).resolve().parents[1]
    reset_scene()
    parts, _materials = build_shotgun()
    triangulate(parts)
    for obj in parts:
        obj["asset_id"] = ASSET_ID
        obj["semantic_part"] = obj.name
    result = export_asset(repo_root, parts)
    print("CLEAN_SHEET_SHOTGUN_RESULT=" + json.dumps(result, sort_keys=True))
    return result


__result__ = main()
