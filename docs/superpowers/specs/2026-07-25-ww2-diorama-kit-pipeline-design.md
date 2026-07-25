# WW2 Diorama Kit Pipeline Design

Date: 2026-07-25
Status: Approved design awaiting written-spec review

## Objective

Build the production pipeline that generates commercially sellable, PS1-era,
Three.js-ready GLB asset packs, and use it to ship `ww2_diorama_kit_01`
(30 assets). Assets are premade and finished: the buyer imports a GLB and
uses it directly.

The pipeline sources geometry from a hosted image-to-3D service, applies a
deterministic PS1 conversion in headless Blender, gates the result against
measured quality criteria, and packages an approved pack for sale.

The storefront is a separate project with its own spec, written immediately
after this one. Nothing in this spec depends on it.

## Environment Constraints

These constraints were verified on 2026-07-25 and they determine the
architecture.

- The workstation GPU is an **AMD Radeon RX 7900 XTX**. There is no CUDA and
  no `nvidia-smi`. Every local generator ranked in
  `docs/research/AI_3D_MODEL_SHORTLIST_2026-07-22.md` (Pixal3D, TRELLIS.2,
  TripoSG, PartCrafter, Stable Fast 3D, SPAR3D) requires NVIDIA CUDA and
  therefore **cannot run on this machine**. Local image-to-3D is not an
  option; hosted generation is mandatory, not preferred.
- The repository was authored on Linux. `factory/config.json` hardcodes
  `/usr/bin/blender`, `/snap/bin/blender`, `/usr/local/bin/blender`, and every
  `working_directory` in `knowledge/*.json` records a `/media/<user>/...`
  path. The factory cannot currently run on this Windows host.
- `doctor` reports `comfyui: unavailable`, so local concept generation is also
  hosted-only. The existing `factory/providers/bfl.py` (hosted FLUX) is the
  working concept path.
- Available and verified: `blender`, `node`, `python`, `three`,
  `threejs_viewer`, `gltf_validator`, `gltfpack`, `playwright_core`,
  `browser`.

## Provider Decision

**Sloyd is the primary geometry provider**, on a paid tier.

Evidence from the 2026-07-25 evaluation generation (`Text to 3D`,
`Game Dev: High Poly`, no style preset, 40k polycount, Auto topology,
2K texture, prompt
`pump action trench shotgun wooden stock short barrel perforated heat shield bayonet lug`):

- Geometry quality is sufficient. Clean silhouette, no floating fragments, no
  melted forms, readable part separation between forend, barrel, receiver, and
  stock. Believable proportions.
- **The output was not historically accurate.** Sloyd named it "Combat
  Shotgun" and produced a modern Mossberg-like silhouette with a ventilated
  top rib, not the Winchester M1897 the prompt described. Sloyd's text-to-3D
  has no reliable historical priors.

This single finding produces the two-lane routing in the architecture below.

The paid tier is required for three independent reasons: marketplace
redistribution rights, API access for batch runs, and the `Split to Parts`
feature (Pro) which provides the semantic part separation
`docs/IDEAL_AI_GAME_ASSET_PIPELINE.md` requires before reduction.

Cost: approximately $0.015 per model, unlimited generations on the paid plan.

### Providers rejected, and why

- **Hunyuan3D 2.1** — the Tencent Community License excludes the EU, the UK,
  and South Korea. Fatal for a worldwide store regardless of quality.
- **MeshAnything V2** — the source repository is S-Lab non-commercial while
  the Hugging Face model card says MIT. Commercial use is uncleared.
- **All free tiers** — Sloyd free forbids download; Meshy free outputs are
  CC BY 4.0; Tripo free forbids commercial use. No free tier yields a
  sellable asset, and none provides a batch API.
- **Hugging Face Spaces** (TripoSG, Stable Fast 3D, TRELLIS) — genuinely
  viable for one-off fixtures: MIT licensed, downloadable, and they run on
  Hugging Face GPUs, which sidesteps the local CUDA problem. Rejected as the
  production path only because ZeroGPU quotas, queue waits, and the absence of
  a batch API make a scheduled 30-asset run impossible.

Tripo (approximately $0.21 per textured model, ~8s generation) remains the
designated second tournament entrant, deferred until one provider works
end to end.

## Architecture

A **pack** is the unit of work. One declarative catalog file describes the
whole kit. The pipeline runs it unattended and produces a single contact sheet
for batch approval.

