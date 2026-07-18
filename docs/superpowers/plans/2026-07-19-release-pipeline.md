# Release Pipeline Implementation Plan

**Date:** 2026-07-19

**Status:** Approved for execution by the user's “proceed” instruction

**Architecture:** `docs/superpowers/specs/2026-07-18-style-neutral-self-improving-asset-factory-design.md`

## Outcome

Install a reproducible release toolchain beneath `G:\DevWork\GameDev\BlenderAssetFactory\.tooling` and add style-neutral commands that validate an authoritative GLB, create and revalidate a non-authoritative optimized derivative, prove that both assets load in the pinned Three.js runtime, create a contact sheet, and publish a release package transactionally. No release operation may modify Blender source files or the active M42 worktree.

## Pinned dependencies

- Node.js `24.17.0` LTS, portable Windows x64 archive from nodejs.org, checksum verified against the official `SHASUMS256.txt`.
- Khronos `gltf-validator` npm package `2.0.0-dev.3.10`.
- meshoptimizer/gltfpack `1.1`, native Windows binary from the signed GitHub release, with a recorded archive checksum.
- Three.js `0.185.1`.
- `playwright-core` `1.61.1`, using an installed Chrome or Edge executable rather than downloading a second browser.

Dependency manifests and npm lockfiles are tracked. Binaries, npm modules, caches, screenshots, and run reports remain excluded under `.tooling`, `tmp`, and `reports` on `G:`.

## Mandatory release gates

1. Input and output paths pass factory ownership and package-boundary checks.
2. The authoritative GLB passes Khronos validation with zero errors.
3. gltfpack creates a separate derivative; it never replaces the authoritative GLB.
4. The derivative passes Khronos validation with zero errors.
5. UV comparison verifies that source and derivative texture-coordinate bounds remain within a configured tolerance. Pixel-atlas jobs use gltfpack floating-point UV preservation and fail closed if UV evidence cannot be read.
6. The pinned Three.js viewer loads and renders both GLBs in a loopback-only browser session and records scene statistics plus screenshots.
7. Required QA views exist and a deterministic contact sheet is captured.
8. Package provenance identifies the authoritative asset, derivative, tool versions, hashes, gate reports, and source job hash.
9. Publication moves a complete staged directory into the release root only after every mandatory gate succeeds. Failure retains a structured report but cannot create a published release.

## Task 1 — Release fixture and GLB inspection

**Files:**

- Create `tests/glb_fixture.py`
- Create `tests/test_gltf_inspection.py`
- Create `factory/gltf_inspection.py`

**Test-first behavior:**

- Generate a deterministic embedded-buffer triangle GLB with positions, indices, UVs, one material, one mesh, one node, and one scene.
- Parse GLB headers and JSON/BIN chunks without third-party Python dependencies.
- Extract primitive counts, triangle counts, texture-coordinate accessor bounds, extensions, embedded/external resource status, and declared generator.
- Reject malformed headers, missing binary chunks, path traversal in external URIs, and unsupported sparse UV accessors when pixel-atlas stability is mandatory.

**Commit:** `feat: inspect glb release evidence`

## Task 2 — Reproducible release-tool bootstrap

**Files:**

- Create `tools/manifests/release-toolchain.json`
- Create `tools/release-node/package.json`
- Create `tools/release-node/package-lock.json`
- Create `bootstrap/setup-release.ps1`
- Modify `bootstrap/setup.ps1`
- Modify `factory/doctor.py`
- Modify `tests/test_doctor.py`
- Create `tests/test_release_bootstrap.py`

**Test-first behavior:**

- Dry-run output resolves every writable/install target to `G:` and exposes exact versions.
- Installer verifies resolved target paths before extraction or replacement.
- Node archive SHA-256 must match the official checksum before extraction.
- gltfpack release archive SHA-256 is recorded and verified before extraction.
- npm uses a cache beneath `.tooling/cache/npm`, installs the exact lockfile beneath `.tooling/release-node`, and runs without audit/fund/network scripts.
- Repeated setup is idempotent and writes `.tooling/release-runtime.json` atomically.
- Doctor invokes real version/probe commands rather than treating marker files as health.

**Commit:** `feat: pin local release toolchain`

## Task 3 — Khronos validator adapter

**Files:**

- Create `tools/release-node/validate-gltf.mjs`
- Create `factory/gltf_validation.py`
- Create `tests/test_gltf_validation.py`
- Modify `factory/cli.py`

**Interface:**

```text
factory.ps1 validate --input <authoritative.glb> --report <report.json> --json
```

The Node adapter validates bytes with the official package and writes only JSON to stdout. Python normalizes the report, hashes the input, rejects validator errors, records warnings separately, and writes the report atomically. The command rejects inputs outside the configured root/model root and reports unavailable tooling as a structured capability failure.

**Commit:** `feat: gate glb releases with Khronos validator`

## Task 4 — Non-authoritative gltfpack derivative

