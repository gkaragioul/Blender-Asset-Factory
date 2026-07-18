# Local Creative Stack Implementation Plan

**Date:** 2026-07-19

**Status:** Approved for execution by the user's repeated "approved" and "proceed" instructions

**Architecture:** `docs/superpowers/specs/2026-07-18-style-neutral-self-improving-asset-factory-design.md`

## Outcome

Install and wire a reproducible, style-neutral creative toolchain whose writable data stays beneath `G:\DevWork\GameDev\BlenderAssetFactory` and whose model weights stay beneath `G:\LLMs`. The first production profile is PS1-era WWII, but no application, model registry, staging contract, or Blender integration may encode that style as a universal default.

The local stack will provide AMD-native concept and texture generation, hand-painting and inpainting in Krita, procedural material authoring in Material Maker, 3D painting in a locally source-built ArmorPaint, and provenance-gated handoff into Blender. External generators may write only to staging. A reviewed import operation must copy accepted files into a project; it may never replace an authoritative asset in place.

## Pinned applications

- ComfyUI `v0.28.0`, official Windows AMD portable archive, checksum verified.
- Krita `5.3.0`, official portable Windows archive, checksum verified.
- Krita AI Diffusion `1.52.1`, official plug-in archive, checksum verified.
- Material Maker `1.7`, official Windows archive, checksum verified.
- ArmorPaint source commit `870a6b18da56eaac222f5d6c340cd8ed492aae6a`, built locally with the installed Visual Studio 2022 Build Tools and clang-cl. No paid binary is required.

Every tracked manifest records version or commit, upstream URL, license/source URL, SHA-256 where an archive is published, install destination, and a deterministic probe. Download caches, extracted applications, build products, profiles, generated images, and model weights are ignored runtime data on `G:`.

## Storage boundaries

```text
G:\DevWork\GameDev\BlenderAssetFactory\.tooling\creative\     installed apps and runtimes
G:\DevWork\GameDev\BlenderAssetFactory\.tooling\profiles\    portable application profiles
G:\DevWork\GameDev\BlenderAssetFactory\.tooling\cache\       verified download/build caches
G:\DevWork\GameDev\BlenderAssetFactory\staging\ai\           immutable generation runs
G:\LLMs\comfyui\                                                ComfyUI model directory
G:\LLMs\manifests\                                              model inventory and provenance
```

ComfyUI is launched with `--models-directory G:\LLMs\comfyui`. Krita is launched through a factory wrapper that redirects `APPDATA`, `LOCALAPPDATA`, cache, and plug-in state to the portable profile on `G:`. Material Maker and ArmorPaint receive factory-owned profile and output paths where supported. Installers fail closed if any writable destination resolves off `G:`.

## Task 1 — Creative tool manifest and safe installer core

**Files:**

- Create `tools/manifests/creative-toolchain.json`
- Create `bootstrap/setup-creative.ps1`
- Create `tests/test_creative_bootstrap.py`
- Modify `bootstrap/setup.ps1`

**Test-first behavior:**

- Dry run exposes all versions, URLs, hashes, destinations, model root, profile root, and planned build actions without network or filesystem mutation.
- Every writable path is normalized and required to be on `G:`.
- Downloads are cached, SHA-256 verified before extraction, and installed through a temporary sibling directory followed by an atomic rename.
- Interrupted or partial installs cannot be reported as healthy and are moved to factory recovery before repair.
- Repeated setup is idempotent and writes `.tooling/creative-runtime.json` atomically.
- Individual `-Only` application selection supports bounded repair without reinstalling the stack.

**Commit:** `feat: pin local creative toolchain`

## Task 2 — AMD ComfyUI service and shared model registry

**Files:**

- Create `factory/creative_runtime.py`
- Create `factory/model_registry.py`
- Create `factory/schemas/model-manifest.schema.json`
- Create `tools/manifests/creative-models.json`
- Create `tools/comfyui/workflows/smoke-texture.json`
- Create `tests/test_creative_runtime.py`
- Create `tests/test_model_registry.py`
- Modify `factory/cli.py`
- Modify `factory/doctor.py`

**Interfaces:**

```text
factory.ps1 creative setup [--only comfyui] --json
factory.ps1 creative start comfyui --json
factory.ps1 creative stop comfyui --json
factory.ps1 creative health comfyui --json
factory.ps1 models plan --manifest tools/manifests/creative-models.json --json
factory.ps1 models install --id <model-id> --json
```

The service binds only to `127.0.0.1`, records PID/port/command/log paths, refuses a foreign process on its port, uses the official AMD portable runtime, and proves the selected GPU/runtime through ComfyUI system statistics. Model installation is allow-listed by manifest, supports resumable downloads, verifies SHA-256, records upstream license and source, and never places weights outside `G:\LLMs`. The initial baseline must be downloadable without credentials, usable for commercial asset production under its published terms, and runnable on the RX 7900 XTX; optional heavier models remain explicit rather than silently downloaded.

**Commit:** `feat: run AMD ComfyUI with shared models`

## Task 3 — Krita, Material Maker, and ArmorPaint adapters

**Files:**

- Create `factory/creative_apps.py`
- Create `tests/test_creative_apps.py`
- Create `tools/launch-krita.ps1`
- Create `tools/launch-material-maker.ps1`
- Create `tools/launch-armorpaint.ps1`
- Modify `factory/cli.py`
- Modify `factory/doctor.py`

**Interfaces:**

