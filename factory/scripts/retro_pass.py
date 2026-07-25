"""PS1 conversion pass. Runs inside Blender.

Implements stages 1-4 of retro_pass: part-aware split, cleanup, normalize,
decimate to band. Texturing is implemented separately (Task 7).

Invoked as:
    blender --background --factory-startup --python retro_pass.py -- \
        --payload payload.json --report report.json
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import bmesh
import bpy
from mathutils import Vector

FLOATER_FRACTION = 0.001
MAX_DECIMATE_PASSES = 8
DECIMATE_SAFETY_MARGIN = 0.9


def _arguments() -> tuple[Path, Path]:
    argv = sys.argv[sys.argv.index("--") + 1 :]
    payload = Path(argv[argv.index("--payload") + 1])
    report = Path(argv[argv.index("--report") + 1])
    return payload, report


def _clear_scene() -> None:
    bpy.ops.wm.read_factory_settings(use_empty=True)


def _ensure_fbx_importer() -> None:
    if hasattr(bpy.ops.import_scene, "fbx"):
        return
    import addon_utils

    addon_utils.enable("io_scene_fbx", default_set=True, persistent=False)


def _import_source(source: Path) -> list:
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


def _split_by_material(meshes: list) -> list:
    # The trenchgun fixture (and PS1-era rigs generally) stores semantic
    # parts as material slots on a single skinned mesh parented to an
    # armature, not as separate top-level mesh objects. "Part-aware split"
    # means: for every material slot on every imported mesh, carve out the
    # faces using that slot into their own standalone (unparented) mesh
    # object named after the material, baking each object's current world
    # matrix so it lands in the same place the skinned mesh occupied.
    # Objects with a single material slot still go through this path so
    # every downstream stage only ever deals with flat, unparented objects.
    parts: list = []
    for obj in meshes:
        world_matrix = obj.matrix_world.copy()
        mesh = obj.data
        slot_count = max(len(obj.material_slots), 1)
        for index in range(slot_count):
            material = obj.material_slots[index].material if obj.material_slots else None
            name = material.name if material else obj.name

            bm = bmesh.new()
            bm.from_mesh(mesh)
            bm.faces.ensure_lookup_table()
            if slot_count > 1:
                drop = [face for face in bm.faces if face.material_index != index]
                if drop:
                    bmesh.ops.delete(bm, geom=drop, context="FACES")
                loose_verts = [vertex for vertex in bm.verts if not vertex.link_faces]
                if loose_verts:
                    bmesh.ops.delete(bm, geom=loose_verts, context="VERTS")
            if len(bm.faces) == 0:
                bm.free()
                continue
            for face in bm.faces:
                face.material_index = 0

            new_mesh = bpy.data.meshes.new(f"{mesh.name}_{name}")
            bm.to_mesh(new_mesh)
            bm.free()

            new_obj = bpy.data.objects.new(name, new_mesh)
            new_obj.matrix_world = world_matrix
            if material:
                new_obj.data.materials.append(material)
            bpy.context.scene.collection.objects.link(new_obj)
            parts.append(new_obj)

    # Drop the pre-split source objects and anything else left over
    # (armatures, empties) so the scene contains exactly the flat parts.
    for obj in list(bpy.context.scene.objects):
        if obj not in parts:
            bpy.data.objects.remove(obj, do_unlink=True)
    return parts


def _triangle_count(meshes: list) -> int:
    total = 0
    for obj in meshes:
        obj.data.calc_loop_triangles()
        total += len(obj.data.loop_triangles)
    return total


def _world_bounds(meshes: list):
    points = [
        obj.matrix_world @ Vector(corner)
        for obj in meshes
        for corner in obj.bound_box
    ]
    xs = [point.x for point in points]
    ys = [point.y for point in points]
    zs = [point.z for point in points]
    return (min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs))


def _remove_floaters(meshes: list) -> list:
    _minimum, _maximum = _world_bounds(meshes)
    diagonal = math.dist(_minimum, _maximum)
    threshold = (diagonal * FLOATER_FRACTION) ** 3
    kept = []
    for obj in meshes:
        dimensions = obj.dimensions
        volume = max(dimensions[0], 1e-9) * max(dimensions[1], 1e-9) * max(dimensions[2], 1e-9)
        if volume < threshold:
            bpy.data.objects.remove(obj, do_unlink=True)
        else:
            kept.append(obj)
    return kept


def _repair(meshes: list) -> None:
    # Uses bmesh directly instead of bpy.ops.object.mode_set(mode="EDIT"):
    # the operator-based EDIT-mode toggle is unreliable in --background mode
    # (it depends on window/screen context that does not exist headlessly).
    # bmesh needs no operator context at all.
    for obj in meshes:
        mesh = obj.data
        bm = bmesh.new()
        bm.from_mesh(mesh)

        loose_verts = [vertex for vertex in bm.verts if not vertex.link_faces]
        if loose_verts:
            bmesh.ops.delete(bm, geom=loose_verts, context="VERTS")

        loose_edges = [edge for edge in bm.edges if not edge.link_faces]
        if loose_edges:
            bmesh.ops.delete(bm, geom=loose_edges, context="EDGES")

        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)

        bm.to_mesh(mesh)
        bm.free()
        mesh.update()


def _normalize(meshes: list, grid_unit: float, up_axis: str) -> dict:
    if up_axis == "Y":
        for obj in meshes:
            if obj.parent is None:
                obj.rotation_euler.rotate_axis("X", -math.pi / 2)
    bpy.context.view_layer.update()

    # Blender's own coordinate frame is always Z-up. When the contract wants
    # a Y-up asset we rotate the geometry -90deg about X (above), which
    # moves the "up" extent of the mesh from world Z onto world Y. So the
    # axis that is actually "up" in the world-space bounds we measure below
    # tracks contract up_axis, not the raw Blender convention.
    up_index = 1 if up_axis == "Y" else 2
    horizontal_indices = tuple(index for index in range(3) if index != up_index)

    minimum, maximum = _world_bounds(meshes)

    def snap(value: float) -> float:
        return round(value / grid_unit) * grid_unit

    centres = {index: (minimum[index] + maximum[index]) / 2 for index in horizontal_indices}
    offset = [0.0, 0.0, 0.0]
    for index in horizontal_indices:
        offset[index] = snap(centres[index]) - centres[index]
    offset[up_index] = -minimum[up_index]

    for obj in meshes:
        if obj.parent is None:
            obj.location[0] += offset[0]
            obj.location[1] += offset[1]
            obj.location[2] += offset[2]
    bpy.context.view_layer.update()
    minimum, maximum = _world_bounds(meshes)

    axis_names = ("x", "y", "z")
    origin = {}
    for index, name in enumerate(axis_names):
        if index == up_index:
            origin[name] = snap(minimum[index])
        else:
            origin[name] = snap((minimum[index] + maximum[index]) / 2)

    return {
        "min": {"x": minimum[0], "y": minimum[1], "z": minimum[2]},
        "max": {"x": maximum[0], "y": maximum[1], "z": maximum[2]},
        "origin": origin,
    }


def _decimate(meshes: list, budget: int) -> tuple[int, int]:
    current = _triangle_count(meshes)
    attempts = 0
    # A single collapse pass at ratio=budget/current typically overshoots the
    # budget slightly (each part rounds independently), so we repeat until
    # the combined triangle count is at or under budget, bounded by
    # MAX_DECIMATE_PASSES so a pathological mesh cannot loop forever.
    #
    # Requesting ratio == budget/current exactly makes this converge on the
    # budget asymptotically (each pass gets a little closer but a collapse
    # modifier's reduction is not perfectly continuous, especially on small
    # per-part meshes near their topological floor) without ever actually
    # landing at or under it. DECIMATE_SAFETY_MARGIN asks for a bit more
    # reduction than the arithmetic minimum each pass so the loop crosses
    # the budget in a handful of passes instead of trailing off forever.
    #
    # MAX_DECIMATE_PASSES bounds the loop but does NOT guarantee the budget
    # is met: a mesh can hit a topological floor (an object's collapse
    # modifier cannot reduce it further without breaking manifoldness)
    # before crossing under budget. Convergence is not attempted here at
    # any cost — the caller (main()) is responsible for checking the
    # returned triangle count against budget and failing loudly rather
    # than silently exporting an over-budget asset. See main() and the
    # task-6 fix-round report for why this split of responsibility was
    # chosen over looping until convergence or raising the pass cap.
    while current > budget and attempts < MAX_DECIMATE_PASSES:
        ratio = max(min((budget / current) * DECIMATE_SAFETY_MARGIN, 1.0), 0.01)
        for obj in meshes:
            if len(obj.data.polygons) == 0:
                continue
            bpy.context.view_layer.objects.active = obj
            modifier = obj.modifiers.new("RetroDecimate", "DECIMATE")
            modifier.decimate_type = "COLLAPSE"
            modifier.ratio = ratio
            modifier.use_collapse_triangulate = True
            bpy.ops.object.modifier_apply(modifier="RetroDecimate")
        current = _triangle_count(meshes)
        attempts += 1
    return current, attempts


def main() -> int:
    payload_path, report_path = _arguments()
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    report = {
        "ok": False,
        "stages": {},
        "triangles_in": 0,
        "triangles_out": 0,
        "parts": [],
        "bounds": {},
        "error": None,
    }
    try:
        contract = payload["contract"]
        role = payload["role"]
        bands = contract["polycount_bands"]
        if role not in bands:
            raise ValueError(
                f"unknown role {role!r}; contract declares {sorted(bands)}"
            )
        budget = bands[role]

        _clear_scene()
        imported = _import_source(Path(payload["source"]))
        if not imported:
            raise ValueError("source contains no mesh objects")
        report["triangles_in"] = _triangle_count(imported)

        meshes = _split_by_material(imported)
        if not meshes:
            raise ValueError("source contains no mesh geometry after material split")
        report["parts"] = sorted(obj.name for obj in meshes)
        report["stages"]["split"] = len(meshes)

        meshes = _remove_floaters(meshes)
        _repair(meshes)
        report["stages"]["cleanup"] = len(meshes)

        report["bounds"] = _normalize(meshes, contract["grid_unit"], contract["up_axis"])
        report["stages"]["normalize"] = True

        triangles_out, decimate_passes = _decimate(meshes, budget)
        report["triangles_out"] = triangles_out
        report["stages"]["decimate"] = budget

        if triangles_out > budget:
            # Non-convergence must never be silent: Gate 1 (Task 10) rejects
            # any asset over its triangle budget, and this is the only
            # point in the pipeline where we know *why* an over-budget
            # asset would be rejected. Failing here (ok: false, no export)
            # rather than exporting anyway surfaces that reason immediately
            # instead of as an unexplained downstream gate failure.
            raise ValueError(
                f"decimate did not converge for role {role!r}: "
                f"budget={budget} triangles_out={triangles_out} "
                f"after {decimate_passes} passes "
                f"(MAX_DECIMATE_PASSES={MAX_DECIMATE_PASSES})"
            )

        bpy.ops.object.select_all(action="SELECT")
        bpy.ops.export_scene.gltf(
            filepath=payload["output"],
            export_format="GLB",
            use_selection=True,
            export_apply=True,
            export_yup=(contract["up_axis"] == "Y"),
        )
        report["ok"] = True
    except Exception as error:  # reported, never swallowed
        report["error"] = f"{type(error).__name__}: {error}"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
