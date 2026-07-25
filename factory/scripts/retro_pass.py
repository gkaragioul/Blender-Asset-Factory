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
ALPHA_BAKE_NODE_NAME = "RetroAlphaBakeTarget"
ALBEDO_NODE_NAME = "RetroAlbedo"
CUTOUT_NODE_NAME = "RetroCutout"

# Cutout is BINARY (glTF alphaMode MASK), not graded (BLEND).
#
# PS1 hardware had no per-texel alpha blending for this idiom. Barbed wire,
# chain-link, foliage and grates were 1-bit stencils: a texel was drawn or it
# was not. Graded alpha is also actively worse in an engine -- BLEND geometry
# has to be depth-sorted per draw and self-sorting fails on exactly the
# interpenetrating shapes (a wire coil, a chain-link fence) this is for,
# producing the very artefacts the PS1 idiom avoids.
#
# So the mask is thresholded IN THE SHADER during the alpha bake rather than
# baked as a gradient and thresholded afterwards, which also removes a colour
# management question: a bake of a graded value lands in the byte buffer
# sRGB-encoded, so "0.5" would read back as 188 rather than 128 and the
# effective cutoff would silently drift. A LESS_THAN node outputs exactly 0.0
# or 1.0, and 0.0 and 1.0 are fixed points of any transfer function.
#
# 0.5 is also glTF's DEFAULT alphaCutoff, which is why the exported material
# carries no alphaCutoff field: absent means 0.5. Blender's exporter detects
# the cutoff from the node setup feeding the Alpha socket (a Math:ROUND node
# means 0.5), not from any material property -- see _wire_cutout.
ALPHA_CUTOFF = 0.5
# Scalar alpha is deliberately NOT a cutout source. A material whose Alpha is
# an unlinked default_value carries a uniform translucency, which is a BLEND
# property of the whole surface and is preserved by _restore_pbr_after_bake
# writing it out as a factor. Feeding it into the mask instead would punch
# the part's entire atlas region out at any value below the cutoff -- the
# multi-texture cube's 0.45 TranslucentMaterial would vanish completely.
ALPHA_OPAQUE = 1.0
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

            # The source is a SKINNED mesh, so its vertices carry deform
            # weights indexed against the source object's vertex groups. The
            # parts built here are standalone and unparented, and the loop
            # below removes the armature outright, so they own no vertex
            # groups at all -- every one of those indices dangles. Blender's
            # own validator rejects the result ("Vertex N has invalid deform
            # group 7", measured on all 7 trenchgun parts) and the glTF
            # exporter then logs "Mesh <name> is not valid, and may be
            # exported wrongly" for each one. Nothing downstream of the split
            # reads weights, so the layer is dropped here, at the point it
            # stops meaning anything, rather than left for _validate_meshes
            # to null out after the fact.
            deform = bm.verts.layers.deform.active
            if deform is not None:
                bm.verts.layers.deform.remove(deform)

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


def _validate_meshes(meshes: list) -> dict:
    """Bring every mesh into a state Blender's own validator accepts.

    Returns {object_name: polygons_removed} for each mesh that needed
    repairing, so a repair is a reported fact rather than a silent one. A
    mesh can appear here with a count of 0: `mesh.validate()` also fixes
    custom-data damage (dangling deform-group indices, out-of-range material
    indices) that deletes no geometry at all, and that damage is just as
    fatal to the export as a broken face.

    Why this is not optional bookkeeping: an invalid mesh makes the glTF
    exporter log "Mesh <name> is not valid, and may be exported wrongly" and
    then export SOMETHING ANYWAY -- the exporter runs its own repair on the
    way out. Measured on the trenchgun: the pass reported 2479 triangles
    while the GLB it wrote contained 2470. Nine triangles existed in every
    in-process measurement and in no exported file.

    That gap is precisely what makes Gate 2 (silhouette IoU, Task 9)
    untrustworthy: the IoU compares a render of the exported asset against
    measurements taken here, and if the exporter is quietly repairing
    geometry on its way out then the two sides are not the same mesh. The
    repair has to happen HERE, where the result is measurable, not there,
    where it is only a warning line.

    `clean_customdata=False` is deliberate. The default (True) strips custom
    data layers it judges invalid, and by the time this runs the meshes carry
    the two named UV layers the bake depends on (SOURCE_UV_NAME and
    ATLAS_UV_NAME, see _prepare_uv_layers). Losing one of those silently
    would break the bake far more thoroughly than the invalidity being fixed.
    """
    repaired = {}
    for obj in sorted(meshes, key=lambda item: item.name):
        mesh = obj.data
        before = len(mesh.polygons)
        if mesh.validate(verbose=False, clean_customdata=False):
            mesh.update()
            repaired[obj.name] = before - len(mesh.polygons)
    return repaired


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
    #
    # This rotation is the ONE and ONLY axis conversion in the pass. main()
    # therefore exports with export_yup=False -- see the comment there; the
    # exporter's own conversion would compound with this one and ship every
    # asset misoriented.
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