```
catalog/ww2_diorama_kit_01.json
        |
        +-- lane A (generic props) ------------+
        |     prompt -> Sloyd text-to-3D      |
        |                                     |
        +-- lane B (period-specific) ---------+
              brief -> FLUX concept ->        |
              Sloyd image-to-3D               |
                                              v
                                   raw/  (immutable, write-once)
                                              |
                                    +---------+---------+
                                    |   PS1 pass        |  x N candidates
                                    +---------+---------+
                                              v
                            optimize -> validate -> preview render
                                              v
                                      contact-sheet.png
                                              v
                                   [ batch approval gate ]
                                              v
                          rejects re-roll        approved -> pack zip
```

### The two lanes

**Lane A — generic props.** Crates, barrels, jerrycans, sandbags, fences,
tank traps, drums, tents, duckboards. A buyer holds no strong prior for what
a correct sandbag looks like, so a text prompt is sufficient. One API call
per candidate. 26 of 30 assets.

**Lane B — period-specific.** Weapons, signage, helmets, radios: anything a
WW2 buyer would recognise as wrong. Requires a controlled reference image.
`factory/providers/bfl.py` generates the concept; Sloyd Image-to-3D converts
it. 4 of 30 assets.

The lane is a routing field on the catalog entry. Everything downstream of
`raw/` is identical for both lanes.

### Three artifact tiers

| Tier | Contents | Rule |
|---|---|---|
| `raw/` | Generator output exactly as received, provider metadata, dated licence snapshot | Write-once. Never mutated, never shipped. All later work re-derives from here. |
| `work/` | PS1 candidates, bakes, validation reports, preview renders | Disposable, rebuildable from `raw/`. |
| `dist/` | Approved GLBs and the pack zip | Reachable only through the approval gate. |

`raw/` is write-once because Sloyd cannot regenerate an output identically.
Losing a raw file means losing that geometry permanently.

## Components

Each unit has one purpose and a defined interface.

### `factory/catalog.py` (new)

Loads and validates a pack catalog: the asset list, and per asset its `id`,
`lane`, `prompt` or `reference_brief`, and `role`. Schema in
`factory/schemas/catalog.schema.json`. Pure data in, validated structure out.

The catalog declares `role` (`small`, `medium`, `large`) and never a triangle
count. The triangle budget is resolved by looking `role` up in the style
contract's `polycount_bands`, so a whole pack can be re-budgeted by editing one
contract value. The "Tri budget" column in the pack contents below shows the
resolved value for this pack's contract, not a per-asset catalog field.

### `factory/style_contract.py` (new)

Loads and validates the per-pack style contract. All style decisions live
here and nowhere else.

```json
{
  "palette": "palettes/ww2_field_48.png",
  "texture_size": 256,
  "filtering": "nearest",
  "polycount_bands": { "small": 400, "medium": 1000, "large": 2500 },
  "grid_unit": 0.5,
  "up_axis": "Y",
  "drop_maps": ["normal", "roughness", "metallic"],
  "vertex_light_bake": true
}
```

### `factory/providers/sloyd.py` (new)

Mirrors the existing `bfl.py` structure, including its injected transport
seams:

```python
JsonTransport = Callable[[str, str, dict, dict | None], dict]
DownloadTransport = Callable[[str, Path], None]
```

Every provider test therefore runs against a fake transport with no network
access and no credit spend. Exposes text-to-3D and image-to-3D, passes
polycount, topology and texture resolution, requests `Split to Parts` where
the catalog asks for it, and writes the raw GLB plus a metadata and licence
record into `raw/`.

### `factory/retro.py` (new) — the PS1 pass

The core new behaviour, and a pure function:

```
retro_pass(raw_asset, style_contract, role) -> ps1_glb
```

Identical inputs must produce a byte-identical GLB. Stages, in order:

1. **Part-aware split.** Use semantic names where present. The
   `trenchgun.fbx` fixture already ships `Barrel`, `Receiver`,
   `ReceiverInternals`, `Stock`, `BarrelAttachment`, `Cartridge`; Sloyd
   `Split to Parts` provides the equivalent. Splitting precedes reduction so
   decimation cannot weld separate mechanical parts together.
2. **Cleanup.** Remove sub-threshold floating fragments and hidden interior
   shells, repair normals and non-manifold edges, preserve hard edges at
   mechanical interfaces.
3. **Normalize.** Consistent up-axis, real-world scale, origin at the base
   for props and at the grip for handhelds, footprint snapped to `grid_unit`.
   This is what makes 30 assets usable together without manual fixing, and it
   is a primary quality claim of the pack.
