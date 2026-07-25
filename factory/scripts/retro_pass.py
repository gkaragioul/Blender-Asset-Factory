"""PS1 conversion pass. Runs inside Blender.

Implements stages 1-8 of retro_pass: part-aware split, cleanup, normalize,
decimate to band, shared UV atlas, bake, palette quantization, map strip,
export.

Invoked as:
    blender --background --factory-startup --python retro_pass.py -- \
        --payload payload.json --report report.json
"""
from __future__ import annotations

import json
import math
import shutil
import sys
import tempfile
from pathlib import Path

import bmesh
import bpy
from mathutils import Vector

# The repository root, so this script can import the host-side factory
# package. factory/png.py and factory/palette.py are standard-library only,
# so Blender's bundled Python imports them unmodified. Reusing them is not
# a convenience: Gate 1 (Task 10) checks palette conformance of the exported
# PNG with factory.palette/factory.png, and the quantizer here decides what
# those bytes are. Two independent decoders or two independent
# nearest-colour searches can silently disagree on a tie or an edge case and
# turn every asset in a pack into a gate failure. There is exactly one
# implementation of each, shared across the process boundary.
_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(_REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPOSITORY_ROOT))

from factory.palette import load_palette  # noqa: E402
from factory.png import encode_rgba  # noqa: E402

FLOATER_FRACTION = 0.001
MAX_DECIMATE_PASSES = 8
DECIMATE_SAFETY_MARGIN = 0.9

UV_ANGLE_LIMIT_DEGREES = 66.0
UV_ISLAND_MARGIN = 0.02
UV_PACK_MARGIN = 0.02
# Texels of bleed around each island. The default (16) is tuned for
# bilinear filtering on large maps and is far wider than the gap
# UV_PACK_MARGIN leaves between islands at 256px, so it would smear parts
# into each other's islands. PS1 filtering is nearest, so 2 texels is
# enough to kill seams. Pinned rather than inherited so the bake cannot
# change with a preferences default (Task 8 wants byte-identical exports).
BAKE_MARGIN_TEXELS = 2
BAKE_NODE_NAME = "RetroBakeTarget"
ALBEDO_NODE_NAME = "RetroAlbedo"
# The bake READS the source maps through the source's own UVs and WRITES
# through the new atlas UVs. Those are different layouts, so they cannot be
# the same layer -- see _prepare_uv_layers.
SOURCE_UV_NAME = "RetroSourceUV"
ATLAS_UV_NAME = "RetroAtlasUV"

# Principled BSDF input sockets that a contract drop_maps entry names.
DROPPABLE_SOCKETS = {
    "normal": "Normal",
    "roughness": "Roughness",
    "metallic": "Metallic",
    "emissive": "Emission Color",
    "specular": "Specular IOR Level",
    "occlusion": "Occlusion",
}


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


def _principled(material):
    if material is None or material.node_tree is None:
        return None
    for node in material.node_tree.nodes:
        if node.type == "BSDF_PRINCIPLED":
            return node
    return None


def _slot_materials(meshes: list) -> list:
    # Deterministic order, and only materials actually reachable from
    # exported geometry -- bpy.data.materials can hold orphans from the
    # import that would otherwise be edited (and counted) for nothing.
    seen = {}
    for obj in sorted(meshes, key=lambda item: item.name):
        for slot in obj.material_slots:
            if slot.material is not None:
                seen[slot.material.name] = slot.material
    return [seen[name] for name in sorted(seen)]


def _ensure_materials(meshes: list) -> None:
    # Cycles cannot bake an object whose material has no active image
    # texture node, and it cannot bake an object with no material at all.
    # _split_by_material leaves a part materialless only if its source slot
    # was empty, which the trenchgun fixture does not do -- but a different
    # source could, and a bake that dies with "No active image found" is a
    # much worse failure than a flat grey part.
    for obj in sorted(meshes, key=lambda item: item.name):
        if obj.material_slots and obj.material_slots[0].material is not None:
            continue
        material = bpy.data.materials.new(f"{obj.name}_Retro")
        if material.node_tree is None:
            # Blender 5.2 deprecates Material.use_nodes ("expected to be
            # removed in Blender 6.0") and new materials already carry a
            # node tree, so this only runs on an older build.
            material.use_nodes = True
        if obj.data.materials:
            obj.data.materials[0] = material
        else:
            obj.data.materials.append(material)


