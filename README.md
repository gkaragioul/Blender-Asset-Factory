# Blender Asset Factory

**Development release · 0.5.0**

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
powershell -NoProfile -ExecutionPolicy Bypass -File .\factory.ps1 verify --json
```

Bootstrap downloads local tooling. Model weights and optional creative applications are separate installations. Read [Getting started](docs/GETTING_STARTED.md) before production work.

## Where files go

The factory root is the repository checkout. `factory/config.json` sets the other locations:

| Setting | Default | Contents |
| --- | --- | --- |
| `tooling_root` | `.tooling/` | uv, Python, Node.js, gltfpack, and pinned npm packages installed by bootstrap |
| `reports_root` | `reports/` | Doctor, verification, validation, and preview reports |
| `model_root` | `models/` | Model weights (not bundled) |
| `blender_candidates` | Standard Windows and Linux locations | Where the factory looks for Blender |

To keep model weights elsewhere, set `model_root` to an absolute path before running bootstrap, or pass `-ModelRoot <path>` to `bootstrap\setup.ps1` and set the same value in `factory/config.json`. Bootstrap refuses to write anywhere outside the factory root and the model root. Older design documents in `docs/superpowers/` and some generated manifests still show the original author's `G:\` layout; treat those paths as examples.

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

Local runtimes, credentials, model weights, backups, and generated job directories are not part of the repository.

## What it touches

- **Downloads and runs tools.** `bootstrap\setup.ps1` downloads the uv installer script from `astral.sh` and runs it, then installs Python into `.tooling/`. `bootstrap\setup-release.ps1` downloads Node.js and gltfpack (checked against the SHA-256 values in `tools/manifests/release-toolchain.json`) and runs `npm ci` with install scripts disabled for gltf-validator, playwright-core and three.
- **Starts other programs.** Factory commands run Blender in the background with the factory's Python scripts, run gltfpack and the glTF validator, and start Chrome or Edge headless through playwright-core with a temporary local web server on `127.0.0.1` for previews and contact sheets. `doctor` checks the HTTP bridge on `127.0.0.1:9876`.
- **Writes files** inside the checkout: `.tooling/`, `reports/`, `tmp/`, `projects/`, `products/`, `assets/`, and the state files in `knowledge/`. Bootstrap also creates the model root. Publication moves each finished release package into place in one step, and failed runs delete their own partial output.
- **Changes Blender settings** only when you run `scripts/configure_blender.py`: it enables the `blender_mcp_bridge` add-on, sets its approved script folder to this checkout, and saves your Blender preferences.
- **Paid API (optional).** `scripts/generate_benchmark_concepts.py` reads `BFL_API_KEY` and sends prompts and reference image URLs to the Black Forest Labs API, which bills your account.

## License

- **Code** (Python, PowerShell, JavaScript, schemas, specifications, tests, and documentation) is released under the [MIT License](LICENSE).
- **Example assets** (the `.blend`, `.glb`, and `.png` files in `examples/` and `assets/`, and the KHEPRI concept blueprint and its prompt) are released under [Creative Commons Attribution 4.0 International (CC BY 4.0)](https://creativecommons.org/licenses/by/4.0/). See [LICENSE-ASSETS.md](LICENSE-ASSETS.md) for the list, the suggested credit line, and notes on the AI-generated blueprint.

- **Reference data** in `profiles/ps1_ww2_frontline/references/` is catalog metadata from [Muster](https://github.com/Kenton-GMI/muster-ww2), used under its MIT License; see [THIRD_PARTY_NOTICES.md](profiles/ps1_ww2_frontline/references/THIRD_PARTY_NOTICES.md).

Third-party tools, models, and references named in the documentation are not included and keep their own licences.

## Disclaimer

This software and the example assets are provided "as is", without warranty of any kind, under the MIT License and CC BY 4.0 respectively. Use them at your own risk.

- Bootstrap downloads and runs software from the internet, including an installer script that is not checksum-verified, and runs PowerShell with the execution policy bypassed.
- The factory runs Python code inside Blender and starts a headless browser. Run it only on specifications, scripts, and `.blend` files you trust.
- Factory commands create, replace, and delete files inside the checkout, and `scripts/configure_blender.py` changes your Blender preferences. Keep backups of work you care about.
- Optional providers can send prompts and image URLs to paid third-party services when you supply an API key.
- The example assets are development assets; they have not passed runtime, LOD, or rigging validation.