4. **Decimate to band.** Driven by the asset's `role`, from the contract's
   `polycount_bands`. Never a per-asset judgment.
5. **UVs.** Retain generator UVs when they pass texel-density and overlap
   checks; otherwise re-unwrap with xatlas.
6. **Bake and quantize.** Generator albedo down to `texture_size`, then
   quantized to the shared pack palette. A single palette across all 30
   assets is the strongest available coherence mechanism.
7. **Strip PBR.** Delete every map in `drop_maps`. PS1 hardware had none of
   them and removing them substantially reduces file size. Optionally bake
   ambient occlusion and lighting to vertex colours.
8. **Export** GLB, then hand off to the existing backend.

Two deliberate exclusions:

- **No baked-in vertex jitter or affine texture warping.** The characteristic
  PS1 wobble is a runtime shader effect and belongs under the buyer's control.
  Baking it into geometry ships permanently distorted meshes. The shader is
  distributed alongside the pack as a bonus, not applied to the assets.
- **No normal-map baking.** `docs/IDEAL_AI_GAME_ASSET_PIPELINE.md` specifies a
  full high-to-low PBR bake. That is correct for a realistic pack and wasted
  work for this one. Skipping it is a large part of why this pack is fast to
  produce.

### `factory/pack.py` (new)

Orchestrates a pack run: catalog -> per-asset generation (cache-aware) ->
PS1 pass over N candidates -> gates -> contact sheet -> approval state ->
release. Enforces the spend cap and the re-roll limit. A single asset failing
must never abort the run.

### `factory/provenance.py` (new)

Appends one ledger row per asset: provider, model version, prompt or
reference hash, generation date, plan tier, and the archived licence terms in
force at that moment. Ships with the pack.

### Reused unchanged

`optimizer.py` (gltfpack), `gltf_validation.py` (Khronos validator),
`runtime_preview.py` (pinned Three.js viewer), `contact_sheet.py`,
`release.py` (transactional publication), `state.py`, `learning.py`,
`doctor.py`, `transfer.py`.

## Quality Gates

Four gates in increasing order of cost. The generator never grades its own
output. This directly addresses the recorded v1 failure: "the same agent that
created the object declared it good, and the scores were constants written
into manifests rather than measurements from an independent evaluator."

### Gate 1 — Deterministic measurements

No model involvement, pure pass/fail:

- Triangle count within the role's band.
- Khronos glTF Validator clean.
- Loads in the pinned Three.js viewer.
- Texture is exactly `texture_size`, nearest filtering, no maps listed in
  `drop_maps` present.
- **Palette conformance:** every albedo pixel is a member of the pack palette.
  Catches style drift mechanically.
- **Grid and pivot conformance:** the base is grounded on the contract's up
  axis and the horizontal footprint centre snaps to `grid_unit`, both checked
  against `retro_pass`'s reported bounds. Gate 2 is structurally blind to this
  — see below.
- **Lower bounds** (every part owns atlas texels; the shipped texture carries
  a minimum number of distinct colours; the atlas covers a minimum fraction;
  declared alpha sources imply `alphaMode: MASK`). See "The structural limit
  of automated gating" below for why these are not optional extras.
- File size within budget.

A Gate 1 failure is a pipeline bug, not a taste question. It never reaches
the user.

### Gate 2 — Silhouette IoU: a catastrophe floor plus comparative ranking

Render the raw asset from 8 fixed views. Render the PS1 asset from the same 8
views. Compute silhouette intersection-over-union.

- **Comparative ranking is the primary mechanism.** `rank_candidates` orders
  the N candidates for one asset against each other and takes the winner. This
  is what the "tournament" language elsewhere in this spec always implied, and
  it needs no invented constant.
- **`GATE2_CATASTROPHE = 0.45` is an absolute floor, and nothing more.** Below
  it the conversion has failed outright; above it, IoU does not rank quality.

This section previously specified `IoU >= 0.95` pass, `0.90` flag, `< 0.90`
reject. **Those numbers were invented, never measured, and are unreachable by
construction at PS1 triangle budgets.** Left in place, Gate 2 would have
rejected every asset the pipeline can produce. What the measurements showed:

- A real, correct conversion of the trenchgun fixture — 45,881 triangles down
  to 2,470, an 18.6x reduction — scores minimum IoU **0.613** (mean 0.637),
  with a per-view spread of 0.57–0.62. That is uniform boundary erosion, not a
  collapsed shape.