def _image_loaded(image) -> bool:
    if image is None:
        return False
    try:
        if image.size[0] == 0 or image.size[1] == 0:
            image.reload()
    except RuntimeError:
        return False
    return image.size[0] > 0 and image.size[1] > 0


def _resolve_source_maps(meshes: list, source: Path) -> dict:
    """Relink the source's texture files, and unlink the ones still missing.

    Authored FBX files routinely carry ABSOLUTE texture paths from whatever
    machine exported them -- the trenchgun fixture points every one of its
    maps at "D:\\Program Files\\BlenderProjects\\..." while the actual PNGs
    ship in a `textures/` directory beside the `.fbx`. Blender resolves none
    of them and Cycles evaluates an unresolvable image as BLACK.

    That failure is completely silent and it destroys this whole task: the
    bake produces a uniformly black image, quantization snaps it to the
    darkest palette entry, and the exported texture is one flat colour that
    passes palette conformance perfectly while carrying no information at
    all. A green test suite over a black texture is the worst outcome
    available here, so this stage exists to make the bake see real data.

    Two steps, in order:
      1. bpy.ops.file.find_missing_files re-points missing images at
         same-named files found under the source's own directory tree.
      2. Anything STILL unresolved is unlinked from the shader graph, so the
         bake falls back to the material's flat base colour instead of
         black. (The fixture's Cartridge maps land here: the FBX asks for
         "Cartridge_low_Cartridge_BaseColor.png" but the shipped file is
         named "Cartridge_BaseColor.png".)

    The counts are reported, because "this asset was baked from flat colours
    because its maps could not be found" is something an operator must be
    able to see rather than infer from a dull texture.
    """
    images = {}
    for material in _slot_materials(meshes):
        if material.node_tree is None:
            continue
        for node in material.node_tree.nodes:
            if node.type == "TEX_IMAGE" and node.image is not None:
                images[node.image.name] = node.image

    missing_before = [
        name for name, image in sorted(images.items()) if not _image_loaded(image)
    ]

    # Searched narrow-to-wide, and never wider than the asset's own folder:
    # find_missing_files walks the directory recursively, so handing it a
    # broad root would be both slow and a way to pick up an unrelated file
    # that merely shares a name.
    for directory in (source.parent, source.parent.parent):
        if not any(not _image_loaded(image) for image in images.values()):
            break
        if not directory.is_dir():
            continue
        try:
            bpy.ops.file.find_missing_files(directory=str(directory))
        except RuntimeError:
            continue

    unresolved = []
    for name, image in sorted(images.items()):
        if _image_loaded(image):
            continue
        unresolved.append(name)

    unlinked = 0
    for material in _slot_materials(meshes):
        tree = material.node_tree
        if tree is None:
            continue
        for node in tree.nodes:
            if node.type != "TEX_IMAGE" or _image_loaded(node.image):
                continue
            for output in node.outputs:
                for link in list(output.links):
                    tree.links.remove(link)
            unlinked += 1

    return {
        "missing_before": len(missing_before),
        "unresolved": unresolved,
        "unlinked_nodes": unlinked,
    }


def _prepare_uv_layers(meshes: list) -> None:
    """Split the source UVs and the atlas UVs onto two named layers.

    A bake is a transfer between two UV layouts, and this is the step that
    keeps them apart. The source's authored UVs are the only way to sample
    its base colour maps; the new atlas is the layout the baked result is
    written into. Unwrapping over the top of the source layer -- the obvious
    single-layer reading of "generate UVs" -- destroys the coordinates the
    bake needs to READ, and the bake then samples the source textures
    through atlas coordinates, i.e. it smears unrelated texels across every
    part. Like the other hazards in this stage it raises nothing.

    Naming both layers explicitly (rather than trusting index order or the
    importer's naming) is what lets _pin_source_uvs bind the source maps to
    the source layer by name, so the result does not depend on which layer
    happens to be flagged active when the bake runs.
    """
    for obj in sorted(meshes, key=lambda item: item.name):
        layers = obj.data.uv_layers
        if not layers:
            layers.new(name=SOURCE_UV_NAME)
        original = layers.active or layers[0]
        if original.name != ATLAS_UV_NAME:
            original.name = SOURCE_UV_NAME
        atlas = layers.get(ATLAS_UV_NAME)
        if atlas is None:
            atlas = layers.new(name=ATLAS_UV_NAME)
        # Set both flags: the bake target layer and the layer a texture node
        # samples by default are separately controlled, and which one a
        # given Blender version's bake honours is not worth betting on.
        layers.active = atlas
        atlas.active_render = True


