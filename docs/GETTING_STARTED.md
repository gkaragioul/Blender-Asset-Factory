# Getting started

## Review the rover

Open `examples/khepri/source/khepri-explorer.blend` in Blender 5.2 LTS. The concept blueprint is packed into the file and also included under `examples/khepri/reference/`.

The export is `examples/khepri/exports/khepri-explorer.glb`. Procedural Blender shading and exported basic PBR materials may render differently in other applications.

## Factory setup

From the repository root on Windows:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\bootstrap\setup.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\factory.ps1 doctor --json
powershell -NoProfile -ExecutionPolicy Bypass -File .\factory.ps1 resume --json
```

Tooling is installed under `.tooling/`. Model weights, ComfyUI, ArmorPaint, and Material Maker are not bundled. Review `factory/config.json` before choosing storage locations.

The configuration resolves the root, tooling, and report paths relative to the checkout, so the repository can live on any drive. Model weights go to `model_root` in `factory/config.json` (default `models/` inside the checkout). To use another folder, set `model_root` to an absolute path before running bootstrap, or pass the same path to bootstrap with `-ModelRoot`:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\bootstrap\setup.ps1 -ModelRoot 'D:\Models'
```

Bootstrap refuses to write outside the factory root and the model root. Some inherited design documents and generated manifests still show the original G: production layout; treat those absolute paths as examples.

A fresh clone needs bootstrap before its doctor can pass. The publication checkout was not independently bootstrapped for this release.

## Blender connections

The factory's `bridge_url` expects its HTTP bridge. KHEPRI was modeled through a separate Blender MCP add-on using a local socket connection. Sharing port 9876 does not make the protocols interchangeable.

For that add-on, follow the upstream [Blender MCP server instructions](https://github.com/djeada/blender-mcp-server). The modeling session used commit `7eed33edf4aca2ab0ca84a6da27321f89f68b504` and MCP Python dependency `1.29.1`. These are provenance details; this repository does not install or bundle the third-party server.

Keep connections on loopback and use approved script directories. Machine-specific MCP settings and account credentials are not included.

## Recheck KHEPRI

Adjust the executable path for your Blender installation:

```powershell
$blender = 'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe'
& $blender --background examples/khepri/source/khepri-explorer.blend --python-exit-code 1 --python examples/khepri/verify_attachments.py
& $blender --background examples/khepri/source/khepri-explorer.blend --python-exit-code 1 --python examples/khepri/verify_tracks.py
& $blender --background examples/khepri/source/khepri-explorer.blend --python-exit-code 1 --python examples/khepri/verify_export.py
```

The scripts update `examples/khepri/qa/`. These are geometry/export checks, not runtime or animation acceptance.

## Review sheet

`review` renders an exported GLB in the pinned Three.js viewer from several angles, measures it, and checks placement and budgets. It needs the release runtime (`.tooling/release-runtime.json`).

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\factory.ps1 review --input assets/ps1_ww2_pump_shotgun_01/ps1_ww2_pump_shotgun_01.glb --output tmp/factory/review/shotgun.png --profile ps1_ww2_frontline --category weapon --json
```

- `--views` picks angles from `q-front, q-front-r, front, left, right, rear, q-rear, q-rear-l, top, bottom, ground, high` (default `q-front,left,front,q-rear,top,ground`).
- `--scale-figure` adds a 1.80 m reference figure.
- `--profile` and `--category` take the triangle band and placement tolerances from the profile. `--expect file.json` adds or overrides keys: `triangles`, `max_draw_calls`, `dimensions` (`width` X, `height` Y, `length` Z in metres), `dimension_tolerance`, `ground_tolerance`, `centre_tolerance` (`null` disables centring).

Conventions: metres at 1:1 scale, +Y up, +Z forward, origin on the ground at the footprint centre. The command exits 1 when a check fails, and the report lists each failure (for example `not_grounded`, `not_centred`, `triangles_above_max`). Real-world dimensions for WW2 subjects are in `profiles/ps1_ww2_frontline/references/muster-ww2-reference-data.json`. Treat them as unverified secondary data. The view angles, scale figure and conventions are adapted from [Muster](https://github.com/Kenton-GMI/muster-ww2) (MIT).

## Continue development

Read `AGENTS.md` and `knowledge/START_HERE.md`. The prior WWII project state is preserved at `knowledge/project-summaries/pre-0.5.0-active-project.json`. KHEPRI's checks do not certify that separate art pipeline.
