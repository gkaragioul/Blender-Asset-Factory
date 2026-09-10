# Blender Asset Factory

**Private development workspace · 0.5.0**

A local-first toolchain for creating and checking Blender assets for Three.js projects. Blender is the editable source of truth; the factory adds specifications, validation, separate optimized exports, runtime previews, and durable production knowledge.

[Project home](docs/index.md) · [Getting started](docs/GETTING_STARTED.md) · [KHEPRI rover](examples/khepri/README.md) · [Release notes](docs/releases/0.5.0.md)

![KHEPRI planetary explorer](examples/khepri/renders/hero.png)

## Included

| Area | Contents |
| --- | --- |
| Factory | Python CLI, PowerShell entry point, bootstrap scripts, specifications, profiles, and tests |
| Pipeline | glTF inspection, validation, optimization, Three.js previews, QA reports, and transactional publication |
| Knowledge | Research, provenance, design documents, lessons, and active project state |
| KHEPRI explorer | Blender source, GLB, concept blueprint, five renders, and repeatable geometry checks |

The factory originated with PS1-era WWII profiles. KHEPRI is a separate science-fiction example; its design decisions do not replace the factory's general rules.

## Quick start

Open [khepri-explorer.blend](examples/khepri/source/khepri-explorer.blend) in **Blender 5.2 LTS** to inspect the rover. Its concept blueprint is packed into the file.

For the factory on Windows, run from the repository root:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\bootstrap\setup.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\factory.ps1 doctor --json
powershell -NoProfile -ExecutionPolicy Bypass -File .\factory.ps1 resume --json
```

Bootstrap downloads local tooling. Model weights and optional creative applications are separate installations. Read [Getting started](docs/GETTING_STARTED.md) before production work.

## Release status

**0.5.0 is a development release.** KHEPRI revision 4 includes connected tow fittings, seated rollers, rear axle clearance, attached roof equipment, and a simpler airlock.

Verified in Blender 5.2 LTS:

- 142 hull-attachment checks.
- All 16 lower rollers contacting their belts, plus rear track clearance checks.
- GLB reimport matching source mesh count, triangle count, and bounds.
- Visual inspection of five vehicle and detail renders.

The export contains **451 meshes and 262,776 triangles**, with an approximate envelope of **6.856 × 3.519 × 3.251 m**. Three.js runtime acceptance, LODs, texture baking, and animation-rig validation remain outstanding.

## Repository map

```text
factory/             Core commands and pipeline
bootstrap/           Local dependency setup
scripts/             Generation and supporting tools
profiles/            Style contracts
specs/               Asset specifications
tests/               Factory tests
tools/               Three.js viewer and release utilities
knowledge/           Durable project state and lessons
docs/                Main page, setup, research, release notes
examples/khepri/     Rover source, export, reference, renders, QA
```

Keep source files separate from optimized derivatives. The factory HTTP bridge and the separate Blender MCP add-on use different protocols; see the setup guide.

Local runtimes, credentials, model weights, backups, and generated job directories are excluded from publication. This repository is private; this release grants no open-source license.