def _pin_source_uvs(meshes: list) -> int:
    """Bind every surviving source map to the source UV layer by name."""
    pinned = 0
    for material in _slot_materials(meshes):
        tree = material.node_tree
        if tree is None:
            continue
        for node in list(tree.nodes):
            if node.type != "TEX_IMAGE" or not _image_loaded(node.image):
                continue
            vector = node.inputs["Vector"]
            if vector.links:
                continue
            uv_node = tree.nodes.new("ShaderNodeUVMap")
            uv_node.uv_map = SOURCE_UV_NAME
            tree.links.new(uv_node.outputs["UV"], vector)
            pinned += 1
    return pinned


def _finalize_uvs(meshes: list) -> None:
    """Leave only the atlas layer, so the export carries one TEXCOORD."""
    for obj in sorted(meshes, key=lambda item: item.name):
        layers = obj.data.uv_layers
        for layer in [item for item in layers if item.name != ATLAS_UV_NAME]:
            layers.remove(layer)
        if layers:
            layers.active = layers[0]
            layers[0].active_render = True


def _shared_uv_atlas(meshes: list) -> bool:
    # A PS1 asset carries ONE texture, so every part must own a distinct
    # region of ONE 0..1 UV space.
    #
    # The obvious reading of "generate UVs" -- smart_project each object on
    # its own, only when it has no UV layer -- is wrong here in two ways,
    # and both are silent:
    #
    #   1. Per-object smart_project gives every object the full 0..1 space.
    #      Six parts baked into one shared image then overwrite each other
    #      and the texture is garbage. Nothing errors.
    #   2. Skipping objects that already have UVs is worse, not better. The
    #      trenchgun's imported UVs are authored per-part and each part uses
    #      the whole 0..1 square, so "already has UVs" is precisely the
    #      overlapping case.
    #
    # So the atlas is always rebuilt, and it is rebuilt for all parts at
    # once: Blender's multi-object edit mode makes smart_project treat every
    # selected object's faces as one packing problem and lay their islands
    # out side by side in a single 0..1 space. _uv_overlap_cells() then
    # measures that this actually happened rather than trusting it.
    bpy.ops.object.select_all(action="DESELECT")
    ordered = sorted(meshes, key=lambda item: item.name)
    for obj in ordered:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = ordered[0]

    # smart_project writes into each mesh's ACTIVE uv layer, which
    # _prepare_uv_layers has already pointed at the atlas layer, so the
    # source layer is left intact for the bake to read through.
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(
        angle_limit=math.radians(UV_ANGLE_LIMIT_DEGREES),
        island_margin=UV_ISLAND_MARGIN,
    )
    # smart_project alone is NOT enough. Measured on the trenchgun, its own
    # packing left 10 overlapping cells out of 785 covered, because its
    # margin is applied per island as it is laid out rather than solved
    # globally. pack_islands re-solves the layout for every island of every
    # selected object at once with a guaranteed separation, and takes the
    # overlap to zero.
    bpy.ops.uv.select_all(action="SELECT")
    # No average_islands_scale here, though equalising texel density is the
    # obvious thing to reach for with parts this different in size. It was
    # tried and measured, and it made the distribution worse, not better: it
    # normalises island scale by 3D surface area, and the barrel has the most
    # of that, so the barrel GAINED texels (2111 -> 2422) while the smallest
    # part lost a third of its own (Cartridge 198 -> 126). smart_project's
    # own sizing already distributes better.
    #
    # shape_method is pinned rather than left to the version default because
    # it changes the packed layout, and Task 8 asserts byte-identical
    # exports.
    bpy.ops.uv.pack_islands(
        margin=UV_PACK_MARGIN,
        rotate=True,
        scale=True,
        merge_overlap=False,
        shape_method="CONCAVE",
    )
    bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.select_all(action="DESELECT")
    return True


