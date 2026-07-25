"""Build a fictionalized PS1-style full-stock over-under trench shotgun.

Structural mechanics come from the user-provided compact over-under FBX.
The full-stock profile and restrained wartime wood/steel language are influenced
by the user-provided M1897 reference, without copying pump-action mechanisms,
logos, markings, or decorative engraving.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector

ASSET_ID = "ps1_reference_derived_trench_shotgun_01"
OUTPUT_RELATIVE = "products/ww2_lowpoly_frontline_pack/source-derived-shotgun-v1"
TARGET_TRIANGLES = 2400
TEXTURE_SIZE = 256
STRUCTURAL_SOURCE = "projects/ww2_lowpoly_frontline_pack/benchmark-shotgun-v1/references/source-mesh/shotgun-fbx/source/shotgun.fbx"
STRUCTURAL_TEXTURE = "projects/ww2_lowpoly_frontline_pack/benchmark-shotgun-v1/references/source-mesh/shotgun-fbx/textures/shotgun_lambert2_BaseColor.jpg"
INFLUENCE_SOURCE = "projects/ww2_lowpoly_frontline_pack/benchmark-shotgun-v1/references/source-mesh/m1897-trenchgun/source/trenchgun.fbx"


def reset_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for collection in (bpy.data.meshes, bpy.data.curves, bpy.data.materials, bpy.data.cameras, bpy.data.lights):
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


def make_flat_material(name: str, color, metallic: float = 0.0, roughness: float = 0.75):
    material = bpy.data.materials.new(name)
    material.diffuse_color = (*color, 1.0)
    material.use_nodes = True
    bsdf = material.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Roughness"].default_value = roughness
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


def make_box(name: str, location, dimensions, material, bevel: float = 0.0):
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=location)
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = dimensions
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    obj.data.materials.append(material)
    if bevel:
        modifier = obj.modifiers.new("PS1_Chamfer", "BEVEL")
        modifier.width = bevel
        modifier.segments = 1
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.modifier_apply(modifier=modifier.name)
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


def reduce_source_parts(objects: list[bpy.types.Object]) -> dict[str, int]:
    before = total_triangles(objects)
    for obj in objects:
        triangles = object_triangles(obj)
        if triangles >= 800:
            ratio = 0.20
        elif triangles >= 300:
            ratio = 0.35
        else:
            continue
        modifier = obj.modifiers.new("PS1_Selective_Decimate", "DECIMATE")
        modifier.decimate_type = "COLLAPSE"
        modifier.ratio = ratio
        modifier.use_collapse_triangulate = True
        bpy.ops.object.select_all(action="DESELECT")
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.modifier_apply(modifier=modifier.name)
        for polygon in obj.data.polygons:
            polygon.use_smooth = False
    return {"before": before, "after": total_triangles(objects)}


def make_full_stock(materials: dict[str, bpy.types.Material]) -> list[bpy.types.Object]:
    # M1897-influenced continuous shoulder stock: broad butt, restrained comb,
    # narrow wrist, and a slight underside swell, attached behind the real receiver.
    profile = [
        (-0.425, 0.070),
        (-0.355, 0.085),
        (-0.255, 0.078),
        (-0.175, 0.062),
        (-0.100, 0.052),
        (-0.100, -0.050),
        (-0.235, -0.050),
        (-0.355, -0.048),
        (-0.425, -0.026),
    ]
    stock = extruded_profile("Full_Walnut_Shoulder_Stock", profile, 0.094, materials["walnut"])
    cheek = extruded_profile(
        "Stock_Cheek_Facet",
        [(-0.360, 0.055), (-0.255, 0.054), (-0.175, 0.041), (-0.205, -0.004), (-0.345, 0.006)],
        0.006,
        materials["walnut_light"],
        y_offset=-0.050,
    )
    buttplate = make_box("Steel_Buttplate", (-0.432, 0.0, 0.020), (0.014, 0.102, 0.126), materials["steel_dark"], bevel=0.004)
    sling = make_box("Rear_Sling_Loop", (-0.315, 0.0, -0.052), (0.030, 0.016, 0.009), materials["steel"])
    return [stock, cheek, buttplate, sling]


def apply_ps1_materials(repo_root: Path, structural: list[bpy.types.Object], additions: list[bpy.types.Object]):
    output = repo_root / OUTPUT_RELATIVE
    output.mkdir(parents=True, exist_ok=True)
    source_image = bpy.data.images.load(str(repo_root / STRUCTURAL_TEXTURE), check_existing=True)
    source_image.scale(TEXTURE_SIZE, TEXTURE_SIZE)
    atlas_path = output / f"{ASSET_ID}_source_atlas_{TEXTURE_SIZE}.png"
    source_image.file_format = "PNG"
    source_image.save_render(str(atlas_path))

    material = bpy.data.materials.new("PS1_Source_Atlas")
    material.use_nodes = True
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    bsdf = nodes.get("Principled BSDF")
    texture = nodes.new("ShaderNodeTexImage")
    texture.name = "PS1_Nearest_Atlas"
    texture.image = source_image
    texture.interpolation = "Closest"
    tint = nodes.new("ShaderNodeMixRGB")
    tint.blend_type = "MULTIPLY"
    tint.inputs[0].default_value = 1.0
    tint.inputs[2].default_value = (0.20, 0.24, 0.28, 1.0)
    links.new(texture.outputs["Color"], tint.inputs[1])
    links.new(tint.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.76
    bsdf.inputs["Metallic"].default_value = 0.08
    for obj in structural:
        obj.data.materials.clear()
        obj.data.materials.append(material)
        for polygon in obj.data.polygons:
            polygon.use_smooth = False
    for obj in additions:
        for polygon in obj.data.polygons:
            polygon.use_smooth = False
    return atlas_path


def create_materials():
    return {
        "walnut": make_flat_material("PS1_Walnut", (0.025, 0.004, 0.001), roughness=0.82),
        "walnut_light": make_flat_material("PS1_Walnut_Highlight", (0.060, 0.012, 0.002), roughness=0.78),
        "steel": make_flat_material("PS1_Worn_Steel", (0.070, 0.085, 0.095), metallic=0.55, roughness=0.62),
        "steel_dark": make_flat_material("PS1_Parkerized_Steel", (0.012, 0.018, 0.023), metallic=0.48, roughness=0.70),
    }


def triangulate(objects: list[bpy.types.Object]):
    for obj in objects:
        bpy.ops.object.select_all(action="DESELECT")
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        modifier = obj.modifiers.new("Runtime_Triangulate", "TRIANGULATE")
        bpy.ops.object.modifier_apply(modifier=modifier.name)


def add_preview_scene(objects: list[bpy.types.Object]):
    minimum, maximum, center = mesh_bounds(objects)
    size = maximum - minimum
    extent = max(size)
    ground_material = make_flat_material("PREVIEW_Ground_Material", (0.025, 0.028, 0.032), roughness=0.95)
    bpy.ops.mesh.primitive_plane_add(size=4, location=(center.x, center.y, minimum.z - 0.035))
    ground = bpy.context.object
    ground.name = "PREVIEW_Ground"
    ground.data.materials.append(ground_material)
    for name, location, energy, size_value, color in (
        ("PREVIEW_Key", center + Vector((-1.2, -1.6, 1.4)), 900, 2.5, (1.0, 0.77, 0.58)),
        ("PREVIEW_Fill", center + Vector((1.4, -1.1, 0.8)), 500, 2.0, (0.55, 0.70, 1.0)),
        ("PREVIEW_Rim", center + Vector((0.5, 1.2, 1.1)), 650, 1.8, (0.65, 0.80, 1.0)),
    ):
        bpy.ops.object.light_add(type="AREA", location=location)
        light = bpy.context.object
        light.name = name
        light.data.energy = energy
        light.data.size = size_value
        light.data.color = color
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
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.world.color = (0.016, 0.018, 0.022)
    scene.view_settings.look = "AgX - Medium High Contrast"
    return camera, center, size, extent


def render_qa_views(repo_root: Path, objects: list[bpy.types.Object]) -> list[Path]:
    output = repo_root / OUTPUT_RELATIVE
    camera, center, size, extent = add_preview_scene(objects)
    scene = bpy.context.scene
    views = {
        "hero": center + Vector((-extent * 0.55, -extent * 2.8, extent * 0.62)),
        "side": center + Vector((0.0, -extent * 3.0, extent * 0.08)),
        "muzzle": center + Vector((extent * 3.0, -extent * 0.08, extent * 0.05)),
        "top": center + Vector((0.0, -extent * 0.10, extent * 3.0)),
    }
    paths = []
    for name, location in views.items():
        camera.location = location
        camera.rotation_euler = (center - location).to_track_quat("-Z", "Y").to_euler()
        camera.data.ortho_scale = max(size.x * 1.12, size.z * 2.0) if name not in {"muzzle", "top"} else max(size.y, size.z) * 2.3 if name == "muzzle" else max(size.x * 1.12, size.y * 3.0)
        path = output / f"{ASSET_ID}_preview_{name}.png"
        scene.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        paths.append(path)
    return paths


def export_asset(repo_root: Path, objects: list[bpy.types.Object], reduction: dict[str, int], atlas_path: Path, previews: list[Path]):
    output = repo_root / OUTPUT_RELATIVE
    blend_path = output / f"{ASSET_ID}.blend"
    glb_path = output / f"{ASSET_ID}.glb"
    manifest_path = output / "manifest.json"
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))
    bpy.ops.object.select_all(action="DESELECT")
    for obj in objects:
        obj.select_set(True)
    bpy.ops.export_scene.gltf(
        filepath=str(glb_path),
        export_format="GLB",
        use_selection=True,
        export_apply=True,
        export_yup=True,
    )
    minimum, maximum, _ = mesh_bounds(objects)
    manifest = {
        "schema_version": 1,
        "asset_id": ASSET_ID,
        "status": "prototype_validated_not_sellable",
        "license_status": "pending_source_page_evidence",
        "design": "fictionalized full-stock over-under trench shotgun",
        "structural_source": {
            "archive_sha256": "fda5628431fa3a1993b4072d24bee9f85280f2f1c3fe3ab81f7de740330eb285",
            "role": "over-under receiver, twin barrels, muzzle bores, trigger and guard construction",
        },
        "influence_source": {
            "path": INFLUENCE_SOURCE,
            "archive_sha256": "57d22c8ba7085b1b20367ebf94dd14be854072df0dd26bea1549ace81f946d6f",
            "role": "full-stock proportion and restrained wartime wood/steel language only",
        },
        "forbidden_copying": ["manufacturer marks", "exact M1897 receiver", "pump-action mechanism", "decorative engraving"],
        "triangles": total_triangles(objects),
        "target_triangles": TARGET_TRIANGLES,
        "source_triangles_before": reduction["before"],
        "source_triangles_after": reduction["after"],
        "materials": sorted({material.name for obj in objects for material in obj.data.materials if material}),
        "dimensions": [round(value, 4) for value in (maximum - minimum)],
        "texture_size": TEXTURE_SIZE,
        "files": {
            "blend": blend_path.name,
            "glb": glb_path.name,
            "atlas": atlas_path.name,
            "previews": [path.name for path in previews],
        },
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print("REFERENCE_DERIVED_RESULT=" + json.dumps(manifest))
    return manifest


def build_reference_derived_prototype(repo_root: Path):
    reset_scene()
    structural = import_structural_source(repo_root)
    reduction = reduce_source_parts(structural)
    materials = create_materials()
    additions = make_full_stock(materials)
    objects = structural + additions
    atlas = apply_ps1_materials(repo_root, structural, additions)
    triangulate(objects)
    previews = render_qa_views(repo_root, objects)
    manifest = export_asset(repo_root, objects, reduction, atlas, previews)
    if manifest["triangles"] > TARGET_TRIANGLES:
        raise RuntimeError(f"triangle budget exceeded: {manifest['triangles']} > {TARGET_TRIANGLES}")


def main():
    args = sys.argv[sys.argv.index("--") + 1 :]
    if len(args) != 1:
        raise SystemExit("usage: blender --background --python generate_reference_derived_shotgun_v1.py -- REPO_ROOT")
    build_reference_derived_prototype(Path(args[0]).resolve())


if __name__ == "__main__":
    main()