**Files:**

- Create `factory/optimizer.py`
- Create `tests/test_optimizer.py`
- Modify `factory/cli.py`

**Interface:**

```text
factory.ps1 optimize --input <authoritative.glb> --output <optimized.glb> [--pixel-atlas] --json
```

The adapter rejects identical source/destination paths, invokes the pinned native binary, uses `-vtf` for pixel-atlas work, preserves supported extras, validates the derivative, compares GLB statistics and UV bounds, records source/output hashes and command arguments, and removes an invalid partial derivative. It never deletes or writes the source.

**Commit:** `feat: create verified gltfpack derivatives`

## Task 5 — Pinned Three.js reference viewer

**Files:**

- Create `tools/threejs-viewer/package.json`
- Create `tools/threejs-viewer/index.html`
- Create `tools/threejs-viewer/viewer.mjs`
- Create `tools/release-node/capture-viewer.mjs`
- Create `factory/runtime_preview.py`
- Create `tests/test_runtime_preview.py`
- Modify `factory/cli.py`

**Interface:**

```text
factory.ps1 preview --input <asset.glb> --output <engine.png> --report <report.json> --json
```

The Python adapter serves only a unique staging directory through an ephemeral loopback port. The browser script launches a discovered Chrome/Edge executable through `playwright-core`, waits for an explicit viewer result, captures a deterministic 960×540 image, and records renderer, scene, mesh, triangle, material, texture, camera-framing, and console-error evidence. The viewer supports meshopt decoding and uses neutral lighting/background independent of any style profile.

**Commit:** `feat: prove assets in pinned Three.js viewer`

## Task 6 — Contact-sheet reporting

**Files:**

- Create `factory/contact_sheet.py`
- Create `tools/release-node/capture-contact-sheet.mjs`
- Create `tests/test_contact_sheet.py`
- Modify `factory/cli.py`

**Interface:**

```text
factory.ps1 report --manifest <views.json> --output <contact-sheet.png> --json
```

The manifest names required semantic views rather than assuming an art style. Missing required views fail. Paths are copied into a unique staging directory, labels and hashes are escaped into deterministic HTML, and the browser captures the sheet. Default release views are beauty, front, side, top, silhouette, wireframe, UV, base-color, ORM, collision, and engine; contracts may declare a different required set.

**Commit:** `feat: generate deterministic asset contact sheets`

## Task 7 — Transactional release coordinator

**Files:**

- Create `factory/release.py`
- Create `factory/schemas/release-job.schema.json`
- Create `tests/test_release.py`
- Modify `factory/cli.py`

**Interface:**

```text
factory.ps1 release --job <release-job.json> --json
```

The coordinator creates `tmp/factory/<run-id>`, copies the authoritative GLB rather than moving it, runs all gates, writes a provenance/package manifest and completion sentinel, then atomically renames the finished stage into `assets/releases/<asset-id>/<version>`. Existing published versions are immutable. Any failed gate records `reports/runs/<run-id>/release-failure.json`, leaves the authoritative source untouched, and publishes nothing.

Tests inject fake adapters to witness validator, optimizer, viewer, and report failures and prove publication never occurs before the final sentinel.

**Commit:** `feat: publish validated asset packages transactionally`

## Task 8 — Phase gate, memory, and transfer metadata

**Files:**

- Modify `factory/verification.py`
- Modify `factory/transfer.py`
- Modify `tools/manifests/transfer.json`
- Modify `knowledge/START_HERE.md`
- Modify `knowledge/FACTORY_STATE.md`
- Create `knowledge/project-summaries/factory-release-pipeline-phase-2.json`
- Create `tests/test_release_continuity.py`

**Verification:**

1. Run all standard-library tests.
2. Run the real validator against the fixture authoritative GLB.
3. Optimize it and validate the derivative.
4. Load both in the pinned Three.js viewer and capture screenshots.
5. Build a contact sheet.
6. Publish a fixture package transactionally and verify all hashes/manifests.
7. Run `factory.ps1 doctor --save`, `factory.ps1 transfer-manifest`, and `factory.ps1 verify --save`.
8. Run `git diff --check` and confirm the M42 worktree still has exactly its pre-existing Task 3 modifications.
9. Close the factory-infrastructure phase with an asset-scoped project summary; do not change the active M42 continuation.

**Commit:** `test: verify portable release pipeline`

## Completion gate

- Release tools install reproducibly beneath `.tooling` on `G:` and are independently probed.
- Authoritative and optimized GLBs both pass the official validator.
- Pixel-atlas UV drift is measured and gated.
- Three.js renders both files through a loopback-only server.
- Contact sheets are deterministic and semantic-view driven.
- Release publication is transactional and immutable.
- Reports contain hashes, versions, commands, timestamps, and provenance.
- The complete suite passes from the canonical worktree.
- Existing M42 Task 3 work is byte-for-byte untouched.