def _rasterize_uvs(obj, resolution: int):
    """Cells of a resolution^2 grid whose centre falls inside a UV triangle."""
    import numpy

    claimed = numpy.zeros((resolution, resolution), dtype=bool)
    mesh = obj.data
    layer = mesh.uv_layers.active
    if layer is None:
        return claimed
    mesh.calc_loop_triangles()
    uvs = layer.data
    for triangle in mesh.loop_triangles:
        points = [uvs[index].uv for index in triangle.loops]
        ax, ay = points[0][0] * resolution, points[0][1] * resolution
        bx, by = points[1][0] * resolution, points[1][1] * resolution
        cx, cy = points[2][0] * resolution, points[2][1] * resolution
        area = (bx - ax) * (cy - ay) - (cx - ax) * (by - ay)
        if abs(area) < 1e-12:
            continue
        low_x = max(int(math.floor(min(ax, bx, cx) - 0.5)), 0)
        high_x = min(int(math.ceil(max(ax, bx, cx) + 0.5)), resolution - 1)
        low_y = max(int(math.floor(min(ay, by, cy) - 0.5)), 0)
        high_y = min(int(math.ceil(max(ay, by, cy) + 0.5)), resolution - 1)
        if high_x < low_x or high_y < low_y:
            continue
        grid_x = numpy.arange(low_x, high_x + 1, dtype=numpy.float64) + 0.5
        grid_y = numpy.arange(low_y, high_y + 1, dtype=numpy.float64) + 0.5
        px, py = numpy.meshgrid(grid_x, grid_y, indexing="ij")
        w0 = ((bx - ax) * (py - ay) - (px - ax) * (by - ay)) / area
        w1 = ((cx - bx) * (py - by) - (px - bx) * (cy - by)) / area
        w2 = ((ax - cx) * (py - cy) - (px - cx) * (ay - cy)) / area
        inside = (w0 >= 0.0) & (w1 >= 0.0) & (w2 >= 0.0)
        claimed[low_x : high_x + 1, low_y : high_y + 1] |= inside
    return claimed


def _uv_overlap_cells(meshes: list, resolution: int):
    """Measure cross-part UV overlap in the shared atlas.

    Returns (overlapping_texels, covered_texels). Run at the bake target's
    own resolution, so a "cell" IS a texel of the texture about to be baked
    and the question it answers is exactly the hazard: do two different
    parts write the same texel? A coarser grid would undersample thin
    islands and could report zero while real overlap existed.

    Any overlap at all is fatal -- whichever part bakes second wins that
    texel and the other part shows a stripe of someone else's surface.

    Adjacency does not count as overlap: texel centres are sampled, and
    UV_PACK_MARGIN separates islands by several texels, so two parts'
    islands merely sitting next to each other cannot produce a false
    positive.
    """
    import numpy

    owner = numpy.full((resolution, resolution), -1, dtype=numpy.int32)
    overlapping = 0
    per_part = {}
    for index, obj in enumerate(sorted(meshes, key=lambda item: item.name)):
        claimed = _rasterize_uvs(obj, resolution)
        overlapping += int(numpy.count_nonzero(claimed & (owner >= 0)))
        owner[claimed] = index
        per_part[obj.name] = int(numpy.count_nonzero(claimed))
    return overlapping, int(numpy.count_nonzero(owner >= 0)), per_part


def _bake_target(meshes: list, size: int):
    image = bpy.data.images.new("RetroBake", width=size, height=size, alpha=True)
    for material in _slot_materials(meshes):
        tree = material.node_tree
        if tree is None:
            continue
        node = tree.nodes.new("ShaderNodeTexImage")
        node.name = BAKE_NODE_NAME
        node.label = BAKE_NODE_NAME
        node.image = image
        # Cycles picks the bake destination as the image texture node that is
        # BOTH active and selected, and it reports a miss as an Info line
        # ("No active and selected image texture node found in material X")
        # while still exiting successfully -- so getting this wrong yields a
        # bake that writes nothing at all, an untouched black image, and a
        # green test suite. Deselect first, then set active, then select:
        # assigning nodes.active does not imply selection.
        for other in tree.nodes:
            other.select = False
        tree.nodes.active = node
        node.select = True
    return image


def _bake(meshes: list) -> None:
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    # Pinned explicitly rather than left at whatever --factory-startup
    # happens to default to, because Task 8 asserts byte-identical exports:
    # GPU sampling and denoising both make the baked bytes machine
    # dependent. A DIFFUSE/COLOR bake is a texture-space lookup of base
    # colour, so one CPU sample is not an approximation -- it is the answer.
    scene.cycles.device = "CPU"
    scene.cycles.samples = 1
    scene.cycles.use_denoising = False
    scene.render.bake.margin = BAKE_MARGIN_TEXELS
    scene.render.bake.margin_type = "ADJACENT_FACES"
    scene.render.bake.use_clear = True
    bpy.ops.object.select_all(action="DESELECT")
    ordered = sorted(meshes, key=lambda item: item.name)
    for obj in ordered:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = ordered[0]
    bpy.ops.object.bake(
        type="DIFFUSE", pass_filter={"COLOR"}, use_selected_to_active=False
    )


