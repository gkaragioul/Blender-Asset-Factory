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

The current configuration resolves root and tooling paths relative to the checkout. Some inherited operator documents, `AGENTS.md`, and `FACTORY_ROOT.txt` describe the original G: production layout. These restrictions were not rewritten by this documentation release. Reconcile the trusted checkout/storage contract before production publication or running older absolute-path commands.

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

## Continue development

Read `AGENTS.md` and `knowledge/START_HERE.md`. The prior WWII project state is preserved at `knowledge/project-summaries/pre-0.5.0-active-project.json`. KHEPRI's checks do not certify that separate art pipeline.