- Re-rendering the same pair at 4x resolution (256 → 1024) **LOWERED** the
  score to minimum 0.5735 / mean 0.595. That rules out pixel quantization on a
  thin object: more resolution resolves finer boundary detail the decimated
  mesh genuinely lacks. **0.61 is real, unavoidable shape loss from an 18.6x
  reduction, not a measurement artefact.**
- The Y-up double-rotation defect — a genuinely catastrophic failure, the
  asset standing on its muzzle — scored **0.03**.

0.03 against 0.613 is ample separation for the question this gate can actually
answer. Only fine discrimination near 0.95 was fantasy. Comparing a PS1 asset
to its own high-poly ancestor measures how much was decimated, which the
triangle counts already report.

Consequently there is no `flag` verdict: `gate2` and `verdict` emit only
`pass` or `reject`.

### The structural limit of automated gating

Recorded here because it is a limit of this design, not a code defect, and it
has been rediscovered five times.

**Gate 1 is composed entirely of upper bounds and set-membership tests, and
Gate 2 is a relative measure between an asset and itself.** An upper bound
(`triangles <= budget`) is satisfied by zero. A membership test (every texel is
in the palette) is satisfied by a constant — one colour is trivially a subset
of any palette. A relative measure is invariant to any defect present on both
sides of the comparison. So a DEGENERATE asset satisfies all three families
trivially, and there is no fourth family of check to add.

The five escapes, all one defect:

1. A black texture (relink failure; Cycles evaluates unresolvable images as
   black) passes palette conformance perfectly.
2. Flat per-part base colours pass a "texture carries detail" check.
3. A solid slab replacing an alpha cutout passes both gates — Gate 1 checks
   palette and budget, Gate 2 compares silhouettes of the *same* geometry
   before and after conversion.
4. A wiped UV atlas passes conformance, again because one colour is trivially
   in any palette.
5. A per-material black bake passes an *aggregate* "the bake wrote something"
   check, because healthy materials outvote the dead one.

Gate 2 in particular structurally cannot detect that the source was already
wrong, and — because it frames each render on its own bounding box, which is
deliberate and makes the comparison translation-invariant — it is also blind
to pivot and grounding regressions.

**The mitigation is LOWER bounds in Gate 1, sourced from `retro_pass`'s own
report**, which the orchestrator previously discarded: a minimum atlas-texel
count per part, a minimum distinct-colour count measured from the shipped PNG,
a minimum atlas coverage fraction, and `alpha_sources` implying
`alphaMode: MASK`. Grid and pivot conformance is likewise policed from the
reported bounds, since Gate 2 cannot see it.

This mitigates rather than closes the gap. Every check added must ship with a
test proving it FAILS on the trivially-conforming input; a check without a
proof-of-failure test is how all five blind spots happened.

### Gate 3 — Independent vision judge

Used for lane B and for ranking the N candidates per asset. Scores each
render against the reference image and the style contract.

Two hard constraints:

- It runs as a separate call with no knowledge of which prompt or seed
  produced which candidate. No self-grading.
- **It ranks and flags; it never approves.** It orders candidates and
  annotates the sheet. It cannot promote anything into `dist/`.

### Gate 4 — Human batch approval

One `contact-sheet.png` for the whole pack. Per asset: raw render, PS1
render, triangle count, silhouette IoU, judge score. The user marks approve or
reject; each reject carries a reason code (`silhouette`, `wrong_subject`,
`style_drift`, `topology`) that determines how it re-rolls: a higher poly
band, a corrected prompt, or a switch to lane B.

Approval state persists. A re-run touches only rejects; approved work is never
re-approved.

Batch approval is not merely a throughput concession. **Style drift is
invisible per asset** and only observable in aggregate: any single crate looks
fine, while 30 individually-fine assets can still be an incoherent kit.
Coherence is what the pack sells, so the contact sheet is the only view in
which the actual product quality can be judged at all.

## Pack 1 Contents: `ww2_diorama_kit_01`

30 assets. 26 lane A, 4 lane B.

**Fortification (7)**

| # | Asset | Lane | Tri budget |
|---|---|---|---|
| 1 | `sandbag_single` | A | 400 |
| 2 | `sandbag_wall` | A | 1000 |
| 3 | `sandbag_corner` | A | 1000 |
| 4 | `czech_hedgehog` | A | 400 |
| 5 | `dragons_teeth` | A | 400 |
| 6 | `barbed_wire_coil` | A | 1000 |
| 7 | `barbed_wire_post` | A | 400 |