def _bake_wrote_nothing(image) -> bool:
    """True if the bake left the image exactly as it was created: all zero.

    Cycles reports "No active and selected image texture node found in
    material X" as an Info line and still succeeds, so a misconfigured bake
    target produces an untouched black image rather than an error. Every
    texel then quantizes to the darkest palette entry, and the result is a
    flat texture that passes palette conformance perfectly while carrying no
    information whatsoever. This is the check that turns that into a
    failure; it cost a full debugging round to find once.
    """
    import numpy

    pixels = numpy.array(image.pixels[:], dtype=numpy.float32).reshape(-1, 4)
    return not bool(numpy.any(pixels[:, :3] > 0.0))


def _quantize_to_png(image, palette_path: Path) -> tuple[bytes, int, int]:
    """Snap every texel of the baked image to the pack palette.

    Returns (png_bytes, palette_size).

    Colour management, empirically established inside Blender 5.2 rather
    than assumed:

    bpy.data.images.new() produces a BYTE-backed image (is_float is False).
    For such an image, image.pixels is a raw passthrough of the stored 8-bit
    buffer -- writing 0.5 stores byte 128 and Blender writes byte 128 to
    disk, with colorspace_settings.name ("sRGB" or "Non-Color") making no
    difference to the saved bytes. The bake already sRGB-encoded the linear
    shader result on its way into that buffer.

    So image.pixels * 255 IS the sRGB byte, and the palette is sRGB bytes:
    they are already in the same space. The linear->sRGB->snap->sRGB->linear
    round trip the brief specifies would shift every channel by several
    8-bit steps in each direction (it assumes a float image) and, worse, its
    final sRGB->linear step reintroduces exactly the rounding error that
    breaks exactness. It is deliberately not performed.

    Exactness is then guaranteed structurally rather than hoped for: the
    snapped bytes are encoded to PNG here, with factory.png, and that PNG is
    handed to the glTF exporter as a packed image file. The exporter embeds
    a packed PNG's bytes verbatim, so no further colour management can touch
    them between here and Gate 1.
    """
    import numpy

    palette = load_palette(palette_path)
    entries = numpy.array(palette, dtype=numpy.int32)

    size = image.size[0], image.size[1]
    raw = numpy.array(image.pixels[:], dtype=numpy.float64)
    pixels = numpy.clip(numpy.rint(raw * 255.0), 0, 255).astype(numpy.int32)
    pixels = pixels.reshape(size[1], size[0], 4)

    rgb = pixels[:, :, :3].reshape(-1, 3)
    # argmin takes the lowest index on a tie and load_palette returns its
    # colours sorted, which is the same tie-break factory.palette.nearest
    # gets from min(); the two therefore agree colour for colour.
    distances = ((rgb[:, None, :] - entries[None, :, :]) ** 2).sum(axis=2)
    snapped = entries[distances.argmin(axis=1)].reshape(size[1], size[0], 3)

    out = numpy.empty((size[1], size[0], 4), dtype=numpy.uint8)
    out[:, :, :3] = snapped.astype(numpy.uint8)
    # Fully opaque: unbaked background texels come out of the bake at alpha
    # 0, and conformance checks RGB on every pixel regardless of alpha, so
    # they are palette-snapped like any other texel. Leaving them
    # transparent would only invite an exporter alpha mode we do not want.
    out[:, :, 3] = 255
    # image.pixels is bottom-row-first; PNG is top-row-first.
    out = out[::-1, :, :]
    distinct = len(numpy.unique(snapped.reshape(-1, 3), axis=0))
    return encode_rgba(size[0], size[1], out.tobytes()), len(palette), distinct


def _apply_albedo(meshes: list, png_bytes: bytes, filtering: str):
    """Load the quantized PNG back in as the one albedo map for every part."""
    scratch = Path(tempfile.mkdtemp(prefix="retro_albedo_"))
    try:
        path = scratch / "retro_albedo.png"
        path.write_bytes(png_bytes)
        image = bpy.data.images.load(str(path))
        # Packing copies the exact file bytes into the blend, which is what
        # the glTF exporter then embeds verbatim -- and it frees us from the
        # scratch file, which is deleted below so no export output depends
        # on a temp path.
        image.pack()
        image.colorspace_settings.name = "sRGB"
    finally:
        shutil.rmtree(scratch, ignore_errors=True)

    interpolation = "Closest" if filtering == "nearest" else "Linear"
    for material in _slot_materials(meshes):
        tree = material.node_tree
        if tree is None:
            continue
        bsdf = _principled(material)
        if bsdf is None:
            continue
        stale = tree.nodes.get(BAKE_NODE_NAME)
        if stale is not None:
            tree.nodes.remove(stale)
        node = tree.nodes.new("ShaderNodeTexImage")
        node.name = ALBEDO_NODE_NAME
        node.label = ALBEDO_NODE_NAME
        node.image = image
        node.interpolation = interpolation
        socket = bsdf.inputs["Base Color"]
        for link in list(socket.links):
            tree.links.remove(link)
        tree.links.new(node.outputs["Color"], socket)
    return image


