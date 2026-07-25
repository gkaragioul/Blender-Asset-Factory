"""Isolated probe for Finding A: a skipped alpha-bake material must not let
Cycles overwrite the finished colour atlas.

_bake_alpha (factory/scripts/retro_pass.py) iterates every material reachable
from the export and, for each one, swaps its surface for an Emission node
driven by the cutout mask and points a NEW image-texture node at the alpha
image. Before that node exists, whatever node _bake_target left active in
that material's tree is still `RetroBakeTarget`, pointing at the finished
colour atlas. If _bake_alpha skips a material (which it used to do whenever
the material had no Material Output node) without first installing its own
target, that stale active node stays live and the EMIT bake below overwrites
the colour atlas instead of the alpha image, because `_prepare_bake` bakes
with `use_clear=True`.

This script builds the smallest scene that can prove that either way: two
one-quad planes sharing one image as their colour atlas, each in its own half
of UV space, with distinct baked colours. PartB's material has a node tree
but no Material Output node -- the skip case. PartA's material carries a
linked (not just scalar) Alpha source, so the alpha bake has real work to do
alongside the skip case, not just the degenerate all-skipped scenario.

It calls retro_pass's own `_bake_target` and `_bake_alpha` directly (loaded
by file path, since factory/scripts is not a package) rather than running
the full pipeline, because reaching a material with no Material Output node
through a real import is not practical -- every real glTF/FBX importer
manufactures one.

Invoked exactly like retro_pass.py's own contract, via run_blender_script:
    blender --background --factory-startup --python alpha_bake_skip_probe.py \
        -- --payload payload.json --report report.json
The payload is unused; it exists only so run_blender_script's generic
--payload/--report calling convention is satisfied.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import bmesh
import bpy

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(_REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPOSITORY_ROOT))

_RETRO_PASS_PATH = _REPOSITORY_ROOT / "factory" / "scripts" / "retro_pass.py"
_spec = importlib.util.spec_from_file_location("retro_pass_probe", _RETRO_PASS_PATH)
retro_pass = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(retro_pass)


def _arguments() -> tuple[Path, Path]:
    argv = sys.argv[sys.argv.index("--") + 1 :]
    payload = Path(argv[argv.index("--payload") + 1])
    report = Path(argv[argv.index("--report") + 1])
    return payload, report


def _plane(name: str, material, u0: float, u1: float):
    mesh = bpy.data.meshes.new(name)
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)

    bm = bmesh.new()
    verts = [
        bm.verts.new((0.0, 0.0, 0.0)),
        bm.verts.new((1.0, 0.0, 0.0)),
        bm.verts.new((1.0, 1.0, 0.0)),
        bm.verts.new((0.0, 1.0, 0.0)),
    ]
    face = bm.faces.new(verts)
    bm.faces.ensure_lookup_table()
    uv_layer = bm.loops.layers.uv.new("UVMap")
    uvs = [(u0, 0.0), (u1, 0.0), (u1, 1.0), (u0, 1.0)]
    for loop, uv in zip(face.loops, uvs):
        loop[uv_layer].uv = uv
    bm.to_mesh(mesh)
    bm.free()

    obj.data.materials.append(material)
    return obj


def _material(name: str, colour: tuple[float, float, float]):
    material = bpy.data.materials.new(name)
    if material.node_tree is None:
        material.use_nodes = True
    tree = material.node_tree
    for node in list(tree.nodes):
        tree.nodes.remove(node)
    output = tree.nodes.new("ShaderNodeOutputMaterial")
    emission = tree.nodes.new("ShaderNodeEmission")
    emission.inputs["Color"].default_value = (*colour, 1.0)
    tree.links.new(emission.outputs["Emission"], output.inputs["Surface"])
    return material, tree, output


def _distinct_rgb(pixels: list[float]) -> int:
    return len({tuple(round(value, 3) for value in pixels[i : i + 3]) for i in range(0, len(pixels), 4)})


def main() -> int:
    _payload_path, report_path = _arguments()
    report = {"ok": False, "error": None}
    try:
        retro_pass._clear_scene()
        for obj in list(bpy.data.objects):
            bpy.data.objects.remove(obj, do_unlink=True)

        mat_a, tree_a, _output_a = _material("MatA", (0.8, 0.1, 0.1))
        mat_b, tree_b, output_b = _material("MatB", (0.1, 0.8, 0.1))
        # The skip case Finding A is about: a node tree with everything a
        # real material has, except the Material Output node _output_node
        # looks for.
        tree_b.nodes.remove(output_b)
        report["mat_b_has_output"] = retro_pass._output_node(tree_b) is not None

        obj_a = _plane("PartA", mat_a, 0.0, 0.5)
        obj_b = _plane("PartB", mat_b, 0.5, 1.0)
        meshes = [obj_a, obj_b]

        size = 32
        baked = retro_pass._bake_target(meshes, size)
        retro_pass._prepare_bake(meshes)
        bpy.ops.object.bake(type="EMIT", use_selected_to_active=False)
        # `baked` now stands in for a completed, real colour bake: PartA and
        # PartB's own distinct emission colours, each in its own UV half.

        before = list(baked.pixels[:])
        report["before_distinct_rgb"] = _distinct_rgb(before)

        # MatA carries a LINKED Alpha source (not just a scalar), so the
        # alpha bake has genuine work to do alongside the MatB skip case.
        value_node = tree_a.nodes.new("ShaderNodeValue")
        value_node.outputs[0].default_value = 0.0
        sources = {"MatA": value_node.outputs[0]}

        retro_pass._bake_alpha(meshes, size, sources)

        after = list(baked.pixels[:])
        report["after_distinct_rgb"] = _distinct_rgb(after)
        report["pixels_unchanged"] = before == after
        report["ok"] = True
    except Exception as error:  # noqa: BLE001 -- reported, never swallowed
        report["error"] = f"{type(error).__name__}: {error}"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