**Logistics (9)**

| # | Asset | Lane | Tri budget |
|---|---|---|---|
| 8 | `ammo_crate_closed` | A | 400 |
| 9 | `ammo_crate_open` | A | 400 |
| 10 | `supply_crate` | A | 400 |
| 11 | `metal_ammo_box` | A | 400 |
| 12 | `oil_drum_upright` | A | 400 |
| 13 | `oil_drum_tipped` | A | 400 |
| 14 | `jerrycan` | A | 400 |
| 15 | `sack_pile` | A | 400 |
| 16 | `wooden_pallet` | A | 400 |

**Trench and structure (8)**

| # | Asset | Lane | Tri budget |
|---|---|---|---|
| 17 | `duckboard_section` | A | 400 |
| 18 | `trench_ladder` | A | 400 |
| 19 | `corrugated_sheet` | A | 400 |
| 20 | `bunker_entrance` | A | 2500 |
| 21 | `ruined_brick_wall` | A | 1000 |
| 22 | `ruined_corner` | A | 1000 |
| 23 | `rubble_pile` | A | 1000 |
| 24 | `telegraph_pole` | A | 400 |

**Camp (2)**

| # | Asset | Lane | Tri budget |
|---|---|---|---|
| 25 | `field_tent` | A | 1000 |
| 26 | `field_stove` | A | 400 |

**Period-specific, lane B (4)**

| # | Asset | Lane | Tri budget |
|---|---|---|---|
| 27 | `signpost` | B | 400 |
| 28 | `m1897_trench_gun` | B | 2500 |
| 29 | `stahlhelm` | B | 1000 |
| 30 | `field_radio` | B | 1000 |

`signpost` is lane B because it carries readable German or English lettering,
and text is the failure mode generators are least reliable at. It requires a
controlled reference image.

The paired variants (crate open and closed, drum upright and tipped, wall and
corner) are near-free: the same generation with a small edit. They are what
makes the kit feel complete rather than sparse.

Expected volume: approximately 90 generations (30 assets x 3 candidates) plus
4 FLUX reference images. Flat cost on Sloyd's unlimited paid tier,
approximately $8-15 for the pack.

Expected pack size: 30 assets at or under 2500 triangles with 256px palette
textures compresses to roughly 1-2 MB for the entire pack. For a Three.js
buyer managing page-load budgets this is a headline feature and belongs in the
store listing.

### Pack deliverables

- 30 finished GLB files, meshopt-compressed via the already-installed
  `gltfpack`, each with an uncompressed fallback for browser compatibility.
  Draco is not used: the toolchain in `.tooling/` provides gltfpack, and
  mixing both compressors is the blind-serial-optimization mistake that
  `docs/IDEAL_AI_GAME_ASSET_PIPELINE.md` warns against.
- 30 preview PNGs for store listings.
- A licence file and the provenance ledger.
- A pre-assembled demo scene: the approved assets arranged as a trench
  diorama and rendered as the store hero image.

## Failure Handling

The governing rule: **one asset failing must never abort the pack run.**
Across 30 unattended assets, partial failure is the normal case.

| Failure | Response |
|---|---|
| API timeout or 5xx | Retry with backoff, then mark `generation_failed` and continue the pack |
| Gate 1 or Gate 2 failure | Automatic re-roll with a reason code, up to `max_rerolls` (default 3), then surface on the contact sheet as a failure |
| Non-manifold beyond cleanup | Voxel remesh as last-resort recovery only. It rounds corners, so it is always flagged, never silent. |
| Palette non-conformance | A bug in the PS1 pass, not the asset. Fails the run loudly. |

### Cost controls

**Content-addressed caching.** Every generation keys on
`hash(prompt or reference, provider, params)`. A re-run reuses `raw/` for
anything unchanged and pays only for what actually changed. Without this,
every iteration on the PS1 pass would re-bill for identical geometry, and the
PS1 pass is where iteration will concentrate.

**Hard spend cap per run.** A `max_generations` ceiling in the catalog,
checked before every provider call. A re-roll loop defect that silently
consumes credits overnight is the most likely way this pipeline causes
financial harm; the cap makes that impossible rather than merely unlikely.

## Platform Repair (prerequisite)

Scoped to path and platform handling only. Not a refactor.

- Add Windows Blender discovery (registry, `PATH`, Program Files) alongside
  the existing POSIX candidates in `factory/config.json` and
  `factory/config.py`.
- Resolve `working_directory` relative to `FACTORY_ROOT.txt` rather than
  storing an absolute path in `knowledge/*.json`.