def _strip_maps(meshes: list, drop_maps: list) -> list:
    removed = set()
    for material in _slot_materials(meshes):
        tree = material.node_tree
        bsdf = _principled(material)
        if bsdf is None:
            continue
        for name in drop_maps:
            socket = bsdf.inputs.get(DROPPABLE_SOCKETS.get(name, ""))
            if socket is None:
                continue
            for link in list(socket.links):
                tree.links.remove(link)
            removed.add(name)
    return sorted(removed)


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
        # Initialised on the failure path too: run_blender_script raises
        # BlenderError if the report is missing, and a report missing keys
        # its caller indexes is only marginally better. A failed run must
        # still be readable.
        "texture": {
            "size": 0,
            "quantized": False,
            "palette_colours": 0,
            "distinct_colours": 0,
            "atlas_coverage": 0.0,
        },
        "dropped_maps": [],
        "vertex_light_bake": False,
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

        _ensure_materials(meshes)
        resolved = _resolve_source_maps(meshes, Path(payload["source"]))
        report["stages"]["source_maps_missing"] = resolved["missing_before"]
        report["stages"]["source_maps_unresolved"] = resolved["unresolved"]

        _prepare_uv_layers(meshes)
        report["stages"]["source_uvs_pinned"] = _pin_source_uvs(meshes)
        size = contract["texture_size"]
        report["stages"]["uv_regenerated"] = _shared_uv_atlas(meshes)
        overlapping, covered, per_part = _uv_overlap_cells(meshes, size)
        report["stages"]["uv_overlap_cells"] = overlapping
        report["stages"]["uv_covered_cells"] = covered
        # Per-part texel counts: a part that scores 0 here is in the export
        # but has no texture, which no aggregate number would reveal.
        report["stages"]["uv_texels_per_part"] = per_part
        if overlapping:
            # A shared atlas with cross-part overlap bakes garbage: two
            # parts write the same texels and the second one wins. That is
            # invisible in every other number this report carries, so it is
            # a hard failure rather than a warning.
            raise ValueError(
                f"shared UV atlas overlaps: {overlapping} of {covered} "
                f"covered texels are claimed by more than one part at "
                f"{size}x{size}"
            )

        baked = _bake_target(meshes, size)
        _bake(meshes)
        if _bake_wrote_nothing(baked):
            raise ValueError(
                "bake produced an entirely black image: Cycles found no "
                "active and selected image texture node, so nothing was "
                "written. Quantizing this would yield a flat texture that "
                "passes palette conformance while carrying no detail."
            )
        png_bytes, palette_colours, distinct = _quantize_to_png(
            baked, Path(payload["palette"])
        )
        _apply_albedo(meshes, png_bytes, contract.get("filtering", "nearest"))
        bpy.data.images.remove(baked)
        _finalize_uvs(meshes)
        report["texture"] = {
            "size": size,
            "quantized": True,
            "palette_colours": palette_colours,
            "distinct_colours": distinct,
            # What fraction of the atlas the parts actually occupy. Not a
            # pass/fail number -- it is here so a pack whose textures are
            # mostly empty is visible rather than merely disappointing.
            "atlas_coverage": round(covered / float(size * size), 4),
        }

        report["dropped_maps"] = _strip_maps(meshes, contract["drop_maps"])
        # The style contract validates a vertex_light_bake flag, but this
        # plan does not implement vertex-colour lighting. Reported as False
        # so no downstream stage can assume it took effect.
        report["vertex_light_bake"] = False

        bpy.ops.object.select_all(action="SELECT")
        bpy.ops.export_scene.gltf(
            filepath=payload["output"],
            export_format="GLB",
            use_selection=True,
            export_apply=True,
            export_yup=(contract["up_axis"] == "Y"),
            export_image_format="AUTO",
        )
        report["ok"] = True
    except Exception as error:  # reported, never swallowed
        report["error"] = f"{type(error).__name__}: {error}"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