def _decimate(meshes: list, budget: int) -> tuple[int, int, dict]:
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

    # The COLLAPSE modifier emits DUPLICATE FACES -- measured on the
    # trenchgun, 9 of them across 4 of the 7 parts ("Face N is a duplicate of
    # N"). They have to go: an invalid mesh makes the glTF exporter repair it
    # on the way out, so triangles_out would describe geometry that never
    # shipped. See _validate_meshes.
    #
    # AFTER the loop, not inside it, and this is measured rather than
    # stylistic. Validating each pass changes what the NEXT pass's ratio is
    # computed from, which changes the whole collapse trajectory and lands on
    # different final geometry -- not merely the same geometry minus its
    # duplicates. On the trenchgun that cost real silhouette fidelity: Gate 2
    # (Task 9) measures IoU per view against the unconverted source, and
    # per-pass validation dropped the worst view from 0.49/0.47-passing
    # margins to 0.4707, under the 0.5 threshold. Cleaning up once at the end
    # leaves the decimation the loop actually tuned for exactly as it was and
    # only removes the degenerate faces from it.
    #
    # Recounting afterwards is what keeps triangles_out honest: validation
    # only ever DELETES geometry, so the count can only fall, and a count
    # that was already under budget stays under it.
    repaired = _validate_meshes(meshes)
    if repaired:
        current = _triangle_count(meshes)
    return current, attempts, repaired


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


# Principled BSDF inputs that suppress the diffuse response, and the values
# that neutralise them for an albedo bake. See _neutralize_pbr_for_bake.
BAKE_NEUTRAL_INPUTS = (
    ("Metallic", 0.0),
    ("Transmission Weight", 0.0),
    ("Alpha", 1.0),
)

# drop_maps entries whose scalar FACTOR is also flattened in the EXPORT, not
# merely unlinked. Only metallic: see _restore_pbr_after_bake.
FLATTEN_FACTOR_ON_DROP = ("metallic",)


def _socket_value(socket):
    value = socket.default_value
    try:
        return list(value)
    except TypeError:
        return value


def _neutralize_pbr_for_bake(meshes: list) -> tuple[list, list]:
    """Zero the shader inputs that make a DIFFUSE/COLOR bake come out black.

    Returns (changed_socket_names, restore_plan). The restore plan is not
    optional bookkeeping -- see _restore_pbr_after_bake for why leaving these
    mutations in place silently corrupts the exported asset.

    A fully metallic surface has NO diffuse component, so Cycles' DIFFUSE
    pass returns black for it however rich its base colour texture is. The
    same is true of full transmission, and alpha below 1 attenuates the
    baked albedo toward black in proportion to how transparent it is.

    This is not hypothetical and not rare. glTF's `metallicFactor` DEFAULTS
    TO 1.0 when the field is absent, so any glTF/GLB source that omits it
    imports as fully metallic -- and metal is the normal case for the
    weapons this pack is built from. Such an asset baked to a completely
    black albedo, which `_bake_wrote_nothing` would then reject outright,
    turning a perfectly convertible source into a hard failure.

    Neutralising happens BEFORE the bake, unlike `_strip_maps`, which runs
    after it and only unlinks the map named in the contract's drop_maps --
    unlinking a metallic *texture* leaves the socket's default_value at 1.0,
    so it would not have helped.

    Links are recorded and re-made rather than abandoned, because these
    sockets are neutralised only to get a clean albedo out of the bake; they
    are not statements about what the asset is.
    """
    changed = set()
    restore = []
    for material in _slot_materials(meshes):
        bsdf = _principled(material)
        if bsdf is None:
            continue
        for name, neutral in BAKE_NEUTRAL_INPUTS:
            socket = bsdf.inputs.get(name)
            if socket is None:
                continue
            restore.append(
                (
                    material.name,
                    name,
                    _socket_value(socket),
                    [(link.from_socket, link.to_socket) for link in socket.links],
                )
            )
            for link in list(socket.links):
                material.node_tree.links.remove(link)
                changed.add(name)
            if socket.default_value != neutral:
                socket.default_value = neutral
                changed.add(name)
    return sorted(changed), restore