- `doctor` must pass on this Windows host before any other phase lands.

## Testing Strategy

`AGENTS.md` requires test-first changes for factory behaviour.

| Layer | What it proves |
|---|---|
| Unit | Catalog schema, style-contract validation, band assignment, palette-conformance checker |
| Provider | Sloyd request and response handling, retry, backoff, spend cap, all against fake transports. No network, no spend. |
| PS1 pass | Integration test on the `trenchgun.fbx` fixture: part split, decimate to band, palette quantize, export |
| Determinism | Same raw plus same contract yields a byte-identical GLB. If this fails, the coherence guarantee does not hold. |
| Gates | Deliberately-bad fixtures (over-budget triangles, off-palette texture, non-manifold mesh, unsnapped pivot) must each fail their gate |
| End-to-end | Full 30-asset pack run against cached `raw/`, offline, zero cost |

The end-to-end test falls out of the architecture: because `raw/` is
content-addressed and immutable, the entire pipeline replays from cache
without touching an API.

### Test fixture

`.hermes/desktop-attachments/m1897-trenchgun.zip` contains
`source/trenchgun.fbx` (1.9 MB) with a full 4K PBR texture set and semantic
part separation across `Barrel`, `Receiver`, `ReceiverInternals`, `Stock`,
`BarrelAttachment`, and `Cartridge`. It is a historically correct Winchester
M1897 and a better PS1-pass fixture than any generated output, at no cost.

**Its provenance is unverified.** The files are dated 2025-02-01 and are
therefore a third-party download. It is approved as a test fixture only.
Before `m1897_trench_gun` ships in any pack, either its source licence must be
verified as permitting redistribution, or the shipped asset must be
regenerated through lane B. Unverifiable asset provenance is a
store-threatening risk, and this must be resolved before pack release rather
than after.

## Implementation Sequence

| Phase | Work | Cost |
|---|---|---|
| 0 | Platform repair; `doctor` green on Windows | free |
| 1 | PS1 pass proven on `trenchgun.fbx` | free |
| 2 | Gates: silhouette IoU, palette conformance, grid conformance | free |
| 3 | Catalog, style contract, pack orchestrator against local fixtures | free |
| 4 | Sloyd provider | first spend |
| 5 | Lane B: FLUX concept to Sloyd image-to-3D | spend |
| 6 | Contact sheet, approval loop, provenance ledger | spend |
| 7 | Full pack run, validated dist zip, demo-scene hero render | spend |

Phases 0 through 3 are approximately half the work and cost nothing. By the
time a subscription is required, the only remaining unknown is whether
Sloyd's output is good, and the 2026-07-25 evaluation already indicates that
it is. If the PS1 pass proves to be the blocker, that surfaces before any
money is spent.

## Out of Scope

- **Storefront and website.** A separate spec, written immediately after this
  one. The pipeline must be able to produce a pack without it.
- **Vehicles.** Pack 2. High value per unit, slow per unit, and a risk to
  pack 1's ship date.
- **Rigging and animation.** Sloyd offers both; a diorama kit needs neither.
- **PBR or realistic edition.** The geometry supports it later. Not now.
- **PS1 wobble shader.** Distributed alongside the pack as a bonus, not part
  of the pipeline.
- **Multi-provider tournament** (Tripo, Hugging Face Spaces). Added once one
  provider works end to end.
- **Browser Studio editor.** Not required to sell packs.

## Superseded Decisions

This design intentionally overrides parts of
`docs/IDEAL_AI_GAME_ASSET_PIPELINE.md`. That document remains correct about
architecture and wrong about this hardware.

- **Local image-to-3D is impossible on this machine.** The shortlist's
  recommendation to run Pixal3D on a 24 GB GPU is unsatisfiable: the card is
  AMD and the entire stack is CUDA-only. Hosted generation replaces it.
- **Full high-to-low PBR baking is dropped** for PS1 packs. It is the correct
  approach for a realistic pack and unnecessary work here.
- **The per-asset human approval gate becomes a per-pack batch gate.** The
  approval requirement is preserved; its granularity changes, and coherence
  review actually improves as a result.
- **ComfyUI as the concept orchestration layer is replaced** by the hosted
  FLUX provider already implemented in `factory/providers/bfl.py`, since
  `doctor` reports `comfyui: unavailable`.

The document's core correction is retained unchanged and is the basis of the
PS1 pass ordering: generate rich form first; simplify only after the form
passes review.
