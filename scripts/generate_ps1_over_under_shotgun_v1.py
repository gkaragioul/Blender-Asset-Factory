"""Build the final PS1-era over-under trench shotgun: game-ready budget,
flat-shaded unlit materials, LOD1, and a collision proxy.

Builds on top of the validated reference-derived prototype
(ps1_reference_derived_trench_shotgun_01) by re-running the structural import
and stock-attachment steps, then applying PS1-authentic finishing:
  - lower triangle budget (no PBR gloss any more)
  - small nearest-filtered indexed-style texture
  - unlit flat vertex/texture shading
  - LOD1 aggressive reduction
  - simple box collision proxy
"""

from __future__ import annotations

import json
import math
import subprocess
import sys
from pathlib import Path

import bpy
from mathutils import Vector

ASSET_ID = "ps1_over_under_trench_shotgun_v1"
OUTPUT_RELATIVE = "products/ww2_lowpoly_frontline_pack/ps1-over-under-shotgun-v1"
TARGET_TRIANGLES = 2200
LOD1_TARGET_TRIANGLES = 900
TEXTURE_SIZE = 128
STRUCTURAL_SOURCE = "projects/ww2_lowpoly_frontline_pack/benchmark-shotgun-v1/references/source-mesh/shotgun-fbx/source/shotgun.fbx"
STRUCTURAL_TEXTURE = "projects/ww2_lowpoly_frontline_pack/benchmark-shotgun-v1/references/source-mesh/shotgun-fbx/textures/shotgun_lambert2_BaseColor.jpg"
PROTOTYPE_ATLAS = "products/ww2_lowpoly_frontline_pack/source-derived-shotgun-v1/ps1_reference_derived_trench_shotgun_01_source_atlas_256.png"


def reset_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for collection in (bpy.data.meshes, bpy.data.curves, bpy.data.materials, bpy.data.cameras, bpy.data.lights, bpy.data.images):
        for block in list(collection):
            if block.users == 0:
                collection.remove(block)


def mesh_bounds(objects: list[bpy.types.Object]):
    points = [obj.matrix_world @ Vector(corner) for obj in objects for corner in obj.bound_box]
    minimum = Vector((min(p.x for p in points), min(p.y for p in points), min(p.z for p in points)))
    maximum = Vector((max(p.x for p in points), max(p.y for p in points), max(p.z for p in points)))
    return minimum, maximum, (minimum + maximum) / 2


def object_triangles(obj: bpy.types.Object) -> int:
    obj.data.calc_loop_triangles()
    return len(obj.data.loop_triangles)


def total_triangles(objects: list[bpy.types.Object]) -> int:
    return sum(object_triangles(obj) for obj in objects if obj.type == "MESH")


def apply_modifier(obj: bpy.types.Object, modifier) -> None:
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.modifier_apply(modifier=modifier.name)


def make_flat_material(name: str, color, unlit: bool = True):
    material = bpy.data.materials.new(name)
    material.diffuse_color = (*color, 1.0)
    material.use_nodes = True
    bsdf = material.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Roughness"].default_value = 1.0
    if "Specular IOR Level" in bsdf.inputs:
        bsdf.inputs["Specular IOR Level"].default_value = 0.0
    material["ps1_unlit"] = True
    return material


def extruded_profile(name: str, profile: list[tuple[float, float]], width: float, material, y_offset: float = 0.0):
    half = width / 2
    vertices = [(x, y_offset - half, z) for x, z in profile] + [(x, y_offset + half, z) for x, z in profile]
    count = len(profile)
    faces = [tuple(range(count - 1, -1, -1)), tuple(range(count, count * 2))]
    for index in range(count):
        following = (index + 1) % count
        faces.append((index, following, count + following, count + index))
    mesh = bpy.data.meshes.new(f"{name}_Mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(material)
    for polygon in obj.data.polygons:
        polygon.use_smooth = False
    return obj


def make_box(name: str, location, dimensions, material=None, bevel: float = 0.0):
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=location)
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = dimensions
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if material:
        obj.data.materials.append(material)
    if bevel:
        modifier = obj.modifiers.new("PS1_Chamfer", "BEVEL")
        modifier.width = bevel
        modifier.segments = 1
        apply_modifier(obj, modifier)
    for polygon in obj.data.polygons:
        polygon.use_smooth = False
    return obj