def _restore_pbr_after_bake(meshes: list, restore: list, drop_maps: list) -> dict:
    """Put back everything _neutralize_pbr_for_bake changed, except metallic.

    This exists because the bake's needs and the EXPORT's contents are two
    different things, and conflating them destroys assets silently.

    The glTF exporter writes an unlinked Principled socket's default_value
    out as a material FACTOR. So an unrestored neutralisation does not just
    affect the bake -- it ships. Left alone, every converted asset would
    export alpha forced to 1.0 regardless of what the source said.

    That is not a cosmetic issue. Forcing alpha to 1.0 turns intentionally
    transparent or cutout geometry into a solid slab, and NO gate catches it:
    Gate 1 checks palette conformance and triangle budget, Gate 2 compares
    silhouettes of the same geometry before and after, so both pass happily.
    Alpha cutout is exactly how PS1-era art renders barbed wire, chain-link,
    foliage and glass -- and `barbed_wire_coil` is a planned asset in this
    very pack. Transmission is the same class of intent, so it is restored
    too.

    Metallic is the one deliberate exception, and it is driven by the
    contract rather than left over from the bake: when the contract's
    drop_maps names `metallic`, the asset is declared non-metallic, so the
    exported factor is flattened to 0 to match. This is also required for
    correctness rather than merely allowed -- the pass bakes flat albedo into
    the base colour texture, and a renderer told `metallicFactor: 1` treats
    that albedo as reflectance and draws the asset black, the exact opposite
    of the flat PS1 look intended.

    Returns the sockets restored and the sockets deliberately left flat, so
    the decision is visible in the report instead of implicit.
    """
    flat_sockets = {
        DROPPABLE_SOCKETS[name]
        for name in drop_maps
        if name in FLATTEN_FACTOR_ON_DROP and name in DROPPABLE_SOCKETS
    }
    materials = {material.name: material for material in _slot_materials(meshes)}
    restored = set()
    flattened = set()
    for material_name, socket_name, original, links in restore:
        material = materials.get(material_name)
        if material is None:
            continue
        bsdf = _principled(material)
        if bsdf is None:
            continue
        socket = bsdf.inputs.get(socket_name)
        if socket is None:
            continue
        if socket_name in flat_sockets:
            flattened.add(socket_name)
            continue
        socket.default_value = original
        for from_socket, to_socket in links:
            try:
                material.node_tree.links.new(from_socket, to_socket)
            except (ReferenceError, RuntimeError):
                # The node feeding this socket may already be gone; the
                # restored default_value still carries the source's intent.
                pass
        restored.add(socket_name)
    return {"restored": sorted(restored), "flattened": sorted(flattened)}


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


def _prepare_bake(meshes: list) -> None:
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


def _bake(meshes: list) -> None:
    _prepare_bake(meshes)
    bpy.ops.object.bake(
        type="DIFFUSE", pass_filter={"COLOR"}, use_selected_to_active=False
    )


def _alpha_sources(restore: list) -> dict:
    """material name -> the socket feeding its Alpha, as it was BEFORE the bake.

    _neutralize_pbr_for_bake forces every Alpha socket to 1.0 and unlinks it,
    because alpha below 1 attenuates a DIFFUSE bake toward black. It records
    what it broke so _restore_pbr_after_bake can put it back; the same record
    is the only surviving description of where the cutout mask came from, so
    the alpha bake reads it rather than re-deriving anything.

    Only the LINK matters here, never the scalar default_value -- see
    ALPHA_OPAQUE.
    """
    sources = {}
    for material_name, socket_name, _original, links in restore:
        if socket_name != "Alpha" or not links:
            continue
        sources[material_name] = links[0][0]
    return sources


