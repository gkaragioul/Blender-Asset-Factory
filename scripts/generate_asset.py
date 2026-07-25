"""Deterministic PS1-era asset generator for Blender 5.x.

Run directly:
  blender --background --factory-startup --python generate_asset.py -- --spec path/to/spec.json

Run through Blender MCP:
  blender_python_exec(script_path=..., args={"spec": "..."})
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector


def parse_inputs() -> dict:
    mcp_args = globals().get("args")
    if isinstance(mcp_args, dict) and mcp_args.get("spec"):
        return mcp_args

    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--spec", required=True)
    parsed = parser.parse_args(argv)
    return {"spec": parsed.spec}


def reset_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for datablocks in (bpy.data.meshes, bpy.data.curves, bpy.data.materials, bpy.data.cameras, bpy.data.lights):
        for block in list(datablocks):
            if block.users == 0:
                datablocks.remove(block)


def make_material(name: str, rgba: list[float], roughness: float = 0.9) -> bpy.types.Material:
    material = bpy.data.materials.new(name=name)
    material.diffuse_color = rgba
    material.use_nodes = True
    node = material.node_tree.nodes.get("Principled BSDF")
    if node:
        node.inputs["Base Color"].default_value = rgba
        node.inputs["Roughness"].default_value = roughness
        node.inputs["Metallic"].default_value = 0.0
    return material


def add_box(
    name: str,
    location: tuple[float, float, float],
    dimensions: tuple[float, float, float],
    material: bpy.types.Material,
    rotation_y: float = 0.0,
) -> bpy.types.Object:
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=location, rotation=(0.0, rotation_y, 0.0))
    obj = bpy.context.active_object
    obj.name = name
    obj.dimensions = dimensions
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    obj.data.materials.append(material)
    for polygon in obj.data.polygons:
        polygon.use_smooth = False
    return obj


def join_meshes(objects: list[bpy.types.Object], name: str) -> bpy.types.Object:
    bpy.ops.object.select_all(action="DESELECT")
    for obj in objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]
    bpy.ops.object.join()
    result = bpy.context.active_object
    result.name = name
    result.data.name = f"{name}_Mesh"
    triangulate = result.modifiers.new(name="PS1_Triangulate", type="TRIANGULATE")
    triangulate.keep_custom_normals = True
    bpy.context.view_layer.objects.active = result
    bpy.ops.object.modifier_apply(modifier=triangulate.name)
    return result


def create_ps1_crate(spec: dict) -> bpy.types.Object:
    palette = spec["palette"]
    dark = make_material("PS1_Wood_Dark", palette["wood_dark"])
    mid = make_material("PS1_Wood_Mid", palette["wood_mid"])
    light = make_material("PS1_Wood_Light", palette["wood_light"])

    parts: list[bpy.types.Object] = []
    parts.append(add_box("Crate_Core", (0, 0, 1), (1.72, 1.72, 1.72), dark))

    # Chunky frame pieces intentionally preserve the angular fifth-generation silhouette.
    for y in (-0.91, 0.91):
        for x in (-0.80, 0.80):
            parts.append(add_box("Frame_V", (x, y, 1), (0.18, 0.16, 1.92), mid))
        for z in (0.12, 1.88):
            parts.append(add_box("Frame_H", (0, y, z), (1.78, 0.16, 0.18), light))
        for angle in (-math.radians(45), math.radians(45)):
            parts.append(add_box("Brace_X", (0, y * 1.01, 1), (0.15, 0.12, 2.28), mid, rotation_y=angle))

    for x in (-0.91, 0.91):
        for z in (0.12, 1.88):
            parts.append(add_box("Side_H", (x, 0, z), (0.16, 1.78, 0.18), light))

    asset = join_meshes(parts, "Asset_PS1_Wood_Crate_01")
    asset["asset_id"] = spec["asset_id"]
    asset["style"] = spec["style"]
    asset["triangle_budget"] = int(spec["triangle_budget"])
    asset["collision_shape"] = "box"
    asset["web_scale_meters"] = 1.0
    return asset


def point_camera(camera: bpy.types.Object, target: tuple[float, float, float]) -> None:
    direction = Vector(target) - camera.location
    camera.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def prepare_preview(spec: dict, asset: bpy.types.Object) -> None:
    ground_mat = make_material("Preview_Ground", spec["palette"]["ground"])
    bpy.ops.mesh.primitive_plane_add(size=24, location=(0, 0, 0))
    ground = bpy.context.active_object
    ground.name = "PREVIEW_Ground"
    ground.data.materials.append(ground_mat)

    bpy.ops.object.camera_add(location=(4.3, -5.5, 3.7))
    camera = bpy.context.active_object
    camera.name = "PREVIEW_Camera"
    camera.data.lens = 52
    point_camera(camera, (0, 0, 0.95))
    bpy.context.scene.camera = camera

    for name, location, energy, size in (
        ("PREVIEW_Key", (-3.5, -4.0, 6.0), 950, 4.0),
        ("PREVIEW_Rim", (4.0, 2.0, 4.5), 700, 3.0),
    ):
        light_data = bpy.data.lights.new(name=name, type="AREA")
        light_data.energy = energy
        light_data.shape = "DISK"
        light_data.size = size
        light_obj = bpy.data.objects.new(name, light_data)
        bpy.context.collection.objects.link(light_obj)
        light_obj.location = location
        direction = asset.location - light_obj.location + Vector((0, 0, 1))
        light_obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()

    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = 640
    scene.render.resolution_y = 640
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False
    scene.world.color = (0.012, 0.015, 0.022)


def triangle_count(obj: bpy.types.Object) -> int:
    depsgraph = bpy.context.evaluated_depsgraph_get()
    evaluated = obj.evaluated_get(depsgraph)
    mesh = evaluated.to_mesh()
    try:
        mesh.calc_loop_triangles()
        return len(mesh.loop_triangles)
    finally:
        evaluated.to_mesh_clear()


def export_asset(spec: dict, asset: bpy.types.Object) -> dict:
    output_root = Path(spec["output_directory"]).resolve()
    asset_dir = output_root / spec["asset_id"]
    asset_dir.mkdir(parents=True, exist_ok=True)

    blend_path = asset_dir / f"{spec['asset_id']}.blend"
    glb_path = asset_dir / f"{spec['asset_id']}.glb"
    preview_path = asset_dir / f"{spec['asset_id']}_preview.png"
    manifest_path = asset_dir / "manifest.json"

    bpy.context.scene.render.filepath = str(preview_path)
    bpy.ops.render.render(write_still=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))

    bpy.ops.object.select_all(action="DESELECT")
    asset.select_set(True)
    bpy.context.view_layer.objects.active = asset
    bpy.ops.export_scene.gltf(
        filepath=str(glb_path),
        export_format="GLB",
        use_selection=True,
        export_apply=True,
        export_yup=True,
    )

    triangles = triangle_count(asset)
    report = {
        "asset_id": spec["asset_id"],
        "display_name": spec["display_name"],
        "style": spec["style"],
        "generator": spec["generator"],
        "triangles": triangles,
        "triangle_budget": spec["triangle_budget"],
        "within_budget": triangles <= int(spec["triangle_budget"]),
        "dimensions_m": [round(float(value), 4) for value in asset.dimensions],
        "files": {
            "blend": str(blend_path),
            "glb": str(glb_path),
            "preview": str(preview_path),
            "manifest": str(manifest_path),
        },
    }
    if not report["within_budget"]:
        raise RuntimeError(f"Triangle budget exceeded: {triangles} > {spec['triangle_budget']}")
    manifest_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main() -> dict:
    inputs = parse_inputs()
    spec_path = Path(inputs["spec"]).resolve()
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    if spec.get("generator") != "ps1_crate":
        raise ValueError(f"Unsupported generator: {spec.get('generator')}")

    reset_scene()
    asset = create_ps1_crate(spec)
    prepare_preview(spec, asset)
    report = export_asset(spec, asset)
    print("ASSET_FACTORY_RESULT=" + json.dumps(report, sort_keys=True))
    return report


__result__ = main()