def import_structural_source(repo_root: Path) -> list[bpy.types.Object]:
    source = repo_root / STRUCTURAL_SOURCE
    bpy.ops.import_scene.fbx(filepath=str(source))
    objects = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    for obj in objects:
        obj.rotation_euler.rotate_axis("Y", math.pi / 2)
        obj.scale = (1.6, 1.6, 1.6)
        obj.name = f"ReferenceMechanic_{obj.name}"
    bpy.context.view_layer.update()

    receiver = next(obj for obj in objects if obj.name.endswith("polySurface14"))
    points = [receiver.matrix_world @ Vector(corner) for corner in receiver.bound_box]
    receiver_center = Vector(
        (
            (min(p.x for p in points) + max(p.x for p in points)) / 2,
            (min(p.y for p in points) + max(p.y for p in points)) / 2,
            (min(p.z for p in points) + max(p.z for p in points)) / 2,
        )
    )
    for obj in objects:
        obj.location -= receiver_center
        bpy.ops.object.select_all(action="DESELECT")
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
    return objects


def make_full_stock(materials: dict[str, bpy.types.Material], structural: list[bpy.types.Object]) -> list[bpy.types.Object]:
    # The source FBX already includes its own complete wooden shoulder stock
    # (polySurface14/15), so no extra full-stock geometry is added here.
    # Only a small M1897-influenced steel accent (sling loop) is added as a
    # restrained period detail, attached directly to the existing stock.
    receiver = next(obj for obj in structural if obj.name.endswith("polySurface14"))
    points = [receiver.matrix_world @ Vector(corner) for corner in receiver.bound_box]
    receiver_rear_x = min(p.x for p in points)
    receiver_z_center = (min(p.z for p in points) + max(p.z for p in points)) / 2
    receiver_z_half = (max(p.z for p in points) - min(p.z for p in points)) / 2
    sling = make_box(
        "Rear_Sling_Loop",
        (receiver_rear_x + 0.045, 0.0, receiver_z_center - receiver_z_half * 0.9),
        (0.024, 0.012, 0.007),
        materials["steel"],
    )
    return [sling]


def reduce_ps1_source(objects: list[bpy.types.Object], target_total: int) -> dict[str, int]:
    before = total_triangles(objects)
    for obj in objects:
        triangles = object_triangles(obj)
        if triangles >= 800:
            ratio = 0.11
        elif triangles >= 300:
            ratio = 0.20
        elif triangles >= 60:
            ratio = 0.55
        else:
            continue
        modifier = obj.modifiers.new("PS1_Selective_Decimate", "DECIMATE")
        modifier.decimate_type = "COLLAPSE"
        modifier.ratio = ratio
        modifier.use_collapse_triangulate = True
        apply_modifier(obj, modifier)
        for polygon in obj.data.polygons:
            polygon.use_smooth = False

    current = total_triangles(objects)
    if current > target_total:
        overall_ratio = max(0.05, (target_total / current) * 0.9)
        for obj in objects:
            if object_triangles(obj) < 12:
                continue
            modifier = obj.modifiers.new("PS1_Global_Trim", "DECIMATE")
            modifier.decimate_type = "COLLAPSE"
            modifier.ratio = overall_ratio
            modifier.use_collapse_triangulate = True
            apply_modifier(obj, modifier)
            for polygon in obj.data.polygons:
                polygon.use_smooth = False
    return {"before": before, "after": total_triangles(objects)}