def _output_node(tree):
    for node in tree.nodes:
        if node.type == "OUTPUT_MATERIAL" and node.is_active_output:
            return node
    for node in tree.nodes:
        if node.type == "OUTPUT_MATERIAL":
            return node
    return None


def _bake_alpha(meshes: list, size: int, sources: dict):
    """Bake the source cutout masks into their own image, through the atlas.

    Cycles has NO alpha bake pass, so the mask is smuggled through the one
    pass that transports an arbitrary value untouched: EMIT. Each material's
    surface is temporarily replaced with an Emission shader whose colour is
    the mask, the EMIT pass is baked into a second image, and the surface is
    put back. The objects, their selection and their UV layers are unchanged
    from the colour bake, so this lands in the SAME shared atlas layout --
    which it must, because the two images are merged texel for texel.

    The emitted value is `alpha < ALPHA_CUTOFF`, i.e. 1.0 means CUT AWAY.
    That inversion is not a matter of taste. Cycles clears the target to zero
    and only writes texels the geometry actually covers, so under the natural
    "1.0 means opaque" reading every texel the bake never reached -- the whole
    atlas background -- would read back as fully transparent and be punched
    out of the export. With the inversion, "not baked" and "solid" are the
    same value, and only a texel the bake positively decided was transparent
    becomes a hole.

    Materials with no recorded alpha link emit a constant 0: their surface is
    solid as far as the MASK is concerned, whatever their scalar alpha says.
    """
    image = bpy.data.images.new(
        "RetroBakeAlpha", width=size, height=size, alpha=True
    )
    undo = []
    for material in _slot_materials(meshes):
        tree = material.node_tree
        if tree is None:
            continue
        output = _output_node(tree)
        created_output = None
        if output is None:
            # _bake_target already planted BAKE_NODE_NAME in this tree and
            # left it active+selected (it does not skip on a missing output
            # node -- only on a missing tree). Skipping here used to leave
            # that node in place, so the EMIT bake below would land on the
            # colour atlas instead of a per-material alpha target -- the
            # exact hazard the paragraph above this loop describes, just not
            # noticed on this path. A material with no Material Output has
            # no surface a renderer reads anyway, so wiring one in for the
            # sole purpose of hosting this bake's target node is harmless.
            output = tree.nodes.new("ShaderNodeOutputMaterial")
            created_output = output
        surface = output.inputs["Surface"]

        # LESS_THAN outputs exactly 0.0 or 1.0, so the mask is binary before
        # it ever reaches the byte buffer and no transfer function can move
        # it. See ALPHA_CUTOFF.
        threshold = tree.nodes.new("ShaderNodeMath")
        threshold.operation = "LESS_THAN"
        threshold.inputs[1].default_value = ALPHA_CUTOFF
        source = sources.get(material.name)
        if source is None:
            threshold.inputs[0].default_value = ALPHA_OPAQUE
        else:
            tree.links.new(source, threshold.inputs[0])

        emission = tree.nodes.new("ShaderNodeEmission")
        tree.links.new(threshold.outputs["Value"], emission.inputs["Color"])

        previous = [(link.from_socket, link.to_socket) for link in surface.links]
        for link in list(surface.links):
            tree.links.remove(link)
        tree.links.new(emission.outputs["Emission"], surface)

        target = tree.nodes.new("ShaderNodeTexImage")
        target.name = ALPHA_BAKE_NODE_NAME
        target.label = ALPHA_BAKE_NODE_NAME
        target.image = image
        # Same active-and-selected dance as _bake_target, and the same silent
        # failure if it is skipped: the colour bake's target node is still in
        # this tree and would otherwise stay active, so the alpha bake would
        # overwrite the albedo with the mask.
        for other in tree.nodes:
            other.select = False
        tree.nodes.active = target
        target.select = True

        undo.append(
            (tree, surface, previous, (threshold, emission, target), created_output)
        )

    try:
        _prepare_bake(meshes)
        bpy.ops.object.bake(type="EMIT", use_selected_to_active=False)
    finally:
        for tree, surface, previous, temporary, created_output in undo:
            for link in list(surface.links):
                tree.links.remove(link)
            for from_socket, to_socket in previous:
                try:
                    tree.links.new(from_socket, to_socket)
                except (ReferenceError, RuntimeError):
                    pass
            for node in temporary:
                tree.nodes.remove(node)
            if created_output is not None:
                tree.nodes.remove(created_output)
    return image


