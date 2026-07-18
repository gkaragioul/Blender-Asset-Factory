# Blender Asset Factory

Blender Asset Factory is a local-first, style-neutral production system for optimized Three.js game assets. Blender is authoritative for geometry and source exports; the factory adds durable knowledge, validation, runtime previews, provenance, and reproducible tooling.

The first production profile is premium PS1-era WWII art. Profiles are data, so the core remains suitable for realistic, stylized, fantasy, science-fiction, mobile, hand-painted, and future asset packs.

## Canonical storage

- Factory: `G:\DevWork\GameDev\BlenderAssetFactory`
- Model weights: `G:\LLMs`
- Local environments: `.tooling` beneath the active trusted checkout
- Blender: discovered explicitly; currently Blender 5.2 LTS
- Blender bridge: loopback only at `127.0.0.1:9876`

## First-time setup

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\bootstrap\setup.ps1
```

The bootstrap pins uv and Python beneath `.tooling` on `G:` and does not modify the user `PATH`.

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

## Durable memory

Start new conversations with [knowledge/START_HERE.md](knowledge/START_HERE.md). Machine-readable active state is in [knowledge/active-project.json](knowledge/active-project.json). The repository—not chat history—is authoritative.

## Architecture

See [the approved factory design](docs/superpowers/specs/2026-07-18-style-neutral-self-improving-asset-factory-design.md) and [the Phase 1 plan](docs/superpowers/plans/2026-07-18-foundation-and-memory.md).
