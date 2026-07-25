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


def _ensure_fbx_importer() -> None:
    # Mirrors factory/scripts/retro_pass.py's _ensure_fbx_importer. Under
    # --factory-startup, io_scene_fbx can be disabled, in which case
    # bpy.ops.import_scene.fbx does not exist at all and raises
    # AttributeError rather than a clean, reportable error. retro_pass.py
    # already pays for this guard; silhouette_render.py needs the same one
    # so a host that converts fine can also measure the raw side -- without
    # it, Gate 2 would fail to render the raw mesh on exactly the hosts
    # where the rest of the pipeline works.
    if hasattr(bpy.ops.import_scene, "fbx"):
        return
    import addon_utils

    addon_utils.enable("io_scene_fbx", default_set=True, persistent=False)


def _import(source: Path) -> list:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    suffix = source.suffix.lower()
    if suffix == ".fbx":
        _ensure_fbx_importer()
        bpy.ops.import_scene.fbx(filepath=str(source))
    elif suffix in (".glb", ".gltf"):
        bpy.ops.import_scene.gltf(filepath=str(source))
    elif suffix == ".obj":
        bpy.ops.wm.obj_import(filepath=str(source))
    else:
        raise ValueError(f"unsupported source format {suffix!r}")
    return [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]


def _flat_white(meshes: list) -> None:
    # Defense in depth, NOT the load-bearing mechanism -- see main() for
    # why. An emission node tree is invisible to BLENDER_WORKBENCH (it
    # only exists for EEVEE/Cycles), and Workbench's MATERIAL color mode
    # reads Material.diffuse_color, not the node graph. diffuse_color is
    # pinned explicitly here so this material is still correct white if
    # something ever switches scene.display.shading.color_type back to
    # "MATERIAL".
    material = bpy.data.materials.new("SilhouetteWhite")
    material.diffuse_color = (1.0, 1.0, 1.0, 1.0)
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


# Matches factory.silhouette.LUMA_THRESHOLD (32 of 255) so a view judged
# non-degenerate here agrees with what mask_from_png will later decide from
# the same PNG bytes.
_LUMA_THRESHOLD = 32 / 255.0


def _coverage_fraction(path: Path) -> float:
    """Fraction of pixels in the just-written PNG that read as "lit".

    Computed from Blender's own decode of the file it just wrote (via
    bpy.data.images.load), independently of any host-side PNG decoder, so
    this is a check on what the render actually produced -- not a
    duplicate of the host-side mask_from_png algorithm, a second witness
    to the same file.
    """
    image = bpy.data.images.load(str(path))
    try:
        pixels = image.pixels[:]
        total = len(pixels) // 4
        lit = 0
        for offset in range(0, len(pixels), 4):
            luma = (
                pixels[offset] * 0.299
                + pixels[offset + 1] * 0.587
                + pixels[offset + 2] * 0.114
            )
            if luma >= _LUMA_THRESHOLD:
                lit += 1
        return lit / total if total else 0.0
    finally:
        bpy.data.images.remove(image)


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
    report = {
        "ok": False,
        "renders": [],
        "coverage": [],
        "radius": None,
        "centre": None,
        "error": None,
    }
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
        # color_type = "MATERIAL" reads Material.diffuse_color, which is
        # fine now that _flat_white pins it -- but "SINGLE" is pinned here
        # instead so the mask does not depend on per-object material state
        # surviving at all: every mesh renders pure white regardless of
        # what material (if any) ended up assigned to it. This is the
        # actual load-bearing mechanism for "flat white"; _flat_white's
        # material is a defensive fallback, not the primary one.
        scene.display.shading.color_type = "SINGLE"
        scene.display.shading.single_color = (1.0, 1.0, 1.0)
        # Workbench only reads scene.world's colour when background_type is
        # "WORLD" -- the default is "THEME", which paints the background
        # with the current UI theme's viewport colour instead, ignoring
        # scene.world.color entirely. Without this line, "flat white on
        # black" silently becomes "flat (fallback grey) on (theme grey)",
        # and whether that still crosses LUMA_THRESHOLD is an accident of
        # whichever theme --factory-startup happens to load.
        scene.display.shading.background_type = "WORLD"
        scene.render.film_transparent = False
        if scene.world is None:
            # --factory-startup with an empty scene (see _import) has no
            # World data-block at all, not merely a default one, so setting
            # .color on it unconditionally raises AttributeError on a bare
            # `--factory-startup` run.
            scene.world = bpy.data.worlds.new("SilhouetteWorld")
        scene.world.color = (0.0, 0.0, 0.0)
        # Pin the view transform. Blender's default view transform (Filmic
        # or AgX, depending on version) applies a tone-mapping curve before
        # writing pixels, which can lift pure black or compress pure white
        # well away from 0/255 -- exactly the kind of unpinned default that
        # would silently change what LUMA_THRESHOLD sees. "Standard" writes
        # values through unmodified.
        scene.view_settings.view_transform = "Standard"
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
            report["coverage"].append(_coverage_fraction(target))
        report["ok"] = True
    except Exception as error:
        report["error"] = f"{type(error).__name__}: {error}"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