def _cut_mask(image):
    """Texels the alpha bake marked as cut away, as a [y][x] boolean grid.

    Row order matches image.pixels (bottom row first), which is also the row
    order _rasterize_uvs indexes by, so the two can be intersected directly.
    """
    import numpy

    width, height = image.size[0], image.size[1]
    raw = numpy.array(image.pixels[:], dtype=numpy.float32).reshape(height, width, 4)
    return raw[:, :, 0] > 0.5


def _cut_texels_per_material(meshes: list, cut, resolution: int) -> dict:
    """material name -> how many of ITS atlas texels the mask cuts away.

    Attributed per material rather than counted globally because glTF's
    alphaMode is a per-MATERIAL declaration. A pack part that carries no
    cutout must not be declared MASK just because a part it shares the atlas
    with does: MASK makes an engine discard texels below the cutoff, so a
    wrongly-declared material is a new way to lose geometry.
    """
    import numpy

    counts = {}
    for obj in sorted(meshes, key=lambda item: item.name):
        material = obj.material_slots[0].material if obj.material_slots else None
        if material is None:
            continue
        # _rasterize_uvs is indexed [x][y]; cut is [y][x].
        claimed = _rasterize_uvs(obj, resolution).T
        counts[material.name] = counts.get(material.name, 0) + int(
            numpy.count_nonzero(claimed & cut)
        )
    return counts


PIXEL_SEMANTICS = "byte-passthrough"


def _verify_pixel_semantics() -> str:
    """Pin the colour-management assumption _quantize_to_png depends on.

    _quantize_to_png treats `image.pixels * 255` as the stored sRGB byte.
    That is true because bpy.data.images.new() returns a BYTE-backed image
    whose pixels are a raw passthrough of the 8-bit buffer -- measured in
    Blender 5.2: writing 0.5 reads back 128/255 and saves as byte 128, not
    the 188 an sRGB-encoding round trip would give.

    That assumption is invisible if it breaks. Because the exported PNG is
    assembled literally out of palette entry bytes, it stays palette-exact
    by construction no matter what the source values meant -- so if a future
    Blender makes these images float-backed, or starts applying a transfer
    function on write, then rint(raw * 255) misreads every texel, every
    texel snaps to the WRONG palette entry, conformance still passes,
    distinct_colours stays plausible, and the only symptom is a
    systematically washed-out texture that nothing complains about.

    So the assumption is asserted rather than assumed, on every run, and it
    fails the pass loudly if the buffer semantics change underneath it.
    """
    probe = bpy.data.images.new("RetroPixelProbe", width=2, height=1, alpha=True)
    try:
        if probe.is_float:
            raise ValueError(
                "bpy.data.images.new returned a float-backed image; "
                "_quantize_to_png assumes a byte buffer whose pixels are "
                "raw 8-bit values, so its rint(pixels * 255) would misread "
                "every texel and quantize to the wrong palette entries"
            )
        probe.pixels = [0.5, 0.5, 0.5, 1.0, 0.25, 0.25, 0.25, 1.0]
        readback = [int(round(value * 255.0)) for value in probe.pixels[:]]
        expected = [128, 128, 128, 255, 64, 64, 64, 255]
        if readback != expected:
            raise ValueError(
                "image.pixels is no longer a raw 8-bit passthrough: wrote "
                f"[0.5, 0.25] and read back {readback}, expected {expected}. "
                "A transfer function is being applied to the pixel buffer, "
                "so _quantize_to_png would snap every texel to the wrong "
                "palette entry while still producing a palette-exact PNG"
            )
    finally:
        bpy.data.images.remove(probe)
    return PIXEL_SEMANTICS


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