def apply_ps1_texture(repo_root: Path, structural: list[bpy.types.Object]) -> Path:
    output = repo_root / OUTPUT_RELATIVE
    output.mkdir(parents=True, exist_ok=True)
    prototype_atlas = repo_root / PROTOTYPE_ATLAS
    ps1_texture_path = output / f"{ASSET_ID}_texture_{TEXTURE_SIZE}.png"
    subprocess.run(
        ["/home/<user>/.hermes/hermes-agent/venv/bin/python3", str(repo_root / "scripts" / "prepare_ps1_over_under_texture.py"), str(prototype_atlas), str(ps1_texture_path)],
        check=True,
        cwd=repo_root,
    )
    image = bpy.data.images.load(str(ps1_texture_path), check_existing=True)
    material = bpy.data.materials.new("PS1_Unlit_Atlas")
    material.use_nodes = True
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    bsdf = nodes.get("Principled BSDF")
    texture = nodes.new("ShaderNodeTexImage")
    texture.name = "PS1_Nearest_Atlas"
    texture.image = image
    texture.interpolation = "Closest"
    links.new(texture.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 1.0
    if "Specular IOR Level" in bsdf.inputs:
        bsdf.inputs["Specular IOR Level"].default_value = 0.0
    material["ps1_unlit"] = True
    for obj in structural:
        obj.data.materials.clear()
        obj.data.materials.append(material)
        for polygon in obj.data.polygons:
            polygon.use_smooth = False
    return ps1_texture_path


def create_materials():
    return {
        "walnut": make_flat_material("PS1_Walnut_Unlit", (0.025, 0.004, 0.001)),
        "steel": make_flat_material("PS1_Worn_Steel_Unlit", (0.070, 0.085, 0.095)),
        "steel_dark": make_flat_material("PS1_Parkerized_Steel_Unlit", (0.012, 0.018, 0.023)),
    }


def triangulate(objects: list[bpy.types.Object]):
    for obj in objects:
        modifier = obj.modifiers.new("Runtime_Triangulate", "TRIANGULATE")
        apply_modifier(obj, modifier)


def duplicate_object(obj: bpy.types.Object, new_name: str) -> bpy.types.Object:
    new_data = obj.data.copy()
    new_obj = obj.copy()
    new_obj.data = new_data
    new_obj.name = new_name
    bpy.context.collection.objects.link(new_obj)
    return new_obj


def make_lod1(hero_objects: list[bpy.types.Object], reducible_names: set[str]) -> list[bpy.types.Object]:
    lod1_objects = []
    for obj in hero_objects:
        clone = duplicate_object(obj, f"PS1_LOD1_{obj.name}")
        clone.location = obj.location.copy()
        lod1_objects.append(clone)
    reducible = [obj for obj in lod1_objects if obj.name.replace("PS1_LOD1_", "", 1) in reducible_names]
    fixed = [obj for obj in lod1_objects if obj not in reducible]
    current_reducible = total_triangles(reducible)
    budget_for_reducible = max(60, LOD1_TARGET_TRIANGLES - total_triangles(fixed))
    if current_reducible > budget_for_reducible:
        overall_ratio = max(0.05, budget_for_reducible / current_reducible)
        for obj in reducible:
            if object_triangles(obj) < 10:
                continue
            modifier = obj.modifiers.new("PS1_LOD1_Decimate", "DECIMATE")
            modifier.decimate_type = "COLLAPSE"
            modifier.ratio = overall_ratio
            modifier.use_collapse_triangulate = True
            apply_modifier(obj, modifier)
            for polygon in obj.data.polygons:
                polygon.use_smooth = False
    for obj in lod1_objects:
        modifier = obj.modifiers.new("LOD1_Triangulate", "TRIANGULATE")
        apply_modifier(obj, modifier)
    return lod1_objects


def make_collision_proxy(hero_objects: list[bpy.types.Object]) -> bpy.types.Object:
    minimum, maximum, center = mesh_bounds(hero_objects)
    size = maximum - minimum
    collision_material = make_flat_material("PS1_Collision_Debug", (0.1, 0.9, 0.2))
    box = make_box("COLLISION_SHOTGUN", (center.x, center.y, center.z), (size.x, size.y, size.z), collision_material)
    box["collision_proxy"] = True
    box.display_type = "WIRE"
    box.hide_render = True
    box.hide_viewport = True
    return box


def add_preview_scene(objects: list[bpy.types.Object]):
    minimum, maximum, center = mesh_bounds(objects)
    size = maximum - minimum
    extent = max(size)
    ground_material = make_flat_material("PREVIEW_Ground_Material", (0.025, 0.028, 0.032))
    bpy.ops.mesh.primitive_plane_add(size=4, location=(center.x, center.y, minimum.z - 0.035))
    ground = bpy.context.object
    ground.name = "PREVIEW_Ground"
    ground.data.materials.append(ground_material)
    for name, location, energy, size_value in (
        ("PREVIEW_Key", center + Vector((-1.2, -1.6, 1.4)), 900, 2.5),
        ("PREVIEW_Fill", center + Vector((1.4, -1.1, 0.8)), 500, 2.0),
        ("PREVIEW_Rim", center + Vector((0.5, 1.2, 1.1)), 650, 1.8),
    ):
        bpy.ops.object.light_add(type="AREA", location=location)
        light = bpy.context.object
        light.name = name
        light.data.energy = energy
        light.data.size = size_value
    bpy.ops.object.camera_add()
    camera = bpy.context.object
    camera.name = "PREVIEW_Camera"
    camera.data.type = "ORTHO"
    bpy.context.scene.camera = camera
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.eevee.taa_render_samples = 96
    scene.render.resolution_x = 1200
    scene.render.resolution_y = 700
    scene.render.image_settings.file_format = "PNG"
    scene.world.color = (0.016, 0.018, 0.022)
    scene.view_settings.look = "AgX - Medium High Contrast"
    return camera, center, size, extent


def render_qa_views(repo_root: Path, hero_objects: list[bpy.types.Object]) -> list[Path]:
    output = repo_root / OUTPUT_RELATIVE
    camera, center, size, extent = add_preview_scene(hero_objects)
    scene = bpy.context.scene
    views = {
        "hero": center + Vector((-extent * 0.55, -extent * 2.8, extent * 0.62)),
        "side": center + Vector((0.0, -extent * 3.0, extent * 0.08)),
        "muzzle": center + Vector((extent * 3.0, -extent * 0.08, extent * 0.05)),
    }
    paths = []
    for name, location in views.items():
        camera.location = location
        camera.rotation_euler = (center - location).to_track_quat("-Z", "Y").to_euler()
        camera.data.ortho_scale = max(size.x * 1.12, size.z * 2.0) if name != "muzzle" else max(size.y, size.z) * 2.3
        path = output / f"{ASSET_ID}_preview_{name}.png"
        scene.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        paths.append(path)
    return paths


def export_final_asset(repo_root: Path, hero_objects, lod1_objects, collision_obj, reduction, texture_path: Path, previews: list[Path]):
    output = repo_root / OUTPUT_RELATIVE
    blend_path = output / f"{ASSET_ID}.blend"
    glb_path = output / f"{ASSET_ID}.glb"
    manifest_path = output / "manifest.json"
    all_objects = hero_objects + lod1_objects + [collision_obj]
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))
    bpy.ops.object.select_all(action="DESELECT")
    for obj in all_objects:
        obj.select_set(True)
    bpy.ops.export_scene.gltf(
        filepath=str(glb_path),
        export_format="GLB",
        use_selection=True,
        export_apply=True,
        export_yup=True,
    )
    minimum, maximum, _ = mesh_bounds(hero_objects)
    manifest = {
        "schema_version": 1,
        "asset_id": ASSET_ID,
        "status": "prototype_validated_not_sellable",
        "license_status": "pending_source_page_evidence",
        "design": "fictionalized PS1-era over-under trench shotgun, game-ready budget",
        "lod0_triangles": total_triangles(hero_objects),
        "lod1_triangles": total_triangles(lod1_objects),
        "target_triangles": TARGET_TRIANGLES,
        "lod1_target_triangles": LOD1_TARGET_TRIANGLES,
        "source_triangles_before": reduction["before"],
        "source_triangles_after": reduction["after"],
        "texture_size": TEXTURE_SIZE,
        "materials": sorted({material.name for obj in all_objects for material in obj.data.materials if material}),
        "dimensions": [round(value, 4) for value in (maximum - minimum)],
        "collision_proxy": collision_obj.name,
        "files": {
            "blend": blend_path.name,
            "glb": glb_path.name,
            "texture": texture_path.name,
            "previews": [path.name for path in previews],
        },
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print("PS1_FINAL_RESULT=" + json.dumps(manifest))
    return manifest


def build_ps1_shotgun(repo_root: Path):
    reset_scene()
    structural = import_structural_source(repo_root)
    materials = create_materials()
    additions = make_full_stock(materials, structural)
    hero_objects = structural + additions
    reduction = reduce_ps1_source(structural, TARGET_TRIANGLES - total_triangles(additions))
    texture_path = apply_ps1_texture(repo_root, structural)
    for obj in additions:
        for polygon in obj.data.polygons:
            polygon.use_smooth = False
    triangulate(hero_objects)
    lod1_objects = make_lod1(hero_objects, {obj.name for obj in structural})
    for obj in lod1_objects:
        obj.hide_set(True)
        obj.hide_render = True
    collision_obj = make_collision_proxy(hero_objects)
    collision_obj.hide_render = True
    bpy.context.collection.objects.unlink(collision_obj)
    previews = render_qa_views(repo_root, hero_objects)
    bpy.context.collection.objects.link(collision_obj)
    manifest = export_final_asset(repo_root, hero_objects, lod1_objects, collision_obj, reduction, texture_path, previews)
    if manifest["lod0_triangles"] > TARGET_TRIANGLES:
        raise RuntimeError(f"LOD0 triangle budget exceeded: {manifest['lod0_triangles']} > {TARGET_TRIANGLES}")
    if manifest["lod1_triangles"] > LOD1_TARGET_TRIANGLES:
        raise RuntimeError(f"LOD1 triangle budget exceeded: {manifest['lod1_triangles']} > {LOD1_TARGET_TRIANGLES}")


def main():
    args = sys.argv[sys.argv.index("--") + 1 :]
    if len(args) != 1:
        raise SystemExit("usage: blender --background --python generate_ps1_over_under_shotgun_v1.py -- REPO_ROOT")
    build_ps1_shotgun(Path(args[0]).resolve())


if __name__ == "__main__":
    main()
