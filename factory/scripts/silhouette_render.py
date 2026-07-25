"""Render fixed-view silhouettes. Runs inside Blender.

Invoked as:
    blender --background --factory-startup --python silhouette_render.py -- \
        --payload payload.json --report report.json
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector


def _arguments() -> tuple[Path, Path]:
    argv = sys.argv[sys.argv.index("--") + 1 :]
    return (
        Path(argv[argv.index("--payload") + 1]),
        Path(argv[argv.index("--report") + 1]),
    )


def _import(source: Path) -> list:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    suffix = source.suffix.lower()
    if suffix == ".fbx":
        bpy.ops.import_scene.fbx(filepath=str(source))
    elif suffix in (".glb", ".gltf"):
        bpy.ops.import_scene.gltf(filepath=str(source))
    elif suffix == ".obj":
        bpy.ops.wm.obj_import(filepath=str(source))
    else:
        raise ValueError(f"unsupported source format {suffix!r}")
    return [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]


def _flat_white(meshes: list) -> None:
    material = bpy.data.materials.new("SilhouetteWhite")
    material.use_nodes = True
    tree = material.node_tree
    tree.nodes.clear()
    emission = tree.nodes.new("ShaderNodeEmission")
    emission.inputs["Color"].default_value = (1.0, 1.0, 1.0, 1.0)
    emission.inputs["Strength"].default_value = 1.0
    output = tree.nodes.new("ShaderNodeOutputMaterial")
    tree.links.new(emission.outputs["Emission"], output.inputs["Surface"])
    for obj in meshes:
        obj.data.materials.clear()
        obj.data.materials.append(material)


def _bounds(meshes: list) -> tuple[tuple[float, float, float], float]:
    points = [
        obj.matrix_world @ Vector(corner)
        for obj in meshes
        for corner in obj.bound_box
    ]
    xs = [p.x for p in points]
    ys = [p.y for p in points]
    zs = [p.z for p in points]
    centre = ((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2, (min(zs) + max(zs)) / 2)
    radius = max(max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs)) / 2
    return centre, max(radius, 1e-6)


def main() -> int:
    payload_path, report_path = _arguments()
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    report = {"ok": False, "renders": [], "radius": None, "centre": None, "error": None}
    try:
        meshes = _import(Path(payload["source"]))
        if not meshes:
            raise ValueError("source contains no mesh objects")
        _flat_white(meshes)
        centre, own_radius = _bounds(meshes)
        # The framing centre always tracks THIS mesh's own bounds -- the
        # conversion pipeline's normalize stage recentres and reorients
        # meshes onto a grid-snapped origin, so a raw source and its
        # converted output are not expected to share a world-space
        # position. The radius (camera distance / zoom) is the one framing
        # quantity that a caller can pin to a shared value across two
        # render_masks() calls, via payload["radius_override"], so neither
        # render is penalized by a framing mismatch. See factory/silhouette.py
        # and task-9-report.md for the full reasoning.
        override = payload.get("radius_override")
        radius = float(override) if override is not None else own_radius
        report["radius"] = own_radius
        report["centre"] = list(centre)

        scene = bpy.context.scene
        scene.render.engine = "BLENDER_WORKBENCH"
        scene.display.shading.light = "FLAT"
        scene.display.shading.color_type = "MATERIAL"
        scene.render.film_transparent = False
        if scene.world is None:
            # --factory-startup with an empty scene (see _import) has no
            # World data-block at all, not merely a default one, so setting
            # .color on it unconditionally raises AttributeError on a bare
            # `--factory-startup` run.
            scene.world = bpy.data.worlds.new("SilhouetteWorld")
        scene.world.color = (0.0, 0.0, 0.0)
        scene.render.resolution_x = payload["resolution"]
        scene.render.resolution_y = payload["resolution"]
        scene.render.image_settings.file_format = "PNG"
        scene.render.image_settings.color_mode = "RGBA"

        camera_data = bpy.data.cameras.new("SilhouetteCamera")
        camera_data.type = "ORTHO"
        camera_data.ortho_scale = radius * 2.4
        camera = bpy.data.objects.new("SilhouetteCamera", camera_data)
        scene.collection.objects.link(camera)
        scene.camera = camera

        output_dir = Path(payload["output_dir"])
        output_dir.mkdir(parents=True, exist_ok=True)
        centre_vector = Vector(centre)
        for index, (azimuth, elevation) in enumerate(payload["views"]):
            theta = math.radians(azimuth)
            phi = math.radians(elevation)
            distance = radius * 4.0
            camera.location = centre_vector + Vector((
                distance * math.cos(phi) * math.sin(theta),
                -distance * math.cos(phi) * math.cos(theta),
                distance * math.sin(phi),
            ))
            # Point the camera at the framing centre with a look-at
            # quaternion instead of deriving rotation_euler by hand from
            # azimuth/elevation. Hand-rolled Euler math from spherical
            # angles is easy to get subtly wrong (axis order, sign of a
            # cross term) and a wrong camera silently renders an empty or
            # solid frame rather than raising -- exactly the failure mode
            # this measurement most needs to avoid. to_track_quat is the
            # library-provided, battle-tested way to point an object's
            # local -Z (Blender camera forward) at a target with local Y
            # as up, and it is correct for every azimuth/elevation pair by
            # construction.
            direction = centre_vector - camera.location
            camera.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
            target = output_dir / f"view_{index:02d}.png"
            scene.render.filepath = str(target)
            bpy.ops.render.render(write_still=True)
            report["renders"].append(str(target))
        report["ok"] = True
    except Exception as error:
        report["error"] = f"{type(error).__name__}: {error}"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
