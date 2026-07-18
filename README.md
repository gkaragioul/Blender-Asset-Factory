# Blender Asset Factory

Blender Asset Factory is a local-first, style-neutral production system for optimized Three.js game assets. Blender is authoritative for geometry and source exports; the factory adds durable knowledge, validation, runtime previews, provenance, and reproducible tooling.

The first production profile is premium PS1-era WWII art. Profiles are data, so the core remains suitable for realistic, stylized, fantasy, science-fiction, mobile, hand-painted, and future asset packs.

## Canonical storage

- Factory: `G:\DevWork\GameDev\BlenderAssetFactory`
- Model weights: `G:\LLMs`
- Local environments: `.tooling` beneath the active trusted checkout
- Blender: discovered explicitly; currently Blender 5.2 LTS
- Blender bridge: loopback only at `127.0.0.1:9876`

Canonical content directories:

- Projects: `G:\DevWork\GameDev\BlenderAssetFactory\projects`
- Generated assets: `G:\DevWork\GameDev\BlenderAssetFactory\assets`
- Specifications: `G:\DevWork\GameDev\BlenderAssetFactory\specs`
- Generators: `G:\DevWork\GameDev\BlenderAssetFactory\scripts`
- Standalone renders: `G:\DevWork\GameDev\BlenderAssetFactory\renders`

Specifications control output paths and normally publish beneath `assets`.

## First-time setup

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\bootstrap\setup.ps1
```

The bootstrap pins uv, Python, portable Node.js, Khronos glTF Validator, native gltfpack, Three.js, and Playwright Core beneath `.tooling` on `G:`. It uses an installed Chrome or Edge executable for loopback-only runtime QA and does not modify the user `PATH`.

## Generate the original reference crate

```powershell
& 'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe' `
  --background --factory-startup `
  --python 'G:\DevWork\GameDev\BlenderAssetFactory\scripts\generate_asset.py' `
  -- --spec 'G:\DevWork\GameDev\BlenderAssetFactory\specs\ps1_crate.json'
```

## Daily entry points

If the machine permits local PowerShell scripts directly:

```powershell
.\factory.ps1 doctor --json
.\factory.ps1 resume --json
.\factory.ps1 verify --json
```

On systems with a restrictive execution policy:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\factory.ps1 doctor --json
powershell -NoProfile -ExecutionPolicy Bypass -File .\factory.ps1 resume --json
powershell -NoProfile -ExecutionPolicy Bypass -File .\factory.ps1 verify --json
```

## Release pipeline

The authoritative GLB is never optimized in place. These commands validate it, create a separate derivative, render runtime evidence, and assemble QA reporting:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\factory.ps1 validate --input <authoritative.glb> --report <validation.json> --json
powershell -NoProfile -ExecutionPolicy Bypass -File .\factory.ps1 optimize --input <authoritative.glb> --output <optimized.glb> --report <optimization.json> --pixel-atlas --json
powershell -NoProfile -ExecutionPolicy Bypass -File .\factory.ps1 preview --input <asset.glb> --output <engine.png> --report <preview.json> --json
powershell -NoProfile -ExecutionPolicy Bypass -File .\factory.ps1 report --manifest <views.json> --output <contact-sheet.png> --qa-report <report.json> --json
powershell -NoProfile -ExecutionPolicy Bypass -File .\factory.ps1 release --job <release-job.json> --json
```

`release` publishes to `assets/releases/<asset-id>/<version>` only after every mandatory gate succeeds. Published versions are immutable; failed runs retain structured evidence beneath `reports/runs` and publish nothing.

## Durable memory

Start new conversations with [knowledge/START_HERE.md](knowledge/START_HERE.md). Machine-readable active state is in [knowledge/active-project.json](knowledge/active-project.json). The repository—not chat history—is authoritative.

## Architecture

See [the approved factory design](docs/superpowers/specs/2026-07-18-style-neutral-self-improving-asset-factory-design.md), [the Phase 1 plan](docs/superpowers/plans/2026-07-18-foundation-and-memory.md), and [the Phase 2 release-pipeline plan](docs/superpowers/plans/2026-07-19-release-pipeline.md).
