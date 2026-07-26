# PS1 Pipeline Follow-ups and Launch Blockers

Date: 2026-07-26
Status: Open items carried out of the PS1 retro pipeline core plan

Everything here was found during implementation, adjudicated, and deliberately
deferred. Nothing in this list blocks the merged pipeline from running; several
items block shipping a paid pack. Ordered by consequence.

## Launch blockers for `ww2_diorama_kit_01`

### 1. Texture-driven alpha cutout does not survive the bake

`_quantize_to_png` forces the atlas opaque and `_drop_foreign_textures` removes
the node carrying a cutout mask, so an asset whose SHAPE depends on a cutout
converts to a solid slab. Neither gate catches it: Gate 1 checks palette
membership and triangle budget, Gate 2 compares silhouettes of the same
geometry before and after.

Blocks `barbed_wire_coil` (#6) and plausibly `barbed_wire_post` (#7). Also
blocks any future pack containing foliage, chain-link, fences or windows —
which is most of a farm or village kit. Scalar material alpha now survives;
texture-channel alpha does not.

### 2. The `m1897-trenchgun` fixture's licence provenance is unverified

Third-party download dated 2025-02-01. Approved as a TEST FIXTURE ONLY. Before
`m1897_trench_gun` ships, either verify the source licence permits
redistribution or regenerate the asset through lane B. Unverifiable asset
provenance is a store-threatening risk.

### 3. Gate 1 can falsely reject an asset with a solid alpha map

`gates.py` fails when `stages.alpha_sources` is non-empty and
`texture.alpha_mode != "MASK"`. But `alpha_sources` counts every material with
a LINKED Alpha socket, while `MASK` is set only when the baked mask actually
loses texels — and `retro_pass` explicitly documents keeping such an asset
OPAQUE as correct, because declaring MASK would hand an engine a licence to
discard geometry for no reason.

Fix: gate on `stages.cutout_texels_per_material` being all-zero instead. Add
the missing control test (declared alpha source, genuinely solid mask, must
pass). Causes false rejects, which are loud and recoverable — hence a
follow-up rather than a blocker, but it is the most likely of these to bite.

## Coverage gaps that let a real defect through

### 4. No test drives `build_pack(validate=True)`

Every `build_pack` call in the suite passes `validate=False` and the CLI test
uses `--skip-validate`, so a regression back to a hardcoded `preview_ok=True`
— the exact defect the final fix wave repaired — would be caught by nothing.
A ~10-line test patching `factory.pack.preview_glb` to raise closes it. This is
the highest-value item in this document: it is the shape of the original bug.

### 5. `MIN_DISTINCT_COLOURS = 3` does not close the flat-colour escape

The original failure was seven parts each baking to a different flat base
colour, which scores ~7 distinct colours. No global colour-count threshold can
separate that from seven well-used palette entries. A per-part regional colour
count would. Live margin is also thinner than the constant's comment suggests:
palette 4, distinct 4, floor 3.

### 6. The placement gate is largely self-certifying

It checks re-measured bounds rather than a snapped value against a snap, so it
is not vacuous — but `_normalize` sets `offset[up] = -minimum[up]` and
`offset[h] = snap(centre) - centre` immediately before, so those bounds are
grounded and aligned by construction. The only production defect that can fire
it is an offset missing some meshes (the `if obj.parent is None` guard). It is
taken PRE-decimation, so it does not describe the shipped GLB, and it would NOT
have caught the Y-up rotation defect its own docstring cites.

The shipped GLB's accessor `min`/`max` are the independent source if this is
ever tightened. "Grid and pivot conformance is policed" is currently a stronger
claim than what ships.

### 7. `stages.source_maps_ambiguous` is computed but never written

`_resolve_source_maps` returns it and `main()` drops it, so an operator cannot
distinguish a REFUSED texture from a NOT-FOUND one. One line. The ambiguity
branch also has no test coverage.

## Structural

### 8. The gates cannot see the product

Gate 1 is composed entirely of upper bounds and membership tests; Gate 2 is a
relative measure between an asset and itself. An upper bound is satisfied by
zero, a membership test by a constant, and a relative measure is invariant to
a defect present on both sides. The final fix wave added lower bounds, which
closes the known instances — but neither gate ever looks at the SOURCE, and
neither can see pack-level coherence, which is the actual product.

The spec already knew this: Gate 3 (independent vision judge) and Gate 4 (human
batch approval over one contact sheet) are the gates that judge what is being
sold, and neither is in the merged pipeline. Style drift is invisible per asset
and only observable in aggregate. **The contact sheet is not later polish; it
is the only gate that sees the product.** Do not ship a paid pack on Gates 1
and 2 alone.

### 9. Standing rule adopted during this work

**No automated check lands without a companion test proving it FAILS on the
trivially-conforming input.** Five separate blind checks were found by hand
during implementation, always the same way, and every time the proof came from
deliberately neutering the check and watching what stayed green. Mandating that
step is what stops instance six.

### 10. The suite interferes with itself

Parallel runs share the extracted fixture and temp state under
`tmp/factory/tests/`, which produced spurious determinism failures three times
before the real cause was found. Per-run fixture copies or a lock are needed
before this runs in CI. Determinism must also be tested UNDER LOAD, not only on
an idle machine — the original defect was a wall-clock-time-bounded UV packing
call that only diverged when the machine was busy.

## Smaller, batched

- `bool` subclasses `int`, so `true` passes positive-integer validation for
  polycount bands, `max_generations` and `max_rerolls`. One shared helper.
- Malformed input raises raw `TypeError`/`AttributeError` rather than
  `CatalogError`/`StyleContractError` in several loaders; `_glb_parts` raises
  uncaught on a malformed JSON chunk.
- `report["parts"]` is captured before floater removal, so it can name parts
  absent from the export. Reported bounds are likewise taken before
  `_validate_meshes` deletes geometry.
- `_drop_foreign_textures` does not recurse into `ShaderNodeGroup` trees, so a
  texture nested in a node group still leaks. The "complete by construction"
  claim in its docstring overstates what is closed.
- `effective_radius` returns the render's own radius, never the override, so
  chained renders silently lose the shared framing guarantee.
- Render targets are appended to the report without checking the file exists.
- The palette conformance loop breaks on the first bad image, discarding
  evidence about later ones.
- `up_axis: "Z"` is permitted by the contract but now exports a
  spec-noncompliant Z-up GLB and is untested. Cheapest correct action is to
  REJECT `"Z"` in `StyleContract.load` and delete the dead branch.
- `tests/test_cli.py` does not enumerate registered commands.
- Several test modules bypass `tests/temp_paths.temporary_root()` while using
  the same location, and `test_temp_directory_policy` greps a literal string so
  it cannot see them.
- Blender scripts write reports with `write_text`, not atomically.

## Environment note

`validate=True` pack runs now require Chrome or Edge plus the pinned Three.js
runtime, because Gate 1's preview criterion is really exercised. A viewer
failure rejects the asset loudly with `preview_error` recorded.
`--skip-validate` is unaffected.