def _quantize_to_png(image, palette_path: Path, cut=None) -> tuple[bytes, int, int]:
    """Snap every texel of the baked image to the pack palette.

    Returns (png_bytes, palette_size, distinct_colours).

    Quantization applies to RGB ONLY. `cut` (from _cut_mask) is written
    straight into the alpha channel as 0 or 255 with no snapping and no
    dithering, and that separation is load-bearing in both directions: Gate 1
    asserts every exported texel's RGB is an exact palette member, so an
    alpha-aware nearest-colour search would break every asset in the pack;
    and a dithered alpha would turn a 1-bit stencil into speckle, which is
    the one thing a MASK material cannot represent.

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
    # Opaque by default, cut only where the alpha bake positively said so.
    #
    # The colour bake's OWN alpha channel is not consulted and never was: it
    # is 0 across the whole atlas background, so honouring it would punch out
    # every unbaked texel. Conformance checks RGB on every pixel regardless
    # of alpha, so background texels are palette-snapped like any other and
    # stay opaque.
    out[:, :, 3] = 255
    if cut is not None:
        out[:, :, 3] = numpy.where(cut, 0, 255).astype(numpy.uint8)
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


def _drop_foreign_textures(meshes: list) -> list:
    """Remove every image texture node that is not the baked albedo.

    "The baked image is the only texture written" has to be ENFORCED, not
    left to be incidentally true. _strip_maps only unlinks the sockets named
    in the contract's drop_maps (normal, roughness, metallic) and
    _apply_albedo only clears Base Color, so any surviving image on some
    other socket -- Emission Color, Specular IOR Level, Alpha, Coat, a
    socket a future Principled BSDF adds -- is still reachable and the
    exporter writes it as a SECOND image.

    That failure is expensive to diagnose from the far end: Gate 1 opens the
    export, finds an unquantized source PNG next to the palettized one, and
    reports thousands of foreign pixels. Every clue points at the quantizer,
    which is innocent. The trenchgun fixture happens to carry no emissive or
    alpha map, so nothing about the fixture would ever reveal it.

    Removing by "is not the albedo node" rather than by a list of sockets to
    clear is the point: a list can only ever cover the sockets someone
    thought of, and Alpha was already missing from DROPPABLE_SOCKETS.

    KNOWN GAP -- this is not exhaustive, despite covering every socket. It
    walks only `material.node_tree.nodes` and does not recurse into
    ShaderNodeGroup node trees, so a TEX_IMAGE nested inside a node group
    (a common PBR channel-packing pattern) still reaches the exporter and
    still becomes a second image. Tracked as a known Minor rather than fixed
    here; do not read this function as a guarantee that only one image can
    ever be exported.
    """
    removed = []
    for material in _slot_materials(meshes):
        tree = material.node_tree
        if tree is None:
            continue
        for node in list(tree.nodes):
            if node.type != "TEX_IMAGE" or node.name == ALBEDO_NODE_NAME:
                continue
            if node.image is not None:
                removed.append(node.image.name)
            tree.nodes.remove(node)
    return sorted(set(removed))


def _wire_cutout(meshes: list, cutout: set, textured: set) -> list:
    """Point every cutout material's Alpha socket at the baked atlas alpha.

    Baking the mask into the exported PNG is only half the job. glTF's
    default alphaMode is OPAQUE, and an OPAQUE material ignores the alpha
    channel entirely -- so a perfect mask that no material declares renders
    as a solid slab in every engine, which is the failure this whole path
    exists to prevent, reached by a different route.

    Blender's glTF exporter does not read alphaMode from any material
    property. It infers it from the node setup feeding the Alpha socket, and
    a `Math:ROUND` node is the shape it recognises as alpha clipping with a
    cutoff of 0.5 (see `detect_alpha_clip` in the exporter's
    search_node_tree). That is exactly the cutoff the mask was thresholded
    at, and it is also glTF's default, so the exporter omits the alphaCutoff
    field -- absent means 0.5.

    Sourcing the alpha from the ALBEDO node, which the exporter also uses for
    Base Color, is what keeps the export to ONE image: the exporter's
    "happy path" copies a packed PNG's bytes verbatim when every channel it
    needs comes from a single image with no channel remapping, and RGB+A from
    one node is precisely that. Wiring alpha from anywhere else would make it
    composite a new PNG, and the palette exactness Gate 1 checks would be
    lost on the way out.

    `textured` names every material whose Alpha socket was linked in the
    SOURCE; those not in `cutout` had a link whose mask turned out to cut
    nothing. Their restored link is cleared rather than left alone, because
    _drop_foreign_textures has by now deleted the image it read from and what
    remains is a stranded node chain the exporter would still interpret.
    """
    wired = []
    for material in _slot_materials(meshes):
        tree = material.node_tree
        bsdf = _principled(material)
        if tree is None or bsdf is None:
            continue
        socket = bsdf.inputs.get("Alpha")
        if socket is None:
            continue
        if material.name in cutout:
            albedo = tree.nodes.get(ALBEDO_NODE_NAME)
            if albedo is None:
                continue
            for link in list(socket.links):
                tree.links.remove(link)
            clip = tree.nodes.new("ShaderNodeMath")
            clip.operation = "ROUND"
            clip.name = CUTOUT_NODE_NAME
            clip.label = CUTOUT_NODE_NAME
            tree.links.new(albedo.outputs["Alpha"], clip.inputs[0])
            tree.links.new(clip.outputs["Value"], socket)
            wired.append(material.name)
        elif material.name in textured:
            for link in list(socket.links):
                tree.links.remove(link)
            socket.default_value = ALPHA_OPAQUE
    return sorted(wired)


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
            "alpha_mode": "OPAQUE",
            "alpha_cutoff": ALPHA_CUTOFF,
            "cutout_texels": 0,
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

        triangles_out, decimate_passes, decimate_repairs = _decimate(meshes, budget)
        report["triangles_out"] = triangles_out
        report["stages"]["decimate"] = budget
        # {part: polygons _validate_meshes removed}. An entry can be 0 when
        # the only repair was to custom data (see _validate_meshes'
        # docstring) -- the key existing does not by itself mean geometry was
        # lost. Reported rather than merely fixed: this is the pass silently
        # losing geometry it asked for, and an operator comparing
        # triangles_in to triangles_out deserves to see where the shortfall
        # came from.
        report["stages"]["decimate_validation"] = decimate_repairs

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
        report["stages"]["pixel_semantics"] = _verify_pixel_semantics()
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

        neutralized, restore_plan = _neutralize_pbr_for_bake(meshes)
        report["stages"]["bake_neutralized"] = neutralized
        baked = _bake_target(meshes, size)
        _bake(meshes)
        if _bake_wrote_nothing(baked):
            raise ValueError(
                "bake produced an entirely black image: Cycles found no "
                "active and selected image texture node, so nothing was "
                "written. Quantizing this would yield a flat texture that "
                "passes palette conformance while carrying no detail."
            )
        # The cutout mask, baked SECOND and into its own image. Cycles has no
        # alpha pass, and the source base colour image the mask lives in is
        # about to be deleted by _drop_foreign_textures, so this is the only
        # window in which the mask can be captured at all. Skipped entirely
        # when no material's Alpha socket was linked in the source: that is
        # the common case (every solid asset in the pack) and it costs a
        # whole second Cycles bake.
        textured_alpha = _alpha_sources(restore_plan)
        cut = None
        cut_per_material = {}
        if textured_alpha:
            alpha_baked = _bake_alpha(meshes, size, textured_alpha)
            cut = _cut_mask(alpha_baked)
            cut_per_material = _cut_texels_per_material(meshes, cut, size)
            bpy.data.images.remove(alpha_baked)
        # A material is only declared MASK if its OWN atlas region actually
        # loses texels. A source can carry an alpha map that turns out to be
        # solid, and declaring MASK on it would hand an engine a licence to
        # discard geometry for no reason.
        cutout_materials = {
            name for name, texels in cut_per_material.items() if texels > 0
        }
        png_bytes, palette_colours, distinct = _quantize_to_png(
            baked, Path(payload["palette"]), cut if cutout_materials else None
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
            "alpha_mode": "MASK" if cutout_materials else "OPAQUE",
            "alpha_cutoff": ALPHA_CUTOFF,
            # Texels of the EXPORTED atlas that are cut. Counted from the
            # mask, so it matches the PNG exactly; it is therefore larger
            # than the per-material figures below, which are attributed by
            # rasterizing UV triangles and so miss the BAKE_MARGIN_TEXELS of
            # bleed the bake writes around every island.
            "cutout_texels": int(cut.sum()) if cutout_materials else 0,
        }
        # Per-material, because alphaMode is a per-material declaration and
        # "the atlas has holes in it" is not the same question as "which part
        # they belong to". A source that declared an alpha map and scored 0
        # here is visible rather than silently downgraded to opaque.
        report["stages"]["alpha_sources"] = sorted(textured_alpha)
        report["stages"]["cutout_texels_per_material"] = cut_per_material

        # Undo the bake-only mutations BEFORE export, and before
        # _drop_foreign_textures removes the nodes their links point at.
        # Without this the asset ships with alpha forced to 1.0.
        report["stages"]["shading_factors"] = _restore_pbr_after_bake(
            meshes, restore_plan, contract["drop_maps"]
        )

        report["dropped_maps"] = _strip_maps(meshes, contract["drop_maps"])
        # After stripping the contract's named maps, remove any image node
        # that is still not the baked albedo, so the export cannot carry a
        # second, unquantized texture regardless of what the source had.
        report["stages"]["foreign_textures_removed"] = _drop_foreign_textures(meshes)
        # Wired LAST, after the source image nodes are gone, so nothing else
        # can be left holding the Alpha socket. A mask in the texture that no
        # material declares is invisible: glTF's default alphaMode is OPAQUE.
        report["stages"]["cutout_materials"] = _wire_cutout(
            meshes, cutout_materials, set(textured_alpha)
        )
        # The style contract validates a vertex_light_bake flag, but this
        # plan does not implement vertex-colour lighting. Reported as False
        # so no downstream stage can assume it took effect.
        report["vertex_light_bake"] = False

        # Last word before the export call, and the only guarantee that what
        # ships is what was measured. _split_by_material and _decimate are
        # both fixed at source, so the expected result here is an EMPTY dict;
        # a non-empty one means some stage after them started corrupting
        # geometry, and it is reported rather than swallowed.
        #
        # triangles_out is recomputed when it is not empty, because
        # mesh.validate() DELETES degenerate geometry. Leaving the earlier
        # count in place would hand Gate 2 (Task 9) a silhouette IoU measured
        # against a triangle count the exported file does not have. The
        # budget needs no re-check: validation only ever removes geometry, so
        # a count that was under budget stays under it.
        export_repairs = _validate_meshes(meshes)
        report["stages"]["export_validation"] = export_repairs
        if export_repairs:
            report["triangles_out"] = _triangle_count(meshes)

        bpy.ops.object.select_all(action="SELECT")
        bpy.ops.export_scene.gltf(
            filepath=payload["output"],
            export_format="GLB",
            use_selection=True,
            export_apply=True,
            # export_yup=False ALWAYS, and that is not a bug -- it is the
            # counterpart of the manual rotation in _normalize.
            #
            # The exporter's export_yup=True performs its OWN Z-up-to-Y-up
            # conversion on the whole scene, unconditionally, independent of
            # any rotation already sitting on the objects. _normalize has
            # already put the scene into the contract's declared frame (it
            # rotates every top-level mesh -90deg about X for up_axis == "Y"),
            # because the grid snapping, the bounds and the origin it reports
            # are all measured in that frame. Asking the exporter to convert
            # on top of that applied the conversion TWICE and shipped every
            # up_axis == "Y" asset rotated ~180deg about X from the
            # artist-authored orientation -- silent, and visible to any
            # spec-compliant glTF consumer. Measured on a probe box with
            # Blender dims (1, 2, 4): manual rotation + export_yup=True
            # exports dims (1, 2, 4), where a correct Y-up glTF is (1, 4, 2).
            #
            # The rotation is not baked into the vertex data -- export_apply
            # applies MODIFIERS, not object transforms -- it lives in each
            # exported node's TRS quaternion. With export_yup=False that
            # quaternion is _normalize's single -90deg-about-X conversion and
            # nothing else: every exported node carries
            # rotation: [-0.7071, 0, 0, 0.7071], which is now the correct
            # single conversion rather than one of two compounding ones. So
            # the scene is written out verbatim, and the frame the report
            # describes is exactly the frame the GLB carries.
            export_yup=False,
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
