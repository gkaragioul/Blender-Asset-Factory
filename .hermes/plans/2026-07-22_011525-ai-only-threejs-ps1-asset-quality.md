# AI-Only Lightweight Three.js PS1 Asset Quality Plan

> **For Hermes:** Use this as the execution plan for autonomous production. Implement with factory tests and Blender/Hermes MCP, not manual DCC work.

**Goal:** Reach asset-pack quality comparable to the supplied PS1/PSX weapon references using AI-driven Blender generation, validation, optimization, and Three.js runtime packaging.

**Architecture:** Keep Blender authoritative for source `.blend` and export `.glb`; use the Blender Asset Factory as the orchestrator; add AI-only art-direction loops around the existing release pipeline. Every asset is built from a JSON contract, inspected in Blender, validated with Khronos glTF Validator, optimized with gltfpack, loaded in a pinned Three.js viewer, and published only after QA gates pass.

**Tech Stack:** Blender 4.0.2 on this Linux host, Blender MCP addon/server on `localhost:9876`, Hermes MCP server `blender`, Python factory modules, Khronos glTF Validator, gltfpack, Three.js viewer, Playwright/Chrome capture, generated contact sheets.

---

## Current System Inventory

Already present in `v1.0`:

- `factory/cli.py`: commands for `doctor`, `validate`, `optimize`, `preview`, `report`, `release`, `learn`, `resume`, `verify`.
- `factory/gltf_validation.py`: Khronos validation gate.
- `factory/optimizer.py`: gltfpack derivative creation and UV-drift evidence.
- `factory/runtime_preview.py`: pinned Three.js runtime proof and screenshots.
- `factory/contact_sheet.py`: deterministic QA sheets.
- `factory/release.py`: transactional immutable publish.
- `knowledge/START_HERE.md`, `knowledge/FACTORY_STATE.md`, `knowledge/active-project.json`: continuation memory.
- Published sample assets:
  - `assets/ps1_wood_crate_01/` — simple PS1 crate, 204 triangles.
  - `assets/ps1_ww2_pump_shotgun_01/` — shotgun, 900 triangles, 256px base-color atlas, 128px ORM atlas, 5 animation clips.
- Hermes/Blender connection installed on this machine:
  - Blender 4.0.2 installed.
  - Blender MCP addon enabled.
  - Hermes MCP server `blender` configured with 22 tools.

## Quality Target From Supplied References

The sample image implies:

- Low-poly weapon silhouettes readable at thumbnail scale.
- PS1/PSX-era texture treatment: pixelated color blocks, low-res atlases, nearest-neighbor look, minimal PBR complexity.
- Strong proportion discipline: long barrels, compact receiver detail, stock/foregrip material contrast.
- Small file sizes for browser/game use.
- Prefer one embedded GLB per weapon with optional animation clips.
- Presentation must include white/neutral product render plus in-engine proof.

## Current Quality Gap

The existing shotgun proves the technical pipeline, but visual quality still needs a dedicated art-director loop:

- Wood is too pale/pink compared with stronger walnut/aged wood in references.
- Metal is too blocky/noisy in value without enough deliberate receiver/bolt/trigger detail.
- Barrel/receiver silhouette is plausible but less elegant than the reference thumbnails.
- Contact-sheet/reference comparison scoring is not yet automated.
- The Linux checkout still contains stale Windows path assumptions in docs/state; update config/state before new autonomous production.

---

## Task 1: Normalize Linux Factory State

**Objective:** Make the factory state reflect this machine before new production.

**Files:**
- Modify: `knowledge/START_HERE.md`
- Modify: `knowledge/FACTORY_STATE.md`
- Modify: `knowledge/active-project.json`
- Possibly modify: `factory/config.py`

**Steps:**
1. Run `python3 -m factory doctor --json` from `v1.0` and inspect actual capability failures.
2. Patch path/config assumptions so canonical root is `/media/<user>/Work/Dev_Work/GameDev/Blender Asset Factory/v1.0`, not `G:\...`, for this Linux checkout.
3. Re-run `python3 -m factory doctor --json` until mandatory capabilities pass.
4. Save refreshed state with the factory state command if supported.

**Verification:**
- `doctor` reports `blender`, `python`, `uv`, `model_root`, `node`, `three`, and `threejs_viewer` accurately for Linux.