```text
factory.ps1 creative launch krita [--file <image>] --json
factory.ps1 creative launch material-maker [--file <material>] --json
factory.ps1 creative launch armorpaint [--file <mesh>] --json
```

Krita starts with its factory-owned portable profile and discovers the pinned AI Diffusion plug-in. The plug-in is configured to use the loopback ComfyUI service without copying model weights. Material Maker and ArmorPaint are probed by real executable/version or bounded headless launch evidence. ArmorPaint is cloned at the pinned commit and built from source; its build metadata records source commit, compiler, MSBuild version, and output hash. Launch adapters validate all supplied files and working directories against factory/model ownership boundaries.

**Commit:** `feat: wire local painting applications`

## Task 4 — Immutable AI provenance staging

**Files:**

- Create `factory/generation_staging.py`
- Create `factory/schemas/generation-job.schema.json`
- Create `factory/schemas/generation-run.schema.json`
- Create `tests/test_generation_staging.py`
- Modify `factory/cli.py`

**Interfaces:**

```text
factory.ps1 stage generation --job <generation-job.json> --json
factory.ps1 stage inspect --run <run-id> --json
factory.ps1 stage accept --run <run-id> --output <project-source-path> --json
```

Each run receives an immutable directory containing the input job, exact workflow, prompt and negative prompt, seed, sampler/settings, model IDs and hashes, tool/runtime versions, source references and hashes, generated file hashes, license/provenance records, and completion sentinel. Acceptance copies a named artifact to a new project path and records the relationship; it cannot overwrite an existing file, write a Blender authoritative file, or mutate the source run. Staging supports concept, texture/material, decal, mask, and inpaint roles without imposing a style.

**Commit:** `feat: preserve generated source provenance`

## Task 5 — Blender handoff and factory integration

**Files:**

- Create `factory/blender_handoff.py`
- Create `tests/test_blender_handoff.py`
- Create `tools/blender/import_staged_images.py`
- Modify `factory/cli.py`
- Modify `factory/doctor.py`

**Interface:**

```text
factory.ps1 blender stage-import --manifest <accepted-sources.json> --blend <authoritative.blend> --json
```

The handoff writes a recovery snapshot before Blender mutation, launches the pinned Blender executable in a bounded subprocess, enforces expected builder/project identity, packs or copies accepted images into project-owned source directories, assigns explicit color spaces and semantic roles, and emits a structured import report. It cannot execute arbitrary staged Python, alter factory safety boundaries, or publish an asset. Tests use a fake Blender executable first; the real smoke test imports a generated neutral texture into a disposable fixture blend.

**Commit:** `feat: hand reviewed sources to Blender`

## Task 6 — End-to-end local creative smoke test

**Files:**

- Create `factory/creative_smoke.py`
- Create `tests/test_creative_smoke.py`
- Create `tools/comfyui/workflows/neutral-material-smoke.json`
- Modify `factory/cli.py`

**Interface:**

```text
factory.ps1 creative smoke --json
```

The smoke path starts ComfyUI loopback-only, queries GPU/runtime evidence, executes a deterministic low-cost neutral material workflow, stages its image and full provenance, optionally opens neither GUI nor browser, accepts the texture into a disposable project fixture, imports it into Blender, saves the fixture, and stops only the service instance it owns. A failed sub-gate leaves evidence but cannot create an accepted source or mutate a real project.

**Commit:** `test: prove local creative vertical slice`

## Task 7 — Continuity, transfer, and learning closeout

**Files:**

- Modify `factory/verification.py`
- Modify `factory/transfer.py`
- Modify `tools/manifests/transfer.json`
- Modify `knowledge/START_HERE.md`
- Modify `knowledge/FACTORY_STATE.md`
- Create `knowledge/project-summaries/factory-local-creative-stack-phase-3.json`
- Create `tests/test_creative_continuity.py`

**Verification:**

1. Run the complete standard-library unit suite.
2. Verify every archive hash and every installed application probe.
3. Prove ComfyUI listens only on loopback and reports the AMD GPU/runtime.
4. Install and hash the initial model, run the deterministic workflow, and preserve its provenance.
5. Prove Krita discovers the plug-in and profile on `G:`.
6. Prove Material Maker launches from the pinned install.
7. Build/probe ArmorPaint from the pinned source commit.
8. Import a staged neutral texture into a disposable Blender fixture and verify the saved data.
9. Run `factory.ps1 doctor --save`, `factory.ps1 transfer-manifest`, and `factory.ps1 verify --save`.
10. Run `git diff --check` and confirm the M42 Task 3 worktree retains exactly its two pre-existing modifications.
11. Close the infrastructure phase with reviewed evidence while leaving the active M42 next action unchanged.

**Commit:** `test: verify portable creative stack`

## Completion gate

- All application binaries, profiles, caches, staging runs, and build products live on `G:`.
- All model weights and their inventory live under `G:\LLMs`.
- ComfyUI uses the RX 7900 XTX locally without paid compute and is loopback-only.
- Krita, AI Diffusion, Material Maker, and source-built ArmorPaint are installed and genuinely probed.
- Generated sources are reproducible and traceable by model/workflow/settings/seed/hash/license.
- No generated source can replace an authoritative asset directly.
- A reviewed source can be transferred through a recovery-protected Blender handoff.
- The system remains style-neutral; PS1 WWII is a project profile, not factory-wide bias.
- Durable memory and transfer metadata allow restoration on another computer or in a new Codex task.