## Task 2: Add a PS1 Weapon Style Contract

**Objective:** Convert the sample quality bar into machine-readable gates.

**Files:**
- Create: `profiles/ps1_weapon/profile.json`
- Create: `profiles/ps1_weapon/materials.json`
- Create: `profiles/ps1_weapon/evaluations.json`
- Create: `tests/test_ps1_weapon_profile.py`

**Contract values:**
- Weapon triangle target: 500–1,200 triangles.
- Base-color atlas: 128–256 px.
- ORM/utility atlas: 64–128 px.
- Materials: target 1–3 draw-call materials.
- Embedded GLB target: under 200 KB for static, under 350 KB for animated hero weapon.
- Required semantic parts: stock, receiver, barrel, muzzle, trigger, sight/rail/detail, optional animation bones.
- Required texture vocabulary: dark walnut, blued/parkerized steel, edge wear, grime/oil, simple shadow gradients.

**Verification:**
- Tests prove budgets load independently of any single asset.

## Task 3: Build an AI Art-Director Scoring Loop

**Objective:** Make Hermes critique generated previews against reference criteria without human intervention.

**Files:**
- Create: `factory/visual_eval.py`
- Create: `factory/schemas/visual-eval.schema.json`
- Create: `tests/test_visual_eval.py`

**Behavior:**
- Input: target style profile, asset manifest, preview image, optional reference images.
- Output JSON scores:
  - silhouette_readability
  - material_separation
  - ps1_texture_authenticity
  - thumbnail_quality
  - geometry_believability
  - threejs_runtime_readiness
- Output next-action critique strings suitable for automatic regeneration.

**Verification:**
- Fixture previews return deterministic schema-valid output.

## Task 4: Create Parametric Weapon Builders

**Objective:** Generate a family of weapon assets without hand modeling.

**Files:**
- Create: `scripts/generate_ps1_weapon.py`
- Create: `specs/ps1_weapon_pump_shotgun_02.json`
- Create: `specs/ps1_weapon_double_barrel_01.json`
- Create: `specs/ps1_weapon_smg_01.json`
- Create: `tests/test_weapon_specs.py`

**Builder requirements:**
- Construct geometry procedurally in Blender Python.
- Name mesh parts semantically.
- Generate UVs and pixel atlases automatically.
- Add low-res hand-painted procedural textures.
- Export `.blend`, authoritative `.glb`, preview render, manifest.
- Optionally generate simple animation clips for moving parts.

**Verification:**
- Each generated asset stays within triangle/material/texture/file-size budgets.

## Task 5: Add Autonomous Regenerate-Until-Pass

**Objective:** Let Hermes/AI iterate alone until quality gates pass.

**Files:**
- Create: `factory/autoproduce.py`
- Create: `factory/schemas/autoproduce-job.schema.json`
- Modify: `factory/cli.py`
- Create: `tests/test_autoproduce.py`

**Interface:**
```bash
python3 -m factory autoproduce --job specs/jobs/ps1_weapon_pack_01.json --json
```

**Loop:**
1. Generate candidate from spec.
2. Run Blender export.
3. Validate GLB.
4. Optimize derivative.
5. Load in Three.js preview.
6. Build contact sheet.
7. Run visual eval.
8. If technical gates fail, repair deterministically.
9. If visual score below threshold, mutate seed/material/proportions and retry.
10. Publish only after all gates pass.

**Verification:**
- Unit tests use fake adapters to prove failed candidates never publish.
- Real smoke test produces at least one valid GLB and preview.

## Task 6: Produce the First AI-Only Weapon Pack

**Objective:** Create a concrete pack matching the attached samples.

**Files/Outputs:**
- `assets/releases/ps1_weapon_pack_01/<version>/`
- Individual assets:
  - pump shotgun
  - double-barrel shotgun
  - rifle/carbine
  - SMG or machine gun
- Each asset includes `.blend`, authoritative `.glb`, optimized `.glb`, preview PNGs, contact sheet, manifest, QA report.

**Verification:**
- All release gates pass.
- Contact sheet visually reaches the reference bar.
- File sizes remain lightweight for Three.js.

---

## Operating Rule

No manual Blender editing. Human input is only high-level direction. Hermes uses Blender MCP/Blender Python, factory tests, runtime previews, and visual self-critique to generate, reject, repair, and publish assets autonomously.
