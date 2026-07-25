# PS1 Retro Pipeline Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert any local source mesh into a validated, quality-gated, PS1-era GLB driven entirely by a declarative style contract, with no hosted API involved.

**Architecture:** A style contract holds every style decision; a catalog declares assets by role. Headless Blender performs the PS1 conversion (split, clean, normalize, decimate, bake, quantize, strip). Host-side Python measures the result: Gate 1 checks deterministic properties of the exported GLB, Gate 2 compares silhouette IoU between the raw and converted meshes. A pack orchestrator runs the whole catalog offline from local source files.

**Tech Stack:** Python 3 standard library only (host side), `bpy` plus its bundled numpy (inside Blender), existing `gltfpack` and Khronos glTF Validator via `.tooling/`, `unittest` for tests.

This plan implements phases 0-3 of
`docs/superpowers/specs/2026-07-25-ww2-diorama-kit-pipeline-design.md`.
Phases 4-7 (Sloyd provider, lane B generation, contact sheet approval loop,
provenance ledger, full pack run) are a separate plan, written after Sloyd's
API surface has been read and verified.

## Global Constraints

Every task's requirements implicitly include this section. Values are copied
verbatim from the spec.

- **Tests use `unittest`, not pytest.** Run with
  `python -m unittest tests.test_name -v`. The full suite is
  `python -m unittest discover -s tests -p "test_*.py"`.
- **Temporary directories must be created under `tests/temp_paths.temporary_root()`**
  (`tmp/factory/tests`). Never `TemporaryDirectory(dir="G:\\")`, never the
  drive root. `tests/test_temp_directory_policy.py` enforces this.
- **All JSON writes go through `factory.io.atomic_write_json`.** All text
  writes go through `factory.io.atomic_write_text`. Both already exist.
- **All factory-owned paths must pass `FactoryConfig.require_owned_path`.**
- **`factory/config.json` keys must remain exactly** `schema_version`, `root`,
  `model_root`, `tooling_root`, `reports_root`, `bridge_url`,
  `blender_candidates`. `factory/config.py` rejects any other key set. Do not
  add a key.
- **Style contract values for this pack:** `texture_size` 256, `filtering`
  `nearest`, `grid_unit` 0.5, `up_axis` `Y`, `drop_maps`
  `["normal", "roughness", "metallic"]`, `vertex_light_bake` true, palette 48
  colours.
- **Polycount bands:** `small` 400, `medium` 1000, `large` 2500.
- **Silhouette IoU thresholds:** pass at `>= 0.95`, flag at `>= 0.90` and
  `< 0.95`, reject below `0.90`. Rendered from **8 fixed views**.
- **`retro_pass` must be deterministic:** identical source plus identical
  contract yields a byte-identical GLB.
- **Compression is gltfpack/meshopt only. Never Draco.** Mixing both is the
  blind serial optimization mistake `docs/IDEAL_AI_GAME_ASSET_PIPELINE.md`
  warns against.
- **Host-side code is standard library only.** No numpy, no Pillow outside
  Blender. numpy is available only inside `bpy` scripts.
- **`raw/` is write-once.** No task may modify a file under a `raw/`
  directory after creating it.
- Preserve unrelated dirty work in the tree. `AGENTS.md` requires this. Stage
  only the files a task names.

## File Structure

**Created:**

| File | Responsibility |
|---|---|
| `factory/blender.py` | Locate the Blender executable across platforms; run a Blender script and return its report |
| `factory/style_contract.py` | Load, validate and digest a style contract; resolve role to triangle band |
| `factory/catalog.py` | Load and validate a pack catalog |
| `factory/png.py` | Decode 8-bit non-interlaced PNG to raw RGBA; no third-party dependency |
| `factory/palette.py` | Load a palette PNG, find nearest palette colour, measure palette conformance |
| `factory/silhouette.py` | Compute silhouette masks and intersection-over-union between two render sets |
| `factory/gates.py` | Gate 1 deterministic measurements and Gate 2 IoU verdict |
| `factory/retro.py` | Host-side wrapper that invokes the Blender PS1 pass and returns its report |
| `factory/pack.py` | Orchestrate a catalog over local source meshes |
| `factory/scripts/retro_pass.py` | Blender-side PS1 conversion: split, clean, normalize, decimate, UV, bake, quantize, strip, export |
| `factory/scripts/silhouette_render.py` | Blender-side silhouette renderer: 8 fixed orthographic views, white on black |
| `factory/schemas/style-contract.schema.json` | Style contract schema |
| `factory/schemas/catalog.schema.json` | Catalog schema |
| `tests/fixtures.py` | Extract and cache the `trenchgun.fbx` test fixture on demand |

**Modified:**

| File | Change |
|---|---|
| `factory/config.json` | Add Windows Blender glob patterns to `blender_candidates` |
| `factory/doctor.py:91-104` | Use `factory.blender.discover_blender` instead of inline `is_file` scan |
| `factory/cli.py` | Register the `pack` handler in `_handlers()` |

---

### Task 1: Cross-platform Blender discovery

The repository cannot run on Windows today: `factory/config.json` lists only
`/usr/bin/blender`, `/snap/bin/blender`, `/usr/local/bin/blender`, and
`factory/doctor.py` tests each with `Path.is_file()`. Windows installs Blender
into a version-named directory, so a literal path cannot be pinned. Discovery
must expand glob patterns and consult `PATH`.

**Files:**
- Create: `factory/blender.py`
- Modify: `factory/config.json`
- Modify: `factory/doctor.py:91-104`
- Test: `tests/test_blender_discovery.py`

**Interfaces:**
- Consumes: `factory.config.FactoryConfig` (existing), specifically the
  `blender_candidates: tuple[Path, ...]` field.
- Produces:
  - `factory.blender.discover_blender(config: FactoryConfig) -> Path | None`
  - `factory.blender.BlenderError(RuntimeError)`
  - `factory.blender.run_blender_script(config: FactoryConfig, script: Path, payload: dict, report_path: Path) -> dict`

- [ ] **Step 1: Write the failing test**

Create `tests/test_blender_discovery.py`:

```python
import json
import tempfile
import unittest
from pathlib import Path

from factory.blender import discover_blender
from factory.config import FactoryConfig
from tests.temp_paths import temporary_root


def _config_with_candidates(temp: Path, candidates: list[str]) -> FactoryConfig:
    root = temp / "repo"
    (root / "factory").mkdir(parents=True)
    (root / "models").mkdir()
    (root / ".tooling").mkdir()
    (root / "reports").mkdir()
    path = root / "factory" / "config.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "root": ".",
                "model_root": "models",
                "tooling_root": ".tooling",
                "reports_root": "reports",
                "bridge_url": "http://127.0.0.1:9876",
                "blender_candidates": candidates,
            }
        ),
        encoding="utf-8",
    )
    return FactoryConfig.load(path)


class BlenderDiscoveryTest(unittest.TestCase):
    def test_finds_literal_candidate(self):
        with tempfile.TemporaryDirectory(dir=temporary_root()) as temp:
            temp_path = Path(temp)
            installed = temp_path / "bin" / "blender"
            installed.parent.mkdir(parents=True)
            installed.write_text("#!/bin/sh\n", encoding="utf-8")
            config = _config_with_candidates(temp_path, [str(installed)])
            self.assertEqual(discover_blender(config), installed)

    def test_expands_glob_candidate_and_prefers_highest_version(self):
        with tempfile.TemporaryDirectory(dir=temporary_root()) as temp:
            temp_path = Path(temp)
            base = temp_path / "Blender Foundation"
            for version in ("Blender 4.2", "Blender 4.10", "Blender 4.9"):
                target = base / version
                target.mkdir(parents=True)
                (target / "blender.exe").write_text("stub", encoding="utf-8")
            config = _config_with_candidates(
                temp_path, [str(base / "*" / "blender.exe")]
            )
            found = discover_blender(config)
            self.assertEqual(found.parent.name, "Blender 4.10")

    def test_returns_none_when_nothing_matches(self):
        with tempfile.TemporaryDirectory(dir=temporary_root()) as temp:
            temp_path = Path(temp)
            config = _config_with_candidates(
                temp_path, [str(temp_path / "absent" / "blender")]
            )
            self.assertIsNone(discover_blender(config))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_blender_discovery -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'factory.blender'`

- [ ] **Step 3: Write minimal implementation**

Create `factory/blender.py`:

```python
from __future__ import annotations

import glob
import json
import re
import shutil
import subprocess
from pathlib import Path

from .config import FactoryConfig
from .io import atomic_write_json


class BlenderError(RuntimeError):
    pass


_VERSION = re.compile(r"(\d+)(?:\.(\d+))?")


def _version_key(path: Path) -> tuple[int, int]:
    match = _VERSION.search(path.parent.name) or _VERSION.search(path.name)
    if not match:
        return (0, 0)
    return (int(match.group(1)), int(match.group(2) or 0))


def discover_blender(config: FactoryConfig) -> Path | None:
    matches: list[Path] = []
    for candidate in config.blender_candidates:
        text = str(candidate)
        if any(character in text for character in "*?["):
            matches.extend(Path(item) for item in glob.glob(text))
        elif candidate.is_file():
            matches.append(candidate)
    if not matches:
        found = shutil.which("blender")
        if found:
            matches.append(Path(found))
    if not matches:
        return None
    return sorted(matches, key=_version_key, reverse=True)[0]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_blender_discovery -v`
Expected: PASS, 3 tests

- [ ] **Step 5: Add the Blender script runner**

Append to `factory/blender.py`:

```python
def run_blender_script(
    config: FactoryConfig,
    script: Path,
    payload: dict,
    report_path: Path,
) -> dict:
    executable = discover_blender(config)
    if executable is None:
        raise BlenderError("no Blender executable was discovered")
    config.require_owned_path(report_path)
    payload_path = report_path.with_name(report_path.name + ".payload.json")
    atomic_write_json(payload_path, payload)
    command = [
        str(executable),
        "--background",
        "--factory-startup",
        "--python",
        str(script),
        "--",
        "--payload",
        str(payload_path),
        "--report",
        str(report_path),
    ]
    completed = subprocess.run(command, capture_output=True, text=True)
    if not report_path.is_file():
        raise BlenderError(
            "Blender produced no report\n"
            f"exit={completed.returncode}\n"
            f"stdout={completed.stdout[-4000:]}\n"
            f"stderr={completed.stderr[-4000:]}"
        )
    return json.loads(report_path.read_text(encoding="utf-8"))
```

`--factory-startup` is required for determinism: it prevents user preferences
and enabled add-ons from altering export behaviour between machines.

- [ ] **Step 6: Add Windows glob patterns to config**

Modify `factory/config.json`, replacing only the `blender_candidates` value.
Do not add or remove any other key.

```json
  "blender_candidates": [
    "/usr/bin/blender",
    "/snap/bin/blender",
    "/usr/local/bin/blender",
    "C:/Program Files/Blender Foundation/*/blender.exe",
    "C:/Program Files/Blender Foundation/Blender/blender.exe"
  ]
```

- [ ] **Step 7: Switch doctor to the discovery function**

In `factory/doctor.py`, add `from .blender import discover_blender` to the
imports, then replace lines 91-93:

```python
    blender = next(
        (path for path in config.blender_candidates if path.is_file()), None
    )
```

with:

```python
    blender = discover_blender(config)
```

Leave the surrounding `if blender:` / `except` / `else` block unchanged.

- [ ] **Step 8: Verify doctor reports Blender available on this host**

Run: `python -m unittest tests.test_doctor -v`
Expected: PASS

Run: `.\factory.ps1 doctor`
Expected: `blender` capability status is `available` with a real
`C:/Program Files/Blender Foundation/...` path.

If `blender` is still `unavailable`, Blender is not installed at the expected
location. Find it with
`Get-Command blender` or
`Get-ChildItem "C:\Program Files\Blender Foundation" -Recurse -Filter blender.exe`
and add that literal path to `blender_candidates` before continuing. Do not
proceed to Task 2 until doctor reports `available`.

- [ ] **Step 9: Commit**

```bash
git add factory/blender.py factory/config.json factory/doctor.py tests/test_blender_discovery.py
git commit -m "feat: discover blender across platforms"
```

---

### Task 2: Style contract

All style decisions live in one file so a pack can be restyled by editing a
single value. The contract's digest feeds the determinism guarantee and later
the generation cache key.

**Files:**
- Create: `factory/style_contract.py`
- Create: `factory/schemas/style-contract.schema.json`
- Test: `tests/test_style_contract.py`

**Interfaces:**
- Consumes: `factory.config.FactoryConfig`, `factory.io.sha256_file`.
- Produces:
  - `factory.style_contract.StyleContract` — frozen dataclass with fields
    `palette: Path`, `texture_size: int`, `filtering: str`,
    `polycount_bands: tuple[tuple[str, int], ...]`, `grid_unit: float`,
    `up_axis: str`, `drop_maps: tuple[str, ...]`, `vertex_light_bake: bool`
  - `StyleContract.load(config: FactoryConfig, path: Path) -> StyleContract`
  - `StyleContract.band_for(role: str) -> int`
  - `StyleContract.digest() -> str` (64-character sha256 hex)
  - `StyleContract.as_payload() -> dict` (JSON-safe, for the Blender script)
  - `factory.style_contract.StyleContractError(ValueError)`

`polycount_bands` is a sorted tuple of pairs rather than a dict so the
dataclass stays hashable and the digest is order-independent.

- [ ] **Step 1: Write the failing test**

Create `tests/test_style_contract.py`:

```python
import json
import tempfile
import unittest
from pathlib import Path

from factory.config import FactoryConfig
from factory.style_contract import StyleContract, StyleContractError
from tests.temp_paths import temporary_root

CONTRACT = {
    "schema_version": 1,
    "palette": "palettes/ww2_field_48.png",
    "texture_size": 256,
    "filtering": "nearest",
    "polycount_bands": {"small": 400, "medium": 1000, "large": 2500},
    "grid_unit": 0.5,
    "up_axis": "Y",
    "drop_maps": ["normal", "roughness", "metallic"],
    "vertex_light_bake": True,
}


class StyleContractTest(unittest.TestCase):
    def setUp(self):
        self.config = FactoryConfig.load()

    def _write(self, temp: Path, overrides: dict | None = None) -> Path:
        data = dict(CONTRACT)
        data.update(overrides or {})
        palette = temp / "palettes" / "ww2_field_48.png"
        palette.parent.mkdir(parents=True, exist_ok=True)
        palette.write_bytes(b"\x89PNG\r\n\x1a\n")
        path = temp / "contract.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def test_resolves_band_for_role(self):
        with tempfile.TemporaryDirectory(dir=temporary_root()) as temp:
            contract = StyleContract.load(self.config, self._write(Path(temp)))
            self.assertEqual(contract.band_for("small"), 400)
            self.assertEqual(contract.band_for("medium"), 1000)
            self.assertEqual(contract.band_for("large"), 2500)

    def test_rejects_unknown_role(self):
        with tempfile.TemporaryDirectory(dir=temporary_root()) as temp:
            contract = StyleContract.load(self.config, self._write(Path(temp)))
            with self.assertRaisesRegex(StyleContractError, "unknown role"):
                contract.band_for("gigantic")

    def test_rejects_non_nearest_filtering(self):
        with tempfile.TemporaryDirectory(dir=temporary_root()) as temp:
            path = self._write(Path(temp), {"filtering": "linear"})
            with self.assertRaisesRegex(StyleContractError, "filtering"):
                StyleContract.load(self.config, path)

    def test_rejects_missing_palette_file(self):
        with tempfile.TemporaryDirectory(dir=temporary_root()) as temp:
            path = self._write(Path(temp), {"palette": "palettes/absent.png"})
            with self.assertRaisesRegex(StyleContractError, "palette"):
                StyleContract.load(self.config, path)

    def test_digest_is_stable_and_sensitive_to_content(self):
        with tempfile.TemporaryDirectory(dir=temporary_root()) as temp:
            temp_path = Path(temp)
            first = StyleContract.load(self.config, self._write(temp_path))
            second = StyleContract.load(self.config, self._write(temp_path))
            self.assertEqual(first.digest(), second.digest())
            self.assertEqual(len(first.digest()), 64)
            changed = StyleContract.load(
                self.config, self._write(temp_path, {"texture_size": 128})
            )
            self.assertNotEqual(first.digest(), changed.digest())


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_style_contract -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'factory.style_contract'`

- [ ] **Step 3: Write minimal implementation**

Create `factory/style_contract.py`:

```python
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from .config import FactoryConfig

ALLOWED_DROP_MAPS = ("normal", "roughness", "metallic", "emissive", "occlusion")
REQUIRED_KEYS = {
    "schema_version",
    "palette",
    "texture_size",
    "filtering",
    "polycount_bands",
    "grid_unit",
    "up_axis",
    "drop_maps",
    "vertex_light_bake",
}


class StyleContractError(ValueError):
    pass


@dataclass(frozen=True)
class StyleContract:
    palette: Path
    texture_size: int
    filtering: str
    polycount_bands: tuple[tuple[str, int], ...]
    grid_unit: float
    up_axis: str
    drop_maps: tuple[str, ...]
    vertex_light_bake: bool

    @classmethod
    def load(cls, config: FactoryConfig, path: Path) -> "StyleContract":
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        if data.keys() != REQUIRED_KEYS:
            raise StyleContractError(
                f"style contract keys must be exactly {sorted(REQUIRED_KEYS)}"
            )
        if data["schema_version"] != 1:
            raise StyleContractError("style contract schema_version must be 1")
        if data["filtering"] != "nearest":
            raise StyleContractError("filtering must be 'nearest' for PS1 packs")
        if data["up_axis"] not in ("Y", "Z"):
            raise StyleContractError("up_axis must be 'Y' or 'Z'")
        if data["texture_size"] not in (64, 128, 256, 512):
            raise StyleContractError("texture_size must be 64, 128, 256 or 512")
        if not isinstance(data["polycount_bands"], dict) or not data["polycount_bands"]:
            raise StyleContractError("polycount_bands must be a non-empty object")
        for role, budget in data["polycount_bands"].items():
            if not isinstance(budget, int) or budget < 1:
                raise StyleContractError(f"band for role {role!r} must be a positive integer")
        for name in data["drop_maps"]:
            if name not in ALLOWED_DROP_MAPS:
                raise StyleContractError(f"unknown drop map {name!r}")
        if float(data["grid_unit"]) <= 0:
            raise StyleContractError("grid_unit must be positive")

        palette = (path.parent / data["palette"]).resolve(strict=False)
        if not palette.is_file():
            raise StyleContractError(f"palette file does not exist: {palette}")

        return cls(
            palette=palette,
            texture_size=data["texture_size"],
            filtering=data["filtering"],
            polycount_bands=tuple(sorted(data["polycount_bands"].items())),
            grid_unit=float(data["grid_unit"]),
            up_axis=data["up_axis"],
            drop_maps=tuple(sorted(data["drop_maps"])),
            vertex_light_bake=bool(data["vertex_light_bake"]),
        )

    def band_for(self, role: str) -> int:
        for name, budget in self.polycount_bands:
            if name == role:
                return budget
        raise StyleContractError(
            f"unknown role {role!r}; known roles are "
            f"{[name for name, _ in self.polycount_bands]}"
        )

    def as_payload(self) -> dict:
        return {
            "texture_size": self.texture_size,
            "filtering": self.filtering,
            "polycount_bands": {name: budget for name, budget in self.polycount_bands},
            "grid_unit": self.grid_unit,
            "up_axis": self.up_axis,
            "drop_maps": list(self.drop_maps),
            "vertex_light_bake": self.vertex_light_bake,
        }

    def digest(self) -> str:
        material = json.dumps(self.as_payload(), sort_keys=True).encode("utf-8")
        palette_bytes = self.palette.read_bytes()
        return hashlib.sha256(material + palette_bytes).hexdigest()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_style_contract -v`
Expected: PASS, 5 tests

- [ ] **Step 5: Write the schema file**

Create `factory/schemas/style-contract.schema.json`:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "Factory style contract",
  "type": "object",
  "additionalProperties": false,
  "required": [
    "schema_version",
    "palette",
    "texture_size",
    "filtering",
    "polycount_bands",
    "grid_unit",
    "up_axis",
    "drop_maps",
    "vertex_light_bake"
  ],
  "properties": {
    "schema_version": { "const": 1 },
    "palette": { "type": "string", "minLength": 1 },
    "texture_size": { "enum": [64, 128, 256, 512] },
    "filtering": { "const": "nearest" },
    "polycount_bands": {
      "type": "object",
      "minProperties": 1,
      "additionalProperties": { "type": "integer", "minimum": 1 }
    },
    "grid_unit": { "type": "number", "exclusiveMinimum": 0 },
    "up_axis": { "enum": ["Y", "Z"] },
    "drop_maps": {
      "type": "array",
      "items": {
        "enum": ["normal", "roughness", "metallic", "emissive", "occlusion"]
      },
      "uniqueItems": true
    },
    "vertex_light_bake": { "type": "boolean" }
  }
}
```

- [ ] **Step 6: Commit**

```bash
git add factory/style_contract.py factory/schemas/style-contract.schema.json tests/test_style_contract.py
git commit -m "feat: load and digest pack style contracts"
```

---

### Task 3: Pack catalog

**Files:**
- Create: `factory/catalog.py`
- Create: `factory/schemas/catalog.schema.json`
- Test: `tests/test_catalog.py`

**Interfaces:**
- Consumes: `factory.style_contract.StyleContract` (for role validation).
- Produces:
  - `factory.catalog.CatalogEntry` — frozen dataclass with `id: str`,
    `lane: str`, `role: str`, `prompt: str | None`,
    `reference_brief: str | None`
  - `factory.catalog.Catalog` — frozen dataclass with `pack_id: str`,
    `style_contract: Path`, `max_generations: int`, `max_rerolls: int`,
    `entries: tuple[CatalogEntry, ...]`
  - `Catalog.load(config: FactoryConfig, path: Path, contract: StyleContract) -> Catalog`
  - `factory.catalog.CatalogError(ValueError)`

- [ ] **Step 1: Write the failing test**

Create `tests/test_catalog.py`:

```python
import json
import tempfile
import unittest
from pathlib import Path

from factory.catalog import Catalog, CatalogError
from factory.config import FactoryConfig
from factory.style_contract import StyleContract
from tests.temp_paths import temporary_root

CONTRACT = {
    "schema_version": 1,
    "palette": "palettes/p.png",
    "texture_size": 256,
    "filtering": "nearest",
    "polycount_bands": {"small": 400, "medium": 1000, "large": 2500},
    "grid_unit": 0.5,
    "up_axis": "Y",
    "drop_maps": ["normal", "roughness", "metallic"],
    "vertex_light_bake": True,
}


class CatalogTest(unittest.TestCase):
    def setUp(self):
        self.config = FactoryConfig.load()

    def _contract(self, temp: Path) -> StyleContract:
        palette = temp / "palettes" / "p.png"
        palette.parent.mkdir(parents=True, exist_ok=True)
        palette.write_bytes(b"\x89PNG\r\n\x1a\n")
        path = temp / "contract.json"
        path.write_text(json.dumps(CONTRACT), encoding="utf-8")
        return StyleContract.load(self.config, path)

    def _write(self, temp: Path, assets: list[dict]) -> Path:
        path = temp / "catalog.json"
        path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "pack_id": "ww2_diorama_kit_01",
                    "style_contract": "contract.json",
                    "max_generations": 200,
                    "max_rerolls": 3,
                    "assets": assets,
                }
            ),
            encoding="utf-8",
        )
        return path

    def test_loads_lane_a_and_lane_b_entries(self):
        with tempfile.TemporaryDirectory(dir=temporary_root()) as temp:
            temp_path = Path(temp)
            contract = self._contract(temp_path)
            path = self._write(
                temp_path,
                [
                    {
                        "id": "ammo_crate_closed",
                        "lane": "A",
                        "role": "small",
                        "prompt": "wooden military ammunition crate closed lid",
                    },
                    {
                        "id": "stahlhelm",
                        "lane": "B",
                        "role": "medium",
                        "reference_brief": "German M35 Stahlhelm, three-quarter view",
                    },
                ],
            )
            catalog = Catalog.load(self.config, path, contract)
            self.assertEqual(catalog.pack_id, "ww2_diorama_kit_01")
            self.assertEqual(catalog.max_rerolls, 3)
            self.assertEqual(len(catalog.entries), 2)
            self.assertEqual(catalog.entries[0].prompt.split()[0], "wooden")
            self.assertIsNone(catalog.entries[1].prompt)

    def test_rejects_lane_a_without_prompt(self):
        with tempfile.TemporaryDirectory(dir=temporary_root()) as temp:
            temp_path = Path(temp)
            contract = self._contract(temp_path)
            path = self._write(
                temp_path,
                [{"id": "crate", "lane": "A", "role": "small",
                  "reference_brief": "wrong field for lane A"}],
            )
            with self.assertRaisesRegex(CatalogError, "lane A"):
                Catalog.load(self.config, path, contract)

    def test_rejects_lane_b_without_reference_brief(self):
        with tempfile.TemporaryDirectory(dir=temporary_root()) as temp:
            temp_path = Path(temp)
            contract = self._contract(temp_path)
            path = self._write(
                temp_path,
                [{"id": "helmet", "lane": "B", "role": "medium",
                  "prompt": "wrong field for lane B"}],
            )
            with self.assertRaisesRegex(CatalogError, "lane B"):
                Catalog.load(self.config, path, contract)

    def test_rejects_role_absent_from_contract(self):
        with tempfile.TemporaryDirectory(dir=temporary_root()) as temp:
            temp_path = Path(temp)
            contract = self._contract(temp_path)
            path = self._write(
                temp_path,
                [{"id": "crate", "lane": "A", "role": "colossal", "prompt": "a crate"}],
            )
            with self.assertRaisesRegex(CatalogError, "colossal"):
                Catalog.load(self.config, path, contract)

    def test_rejects_duplicate_asset_ids(self):
        with tempfile.TemporaryDirectory(dir=temporary_root()) as temp:
            temp_path = Path(temp)
            contract = self._contract(temp_path)
            path = self._write(
                temp_path,
                [
                    {"id": "crate", "lane": "A", "role": "small", "prompt": "a crate"},
                    {"id": "crate", "lane": "A", "role": "small", "prompt": "a crate"},
                ],
            )
            with self.assertRaisesRegex(CatalogError, "duplicate"):
                Catalog.load(self.config, path, contract)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_catalog -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'factory.catalog'`

- [ ] **Step 3: Write minimal implementation**

Create `factory/catalog.py`:

```python
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .config import FactoryConfig
from .style_contract import StyleContract, StyleContractError

REQUIRED_KEYS = {
    "schema_version",
    "pack_id",
    "style_contract",
    "max_generations",
    "max_rerolls",
    "assets",
}
IDENTIFIER = "abcdefghijklmnopqrstuvwxyz0123456789_"


class CatalogError(ValueError):
    pass


@dataclass(frozen=True)
class CatalogEntry:
    id: str
    lane: str
    role: str
    prompt: str | None
    reference_brief: str | None


@dataclass(frozen=True)
class Catalog:
    pack_id: str
    style_contract: Path
    max_generations: int
    max_rerolls: int
    entries: tuple[CatalogEntry, ...]

    @classmethod
    def load(
        cls,
        config: FactoryConfig,
        path: Path,
        contract: StyleContract,
    ) -> "Catalog":
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        if data.keys() != REQUIRED_KEYS:
            raise CatalogError(f"catalog keys must be exactly {sorted(REQUIRED_KEYS)}")
        if data["schema_version"] != 1:
            raise CatalogError("catalog schema_version must be 1")
        if set(data["pack_id"]) - set(IDENTIFIER):
            raise CatalogError("pack_id must be lowercase alphanumeric with underscores")
        for field in ("max_generations", "max_rerolls"):
            if not isinstance(data[field], int) or data[field] < 1:
                raise CatalogError(f"{field} must be a positive integer")
        if not data["assets"]:
            raise CatalogError("catalog must declare at least one asset")

        entries: list[CatalogEntry] = []
        seen: set[str] = set()
        for asset in data["assets"]:
            identifier = asset.get("id", "")
            if not identifier or set(identifier) - set(IDENTIFIER):
                raise CatalogError(f"invalid asset id {identifier!r}")
            if identifier in seen:
                raise CatalogError(f"duplicate asset id {identifier!r}")
            seen.add(identifier)

            lane = asset.get("lane")
            if lane not in ("A", "B"):
                raise CatalogError(f"asset {identifier!r} lane must be 'A' or 'B'")

            role = asset.get("role", "")
            try:
                contract.band_for(role)
            except StyleContractError as error:
                raise CatalogError(
                    f"asset {identifier!r} role {role!r} is not in the style contract: {error}"
                ) from error

            prompt = asset.get("prompt")
            brief = asset.get("reference_brief")
            if lane == "A" and (not prompt or brief):
                raise CatalogError(
                    f"asset {identifier!r} is lane A and must declare 'prompt' "
                    "and must not declare 'reference_brief'"
                )
            if lane == "B" and (not brief or prompt):
                raise CatalogError(
                    f"asset {identifier!r} is lane B and must declare "
                    "'reference_brief' and must not declare 'prompt'"
                )

            unexpected = set(asset) - {"id", "lane", "role", "prompt", "reference_brief"}
            if unexpected:
                raise CatalogError(
                    f"asset {identifier!r} has unexpected keys {sorted(unexpected)}"
                )

            entries.append(
                CatalogEntry(
                    id=identifier,
                    lane=lane,
                    role=role,
                    prompt=prompt,
                    reference_brief=brief,
                )
            )

        return cls(
            pack_id=data["pack_id"],
            style_contract=(path.parent / data["style_contract"]).resolve(strict=False),
            max_generations=data["max_generations"],
            max_rerolls=data["max_rerolls"],
            entries=tuple(entries),
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_catalog -v`
Expected: PASS, 5 tests

- [ ] **Step 5: Write the schema file**

Create `factory/schemas/catalog.schema.json`:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "Factory pack catalog",
  "type": "object",
  "additionalProperties": false,
  "required": [
    "schema_version",
    "pack_id",
    "style_contract",
    "max_generations",
    "max_rerolls",
    "assets"
  ],
  "properties": {
    "schema_version": { "const": 1 },
    "pack_id": { "type": "string", "pattern": "^[a-z0-9_]+$" },
    "style_contract": { "type": "string", "minLength": 1 },
    "max_generations": { "type": "integer", "minimum": 1 },
    "max_rerolls": { "type": "integer", "minimum": 1 },
    "assets": {
      "type": "array",
      "minItems": 1,
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["id", "lane", "role"],
        "properties": {
          "id": { "type": "string", "pattern": "^[a-z0-9_]+$" },
          "lane": { "enum": ["A", "B"] },
          "role": { "type": "string", "minLength": 1 },
          "prompt": { "type": "string", "minLength": 1 },
          "reference_brief": { "type": "string", "minLength": 1 }
        }
      }
    }
  }
}
```

- [ ] **Step 6: Commit**

```bash
git add factory/catalog.py factory/schemas/catalog.schema.json tests/test_catalog.py
git commit -m "feat: validate pack catalogs against the style contract"
```

---

### Task 4: PNG decoding and palette conformance

Gate 1 must prove that every pixel of a shipped texture is a member of the
pack palette. That requires reading PNG bytes host-side, and the host side is
standard library only, so a small decoder is needed. Scope is deliberately
narrow: the factory produces these PNGs itself, so only 8-bit non-interlaced
RGB and RGBA need support.

**Files:**
- Create: `factory/png.py`
- Create: `factory/palette.py`
- Test: `tests/test_png.py`
- Test: `tests/test_palette.py`

**Interfaces:**
- Consumes: `tests.glb_fixture` helpers are **not** reused here; this task
  builds its own PNG bytes in the test.
- Produces:
  - `factory.png.decode_rgba(data: bytes) -> tuple[int, int, bytes]` returning
    `(width, height, rgba_bytes)` where `rgba_bytes` has length
    `width * height * 4`
  - `factory.png.encode_rgba(width: int, height: int, rgba: bytes) -> bytes`
  - `factory.png.PngError(ValueError)`
  - `factory.palette.load_palette(path: Path) -> tuple[tuple[int, int, int], ...]`
  - `factory.palette.nearest(colour: tuple[int, int, int], palette) -> tuple[int, int, int]`
  - `factory.palette.conformance(png_bytes: bytes, palette) -> dict` returning
    `{"ok": bool, "pixels": int, "foreign_pixels": int, "foreign_colours": list}`
  - `factory.palette.PaletteError(ValueError)`

- [ ] **Step 1: Write the failing PNG test**

Create `tests/test_png.py`:

```python
import unittest

from factory.png import PngError, decode_rgba, encode_rgba


class PngRoundTripTest(unittest.TestCase):
    def test_round_trips_rgba_pixels(self):
        width, height = 3, 2
        rgba = bytes(
            [
                255, 0, 0, 255,   0, 255, 0, 255,   0, 0, 255, 255,
                10, 20, 30, 255,  40, 50, 60, 255,  70, 80, 90, 255,
            ]
        )
        encoded = encode_rgba(width, height, rgba)
        self.assertEqual(encoded[:8], b"\x89PNG\r\n\x1a\n")
        self.assertEqual(decode_rgba(encoded), (width, height, rgba))

    def test_rejects_non_png_data(self):
        with self.assertRaisesRegex(PngError, "signature"):
            decode_rgba(b"not a png at all")

    def test_rejects_wrong_pixel_buffer_length(self):
        with self.assertRaisesRegex(PngError, "length"):
            encode_rgba(2, 2, b"\x00\x00\x00")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_png -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'factory.png'`

- [ ] **Step 3: Implement the PNG codec**

Create `factory/png.py`:

```python
from __future__ import annotations

import binascii
import struct
import zlib

SIGNATURE = b"\x89PNG\r\n\x1a\n"
_CHANNELS = {2: 3, 6: 4}


class PngError(ValueError):
    pass


def _chunk(kind: bytes, payload: bytes) -> bytes:
    return (
        struct.pack(">I", len(payload))
        + kind
        + payload
        + struct.pack(">I", binascii.crc32(kind + payload) & 0xFFFFFFFF)
    )


def encode_rgba(width: int, height: int, rgba: bytes) -> bytes:
    if len(rgba) != width * height * 4:
        raise PngError(
            f"pixel buffer length {len(rgba)} does not match {width}x{height} RGBA"
        )
    stride = width * 4
    raw = b"".join(
        b"\x00" + rgba[row * stride : (row + 1) * stride] for row in range(height)
    )
    header = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    return (
        SIGNATURE
        + _chunk(b"IHDR", header)
        + _chunk(b"IDAT", zlib.compress(raw, 9))
        + _chunk(b"IEND", b"")
    )


def _unfilter(raw: bytes, width: int, height: int, channels: int) -> bytes:
    stride = width * channels
    out = bytearray(height * stride)
    previous = bytearray(stride)
    position = 0
    for row in range(height):
        filter_type = raw[position]
        position += 1
        line = bytearray(raw[position : position + stride])
        position += stride
        if filter_type == 1:
            for index in range(channels, stride):
                line[index] = (line[index] + line[index - channels]) & 0xFF
        elif filter_type == 2:
            for index in range(stride):
                line[index] = (line[index] + previous[index]) & 0xFF
        elif filter_type == 3:
            for index in range(stride):
                left = line[index - channels] if index >= channels else 0
                line[index] = (line[index] + ((left + previous[index]) >> 1)) & 0xFF
        elif filter_type == 4:
            for index in range(stride):
                left = line[index - channels] if index >= channels else 0
                upper_left = previous[index - channels] if index >= channels else 0
                up = previous[index]
                estimate = left + up - upper_left
                deltas = (
                    abs(estimate - left),
                    abs(estimate - up),
                    abs(estimate - upper_left),
                )
                nearest = (left, up, upper_left)[deltas.index(min(deltas))]
                line[index] = (line[index] + nearest) & 0xFF
        elif filter_type != 0:
            raise PngError(f"unsupported PNG filter type {filter_type}")
        out[row * stride : (row + 1) * stride] = line
        previous = line
    return bytes(out)


def decode_rgba(data: bytes) -> tuple[int, int, bytes]:
    if not data.startswith(SIGNATURE):
        raise PngError("data does not begin with a PNG signature")
    position = len(SIGNATURE)
    header: tuple | None = None
    compressed = bytearray()
    while position < len(data):
        (length,) = struct.unpack(">I", data[position : position + 4])
        kind = data[position + 4 : position + 8]
        payload = data[position + 8 : position + 8 + length]
        position += 12 + length
        if kind == b"IHDR":
            header = struct.unpack(">IIBBBBB", payload)
        elif kind == b"IDAT":
            compressed.extend(payload)
        elif kind == b"IEND":
            break
    if header is None:
        raise PngError("PNG has no IHDR chunk")
    width, height, depth, colour_type, _compression, _filter, interlace = header
    if depth != 8:
        raise PngError(f"only 8-bit PNGs are supported, got {depth}")
    if interlace != 0:
        raise PngError("interlaced PNGs are not supported")
    if colour_type not in _CHANNELS:
        raise PngError(f"unsupported PNG colour type {colour_type}")
    channels = _CHANNELS[colour_type]
    pixels = _unfilter(zlib.decompress(bytes(compressed)), width, height, channels)
    if channels == 4:
        return width, height, pixels
    rgba = bytearray(width * height * 4)
    for index in range(width * height):
        rgba[index * 4 : index * 4 + 3] = pixels[index * 3 : index * 3 + 3]
        rgba[index * 4 + 3] = 255
    return width, height, bytes(rgba)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_png -v`
Expected: PASS, 3 tests

- [ ] **Step 5: Write the failing palette test**

Create `tests/test_palette.py`:

```python
import tempfile
import unittest
from pathlib import Path

from factory.palette import PaletteError, conformance, load_palette, nearest
from factory.png import encode_rgba
from tests.temp_paths import temporary_root

RED = (255, 0, 0)
GREEN = (0, 255, 0)
BLUE = (0, 0, 255)


def _png(colours: list[tuple[int, int, int]]) -> bytes:
    rgba = bytearray()
    for colour in colours:
        rgba.extend((*colour, 255))
    return encode_rgba(len(colours), 1, bytes(rgba))


class PaletteTest(unittest.TestCase):
    def test_loads_unique_colours_in_stable_order(self):
        with tempfile.TemporaryDirectory(dir=temporary_root()) as temp:
            path = Path(temp) / "palette.png"
            path.write_bytes(_png([RED, GREEN, BLUE, RED]))
            self.assertEqual(load_palette(path), (BLUE, GREEN, RED))

    def test_rejects_empty_palette(self):
        with tempfile.TemporaryDirectory(dir=temporary_root()) as temp:
            path = Path(temp) / "palette.png"
            path.write_bytes(encode_rgba(1, 1, bytes((0, 0, 0, 0))))
            with self.assertRaisesRegex(PaletteError, "opaque"):
                load_palette(path)

    def test_nearest_picks_closest_palette_colour(self):
        palette = (RED, GREEN, BLUE)
        self.assertEqual(nearest((250, 10, 10), palette), RED)
        self.assertEqual(nearest((10, 10, 240), palette), BLUE)

    def test_conformance_passes_for_in_palette_image(self):
        palette = (RED, GREEN, BLUE)
        report = conformance(_png([RED, GREEN, BLUE]), palette)
        self.assertTrue(report["ok"])
        self.assertEqual(report["foreign_pixels"], 0)
        self.assertEqual(report["pixels"], 3)

    def test_conformance_reports_foreign_colours(self):
        palette = (RED, GREEN)
        report = conformance(_png([RED, (7, 7, 7), (7, 7, 7)]), palette)
        self.assertFalse(report["ok"])
        self.assertEqual(report["foreign_pixels"], 2)
        self.assertEqual(report["foreign_colours"], [[7, 7, 7]])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 6: Run test to verify it fails**

Run: `python -m unittest tests.test_palette -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'factory.palette'`

- [ ] **Step 7: Implement the palette module**

Create `factory/palette.py`:

```python
from __future__ import annotations

from collections import Counter
from pathlib import Path

from .png import decode_rgba

Colour = tuple[int, int, int]
MAX_FOREIGN_COLOURS_REPORTED = 16


class PaletteError(ValueError):
    pass


def load_palette(path: Path) -> tuple[Colour, ...]:
    _width, _height, rgba = decode_rgba(path.read_bytes())
    colours = {
        (rgba[index], rgba[index + 1], rgba[index + 2])
        for index in range(0, len(rgba), 4)
        if rgba[index + 3] == 255
    }
    if not colours:
        raise PaletteError(f"palette {path} contains no opaque pixels")
    return tuple(sorted(colours))


def nearest(colour: Colour, palette: tuple[Colour, ...]) -> Colour:
    def distance(candidate: Colour) -> int:
        return sum((a - b) ** 2 for a, b in zip(colour, candidate))

    return min(palette, key=distance)


def conformance(png_bytes: bytes, palette: tuple[Colour, ...]) -> dict:
    _width, _height, rgba = decode_rgba(png_bytes)
    allowed = set(palette)
    foreign: Counter[Colour] = Counter()
    total = len(rgba) // 4
    for index in range(0, len(rgba), 4):
        colour = (rgba[index], rgba[index + 1], rgba[index + 2])
        if colour not in allowed:
            foreign[colour] += 1
    return {
        "ok": not foreign,
        "pixels": total,
        "foreign_pixels": sum(foreign.values()),
        "foreign_colours": [
            list(colour)
            for colour, _count in foreign.most_common(MAX_FOREIGN_COLOURS_REPORTED)
        ],
    }
```

- [ ] **Step 8: Run test to verify it passes**

Run: `python -m unittest tests.test_palette -v`
Expected: PASS, 5 tests

- [ ] **Step 9: Commit**

```bash
git add factory/png.py factory/palette.py tests/test_png.py tests/test_palette.py
git commit -m "feat: measure texture palette conformance"
```

---

### Task 5: Test fixture harness

Later tasks need a real dense, part-separated, textured mesh. The repository
already contains one:
`../.hermes/desktop-attachments/m1897-trenchgun.zip` holds
`source/trenchgun.fbx` (1.9 MB) with 4K PBR maps and parts named `Barrel`,
`Receiver`, `ReceiverInternals`, `Stock`, `BarrelAttachment`, `Cartridge`.

It is 62 MB extracted, so it must not be committed. It extracts into
`tmp/factory/`, which `.gitignore` already excludes.

**Its licence is unverified.** It is a test fixture only. Do not copy it into
`assets/`, `products/` or `dist/`, and do not ship it.

**Files:**
- Create: `tests/fixtures.py`
- Test: `tests/test_fixtures.py`

**Interfaces:**
- Produces:
  - `tests.fixtures.trenchgun_fbx() -> Path` — extracts on first call, caches,
    returns the path to `trenchgun.fbx`
  - `tests.fixtures.FixtureUnavailable(unittest.SkipTest)`

- [ ] **Step 1: Write the failing test**

Create `tests/test_fixtures.py`:

```python
import unittest

from tests.fixtures import FixtureUnavailable, trenchgun_fbx


class FixtureHarnessTest(unittest.TestCase):
    def test_extracts_trenchgun_fixture(self):
        try:
            path = trenchgun_fbx()
        except FixtureUnavailable as error:
            self.skipTest(str(error))
        self.assertTrue(path.is_file())
        self.assertEqual(path.name, "trenchgun.fbx")
        self.assertGreater(path.stat().st_size, 1_000_000)

    def test_second_call_reuses_extraction(self):
        try:
            first = trenchgun_fbx()
        except FixtureUnavailable as error:
            self.skipTest(str(error))
        stamp = first.stat().st_mtime_ns
        self.assertEqual(trenchgun_fbx().stat().st_mtime_ns, stamp)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_fixtures -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'tests.fixtures'`

- [ ] **Step 3: Write minimal implementation**

Create `tests/fixtures.py`:

```python
from __future__ import annotations

import unittest
import zipfile
from pathlib import Path

from tests.temp_paths import temporary_root

ARCHIVE_CANDIDATES = (
    Path(__file__).resolve().parents[2] / ".hermes" / "desktop-attachments" / "m1897-trenchgun.zip",
    Path(__file__).resolve().parents[1] / ".hermes" / "desktop-attachments" / "m1897-trenchgun.zip",
)


class FixtureUnavailable(unittest.SkipTest):
    pass


def trenchgun_fbx() -> Path:
    destination = temporary_root() / "fixtures" / "m1897-trenchgun"
    target = destination / "source" / "trenchgun.fbx"
    if target.is_file():
        return target
    archive = next((path for path in ARCHIVE_CANDIDATES if path.is_file()), None)
    if archive is None:
        raise FixtureUnavailable(
            "m1897-trenchgun.zip was not found; looked in "
            + ", ".join(str(path) for path in ARCHIVE_CANDIDATES)
        )
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as bundle:
        bundle.extractall(destination)
    if not target.is_file():
        raise FixtureUnavailable(f"{archive} does not contain source/trenchgun.fbx")
    return target
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_fixtures -v`
Expected: PASS, 2 tests

- [ ] **Step 5: Commit**

```bash
git add tests/fixtures.py tests/test_fixtures.py
git commit -m "test: extract the trenchgun mesh fixture on demand"
```

---

### Task 6: Blender PS1 pass — geometry stages

Implements stages 1-4 of `retro_pass`: part-aware split, cleanup, normalize,
decimate to band. Texturing follows in Task 7 so each half can be reviewed
and rejected independently.

The script reads a JSON payload and writes a JSON report, matching the
contract `factory.blender.run_blender_script` established in Task 1.

**Files:**
- Create: `factory/scripts/retro_pass.py`
- Test: `tests/test_retro_geometry.py`

**Interfaces:**
- Consumes: `factory.blender.run_blender_script`,
  `factory.style_contract.StyleContract.as_payload`.
- Produces: a Blender script accepting
  `--payload <path> --report <path>` where the payload is
  `{"source": str, "output": str, "role": str, "contract": <as_payload dict>}`
  and the report is
  `{"ok": bool, "stages": {...}, "triangles_in": int, "triangles_out": int, "parts": [str], "bounds": {...}, "error": str | None}`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_retro_geometry.py`:

```python
import tempfile
import unittest
from pathlib import Path

from factory.blender import discover_blender, run_blender_script
from factory.config import FactoryConfig
from factory.style_contract import StyleContract
from tests.fixtures import FixtureUnavailable, trenchgun_fbx
from tests.temp_paths import temporary_root

SCRIPT = Path(__file__).resolve().parents[1] / "factory" / "scripts" / "retro_pass.py"
CONTRACT_PAYLOAD = {
    "texture_size": 256,
    "filtering": "nearest",
    "polycount_bands": {"small": 400, "medium": 1000, "large": 2500},
    "grid_unit": 0.5,
    "up_axis": "Y",
    "drop_maps": ["normal", "roughness", "metallic"],
    "vertex_light_bake": True,
}


class RetroGeometryTest(unittest.TestCase):
    def setUp(self):
        self.config = FactoryConfig.load()
        if discover_blender(self.config) is None:
            self.skipTest("Blender is not available on this host")
        try:
            self.source = trenchgun_fbx()
        except FixtureUnavailable as error:
            self.skipTest(str(error))

    def _run(self, role: str) -> tuple[dict, Path]:
        work = self.config.root / "tmp" / "factory" / "tests" / "retro"
        work.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=work) as temp:
            output = Path(temp) / "out.glb"
            report_path = Path(temp) / "report.json"
            report = run_blender_script(
                self.config,
                SCRIPT,
                {
                    "source": str(self.source),
                    "output": str(output),
                    "role": role,
                    "contract": CONTRACT_PAYLOAD,
                },
                report_path,
            )
            return report, output if output.is_file() else Path()

    def test_decimates_to_large_band(self):
        report, output = self._run("large")
        self.assertTrue(report["ok"], report.get("error"))
        self.assertGreater(report["triangles_in"], 2500)
        self.assertLessEqual(report["triangles_out"], 2500)
        self.assertTrue(output.is_file())

    def test_preserves_semantic_parts(self):
        report, _output = self._run("large")
        self.assertIn("Barrel", report["parts"])
        self.assertIn("Stock", report["parts"])

    def test_normalizes_origin_to_grid(self):
        report, _output = self._run("large")
        for axis in ("x", "y", "z"):
            remainder = abs(report["bounds"]["origin"][axis]) % 0.5
            self.assertTrue(
                remainder < 1e-4 or abs(remainder - 0.5) < 1e-4,
                f"origin {axis} is not snapped to grid: {report['bounds']['origin']}",
            )

    def test_rejects_unknown_role(self):
        report, _output = self._run("colossal")
        self.assertFalse(report["ok"])
        self.assertIn("colossal", report["error"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_retro_geometry -v`
Expected: FAIL — `factory/scripts/retro_pass.py` does not exist, so
`run_blender_script` raises `BlenderError: Blender produced no report`

- [ ] **Step 3: Write the geometry stages**

Create `factory/scripts/retro_pass.py`:

```python
"""PS1 conversion pass. Runs inside Blender.

Invoked as:
    blender --background --factory-startup --python retro_pass.py -- \
        --payload payload.json --report report.json
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector

FLOATER_FRACTION = 0.001


def _arguments() -> tuple[Path, Path]:
    argv = sys.argv[sys.argv.index("--") + 1 :]
    payload = Path(argv[argv.index("--payload") + 1])
    report = Path(argv[argv.index("--report") + 1])
    return payload, report


def _clear_scene() -> None:
    bpy.ops.wm.read_factory_settings(use_empty=True)


def _import_source(source: Path) -> list:
    suffix = source.suffix.lower()
    if suffix == ".fbx":
        bpy.ops.import_scene.fbx(filepath=str(source))
    elif suffix in (".glb", ".gltf"):
        bpy.ops.import_scene.gltf(filepath=str(source))
    elif suffix == ".obj":
        bpy.ops.wm.obj_import(filepath=str(source))
    else:
        raise ValueError(f"unsupported source format {suffix!r}")
    return [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]


def _triangle_count(meshes: list) -> int:
    total = 0
    for obj in meshes:
        obj.data.calc_loop_triangles()
        total += len(obj.data.loop_triangles)
    return total


def _world_bounds(meshes: list):
    points = [
        obj.matrix_world @ Vector(corner)
        for obj in meshes
        for corner in obj.bound_box
    ]
    xs = [point.x for point in points]
    ys = [point.y for point in points]
    zs = [point.z for point in points]
    return (min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs))


def _remove_floaters(meshes: list) -> list:
    _minimum, _maximum = _world_bounds(meshes)
    diagonal = math.dist(_minimum, _maximum)
    threshold = (diagonal * FLOATER_FRACTION) ** 3
    kept = []
    for obj in meshes:
        dimensions = obj.dimensions
        volume = max(dimensions[0], 1e-9) * max(dimensions[1], 1e-9) * max(dimensions[2], 1e-9)
        if volume < threshold:
            bpy.data.objects.remove(obj, do_unlink=True)
        else:
            kept.append(obj)
    return kept


def _repair(meshes: list) -> None:
    for obj in meshes:
        bpy.context.view_layer.objects.active = obj
        obj.select_set(True)
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="SELECT")
        bpy.ops.mesh.delete_loose()
        bpy.ops.mesh.remove_doubles(threshold=1e-5)
        bpy.ops.mesh.normals_make_consistent(inside=False)
        bpy.ops.object.mode_set(mode="OBJECT")
        obj.select_set(False)


def _normalize(meshes: list, grid_unit: float, up_axis: str) -> dict:
    if up_axis == "Y":
        for obj in meshes:
            if obj.parent is None:
                obj.rotation_euler.rotate_axis("X", -math.pi / 2)
    bpy.context.view_layer.update()
    minimum, maximum = _world_bounds(meshes)
    centre_x = (minimum[0] + maximum[0]) / 2
    centre_z = (minimum[2] + maximum[2]) / 2

    def snap(value: float) -> float:
        return round(value / grid_unit) * grid_unit

    offset = (
        snap(-centre_x) - (-centre_x) - centre_x,
        -minimum[1],
        snap(-centre_z) - (-centre_z) - centre_z,
    )
    for obj in meshes:
        if obj.parent is None:
            obj.location[0] += offset[0]
            obj.location[1] += offset[1]
            obj.location[2] += offset[2]
    bpy.context.view_layer.update()
    minimum, maximum = _world_bounds(meshes)
    return {
        "min": {"x": minimum[0], "y": minimum[1], "z": minimum[2]},
        "max": {"x": maximum[0], "y": maximum[1], "z": maximum[2]},
        "origin": {
            "x": snap((minimum[0] + maximum[0]) / 2),
            "y": snap(minimum[1]),
            "z": snap((minimum[2] + maximum[2]) / 2),
        },
    }


def _decimate(meshes: list, budget: int) -> int:
    current = _triangle_count(meshes)
    if current <= budget:
        return current
    ratio = budget / current
    for obj in meshes:
        bpy.context.view_layer.objects.active = obj
        modifier = obj.modifiers.new("RetroDecimate", "DECIMATE")
        modifier.decimate_type = "COLLAPSE"
        modifier.ratio = ratio
        modifier.use_collapse_triangulate = True
        bpy.ops.object.modifier_apply(modifier="RetroDecimate")
    return _triangle_count(meshes)


def main() -> int:
    payload_path, report_path = _arguments()
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    report = {
        "ok": False,
        "stages": {},
        "triangles_in": 0,
        "triangles_out": 0,
        "parts": [],
        "bounds": {},
        "error": None,
    }
    try:
        contract = payload["contract"]
        role = payload["role"]
        bands = contract["polycount_bands"]
        if role not in bands:
            raise ValueError(
                f"unknown role {role!r}; contract declares {sorted(bands)}"
            )
        budget = bands[role]

        _clear_scene()
        meshes = _import_source(Path(payload["source"]))
        if not meshes:
            raise ValueError("source contains no mesh objects")
        report["triangles_in"] = _triangle_count(meshes)
        report["parts"] = sorted(obj.name for obj in meshes)
        report["stages"]["split"] = len(meshes)

        meshes = _remove_floaters(meshes)
        _repair(meshes)
        report["stages"]["cleanup"] = len(meshes)

        report["bounds"] = _normalize(meshes, contract["grid_unit"], contract["up_axis"])
        report["stages"]["normalize"] = True

        report["triangles_out"] = _decimate(meshes, budget)
        report["stages"]["decimate"] = budget

        bpy.ops.object.select_all(action="SELECT")
        bpy.ops.export_scene.gltf(
            filepath=payload["output"],
            export_format="GLB",
            use_selection=True,
            export_apply=True,
            export_yup=(contract["up_axis"] == "Y"),
        )
        report["ok"] = True
    except Exception as error:  # reported, never swallowed
        report["error"] = f"{type(error).__name__}: {error}"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_retro_geometry -v`
Expected: PASS, 4 tests

If `test_preserves_semantic_parts` fails, print `report["parts"]` and check
whether the FBX importer prefixed or suffixed the object names. Adjust the
assertion to match the real names rather than renaming objects in the script:
the names come from the source and are data, not something to normalize.

- [ ] **Step 5: Commit**

```bash
git add factory/scripts/retro_pass.py tests/test_retro_geometry.py
git commit -m "feat: split clean normalize and decimate meshes in blender"
```

---

### Task 7: Blender PS1 pass — texture stages

Implements stages 5-8: UV validation, bake to `texture_size`, quantize to the
pack palette, strip the maps named in `drop_maps`, optional vertex-light bake,
export.

Quantization runs inside Blender using the numpy bundled with `bpy`, because
the baked image lives in `bpy.data.images` and never touches disk before
quantization.

**Files:**
- Modify: `factory/scripts/retro_pass.py`
- Test: `tests/test_retro_texture.py`

**Interfaces:**
- Consumes: the payload contract from Task 6, plus a new required payload key
  `palette` (absolute path to the palette PNG).
- Produces: two extra report keys —
  `"texture": {"size": int, "quantized": bool, "palette_colours": int}` and
  `"dropped_maps": [str]`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_retro_texture.py`:

```python
import json
import struct
import tempfile
import unittest
from pathlib import Path

from factory.blender import discover_blender, run_blender_script
from factory.config import FactoryConfig
from factory.palette import conformance, load_palette
from factory.png import encode_rgba
from tests.fixtures import FixtureUnavailable, trenchgun_fbx
from tests.temp_paths import temporary_root

SCRIPT = Path(__file__).resolve().parents[1] / "factory" / "scripts" / "retro_pass.py"


def _glb_textures(path: Path) -> list[bytes]:
    data = path.read_bytes()
    json_length = struct.unpack_from("<I", data, 12)[0]
    document = json.loads(data[20 : 20 + json_length].decode("utf-8"))
    binary_offset = 20 + json_length + 8
    images = []
    for image in document.get("images", []):
        view = document["bufferViews"][image["bufferView"]]
        start = binary_offset + view.get("byteOffset", 0)
        images.append(data[start : start + view["byteLength"]])
    return images


class RetroTextureTest(unittest.TestCase):
    def setUp(self):
        self.config = FactoryConfig.load()
        if discover_blender(self.config) is None:
            self.skipTest("Blender is not available on this host")
        try:
            self.source = trenchgun_fbx()
        except FixtureUnavailable as error:
            self.skipTest(str(error))

    def _palette(self, temp: Path) -> Path:
        colours = [
            (20, 18, 16), (60, 52, 42), (104, 82, 56), (146, 118, 82),
            (44, 46, 44), (86, 92, 86), (132, 138, 130), (188, 192, 186),
        ]
        rgba = bytearray()
        for colour in colours:
            rgba.extend((*colour, 255))
        path = temp / "palette.png"
        path.write_bytes(encode_rgba(len(colours), 1, bytes(rgba)))
        return path

    def _run(self, temp: Path) -> tuple[dict, Path, Path]:
        palette = self._palette(temp)
        output = temp / "out.glb"
        report_path = temp / "report.json"
        report = run_blender_script(
            self.config,
            SCRIPT,
            {
                "source": str(self.source),
                "output": str(output),
                "role": "large",
                "palette": str(palette),
                "contract": {
                    "texture_size": 256,
                    "filtering": "nearest",
                    "polycount_bands": {"small": 400, "medium": 1000, "large": 2500},
                    "grid_unit": 0.5,
                    "up_axis": "Y",
                    "drop_maps": ["normal", "roughness", "metallic"],
                    "vertex_light_bake": True,
                },
            },
            report_path,
        )
        return report, output, palette

    def test_bakes_a_quantized_texture_at_contract_size(self):
        work = self.config.root / "tmp" / "factory" / "tests" / "retro"
        work.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=work) as temp:
            report, output, palette = self._run(Path(temp))
            self.assertTrue(report["ok"], report.get("error"))
            self.assertEqual(report["texture"]["size"], 256)
            self.assertTrue(report["texture"]["quantized"])

            textures = _glb_textures(output)
            self.assertTrue(textures, "exported GLB embeds no image")
            colours = load_palette(palette)
            for image in textures:
                result = conformance(image, colours)
                self.assertTrue(
                    result["ok"],
                    f"{result['foreign_pixels']} foreign pixels: "
                    f"{result['foreign_colours'][:4]}",
                )

    def test_drops_pbr_maps_named_in_the_contract(self):
        work = self.config.root / "tmp" / "factory" / "tests" / "retro"
        work.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=work) as temp:
            report, output, _palette = self._run(Path(temp))
            self.assertEqual(
                report["dropped_maps"], ["metallic", "normal", "roughness"]
            )
            document = json.loads(
                output.read_bytes()[20 : 20 + struct.unpack_from("<I", output.read_bytes(), 12)[0]]
                .decode("utf-8")
            )
            for material in document.get("materials", []):
                self.assertNotIn("normalTexture", material)
                self.assertNotIn("occlusionTexture", material)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_retro_texture -v`
Expected: FAIL with `KeyError: 'texture'` — the report has no texture section
yet.

- [ ] **Step 3: Add the texture stages**

In `factory/scripts/retro_pass.py`, add these functions above `main`:

```python
def _ensure_uvs(meshes: list) -> bool:
    regenerated = False
    for obj in meshes:
        if not obj.data.uv_layers:
            bpy.context.view_layer.objects.active = obj
            obj.select_set(True)
            bpy.ops.object.mode_set(mode="EDIT")
            bpy.ops.mesh.select_all(action="SELECT")
            bpy.ops.uv.smart_project(angle_limit=math.radians(66.0), island_margin=0.02)
            bpy.ops.object.mode_set(mode="OBJECT")
            obj.select_set(False)
            regenerated = True
    return regenerated


def _bake_target(size: int):
    image = bpy.data.images.new("RetroBake", width=size, height=size, alpha=True)
    for obj in bpy.context.scene.objects:
        if obj.type != "MESH":
            continue
        for slot in obj.material_slots:
            material = slot.material
            if material is None or not material.use_nodes:
                continue
            node = material.node_tree.nodes.new("ShaderNodeTexImage")
            node.image = image
            node.select = True
            material.node_tree.nodes.active = node
    return image


def _quantize(image, palette_path: Path) -> int:
    import numpy

    _width, _height, rgba = _read_png(palette_path)
    entries = sorted(
        {
            (rgba[index], rgba[index + 1], rgba[index + 2])
            for index in range(0, len(rgba), 4)
            if rgba[index + 3] == 255
        }
    )
    palette = numpy.array(entries, dtype=numpy.int16)
    pixels = numpy.array(image.pixels[:], dtype=numpy.float32).reshape(-1, 4)
    srgb = numpy.where(
        pixels[:, :3] <= 0.0031308,
        pixels[:, :3] * 12.92,
        1.055 * numpy.power(numpy.clip(pixels[:, :3], 0.0, None), 1 / 2.4) - 0.055,
    )
    bytes_rgb = numpy.clip(numpy.rint(srgb * 255.0), 0, 255).astype(numpy.int16)
    distances = ((bytes_rgb[:, None, :] - palette[None, :, :]) ** 2).sum(axis=2)
    mapped = palette[distances.argmin(axis=1)].astype(numpy.float32) / 255.0
    linear = numpy.where(
        mapped <= 0.04045,
        mapped / 12.92,
        numpy.power((mapped + 0.055) / 1.055, 2.4),
    )
    pixels[:, :3] = linear
    image.pixels = pixels.reshape(-1).tolist()
    return len(entries)


def _read_png(path: Path) -> tuple[int, int, bytes]:
    import binascii
    import struct as _struct
    import zlib

    data = path.read_bytes()
    position = 8
    header = None
    compressed = bytearray()
    while position < len(data):
        (length,) = _struct.unpack(">I", data[position : position + 4])
        kind = data[position + 4 : position + 8]
        payload = data[position + 8 : position + 8 + length]
        position += 12 + length
        if kind == b"IHDR":
            header = _struct.unpack(">IIBBBBB", payload)
        elif kind == b"IDAT":
            compressed.extend(payload)
        elif kind == b"IEND":
            break
    width, height, _depth, colour_type, _c, _f, _i = header
    channels = 4 if colour_type == 6 else 3
    raw = zlib.decompress(bytes(compressed))
    stride = width * channels
    out = bytearray()
    previous = bytearray(stride)
    position = 0
    for _row in range(height):
        filter_type = raw[position]
        position += 1
        line = bytearray(raw[position : position + stride])
        position += stride
        if filter_type == 1:
            for index in range(channels, stride):
                line[index] = (line[index] + line[index - channels]) & 0xFF
        elif filter_type == 2:
            for index in range(stride):
                line[index] = (line[index] + previous[index]) & 0xFF
        out.extend(line)
        previous = line
    if channels == 4:
        return width, height, bytes(out)
    rgba = bytearray()
    for index in range(0, len(out), 3):
        rgba.extend(out[index : index + 3])
        rgba.append(255)
    return width, height, bytes(rgba)


def _strip_maps(drop_maps: list) -> list:
    removed = set()
    sockets = {
        "normal": "Normal",
        "roughness": "Roughness",
        "metallic": "Metallic",
        "emissive": "Emission Color",
        "occlusion": "Occlusion",
    }
    for material in bpy.data.materials:
        if not material.use_nodes:
            continue
        bsdf = material.node_tree.nodes.get("Principled BSDF")
        if bsdf is None:
            continue
        for name in drop_maps:
            socket = bsdf.inputs.get(sockets.get(name, ""))
            if socket is None:
                continue
            for link in list(socket.links):
                material.node_tree.links.remove(link)
            removed.add(name)
    return sorted(removed)
```

- [ ] **Step 4: Wire the texture stages into `main`**

In `factory/scripts/retro_pass.py`, inside `main`, insert after the
`report["stages"]["decimate"] = budget` line and before the export call:

```python
        report["stages"]["uv_regenerated"] = _ensure_uvs(meshes)

        size = contract["texture_size"]
        image = _bake_target(size)
        bpy.context.scene.render.engine = "CYCLES"
        bpy.context.scene.cycles.samples = 1
        bpy.ops.object.select_all(action="SELECT")
        bpy.ops.object.bake(type="DIFFUSE", pass_filter={"COLOR"}, use_selected_to_active=False)
        palette_colours = _quantize(image, Path(payload["palette"]))
        report["texture"] = {
            "size": size,
            "quantized": True,
            "palette_colours": palette_colours,
        }

        report["dropped_maps"] = _strip_maps(contract["drop_maps"])
        report["vertex_light_bake"] = False
```

`vertex_light_bake` is validated by the style contract but **not applied in
this plan**. Report it as `False` so the field is never silently assumed to
have taken effect. Baking ambient occlusion and lighting into vertex colours
is deferred to the next plan, where it can be compared against the flat-lit
result on a real approved asset rather than guessed at now. Do not delete the
contract field: the schema is shipped and later packs depend on it.

Also change the export call so the baked image is the only texture written:

```python
        bpy.ops.object.select_all(action="SELECT")
        bpy.ops.export_scene.gltf(
            filepath=payload["output"],
            export_format="GLB",
            use_selection=True,
            export_apply=True,
            export_yup=(contract["up_axis"] == "Y"),
            export_image_format="PNG",
        )
```

And add `"texture": {}` and `"dropped_maps": []` to the initial `report` dict
so a failure path still returns a well-formed report.

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m unittest tests.test_retro_texture -v`
Expected: PASS, 2 tests

If quantization leaves foreign pixels, the cause is almost always colour
management: Blender stores `image.pixels` in linear float, and the palette is
sRGB bytes. The `_quantize` conversion above handles that. Verify by setting
`image.colorspace_settings.name` and re-checking, not by loosening the
conformance assertion — Gate 1 depends on it being exact.

- [ ] **Step 6: Commit**

```bash
git add factory/scripts/retro_pass.py tests/test_retro_texture.py
git commit -m "feat: bake and palette-quantize ps1 textures"
```

---

### Task 8: Host-side retro wrapper and determinism

Wraps the Blender script behind a typed Python function and proves the
determinism guarantee the spec requires. Blender writes its own version into
`asset.generator`, so the comparison normalizes that one field before
asserting byte equality.

**Files:**
- Create: `factory/retro.py`
- Test: `tests/test_retro.py`

**Interfaces:**
- Consumes: `factory.blender.run_blender_script`,
  `factory.style_contract.StyleContract`.
- Produces:
  - `factory.retro.retro_pass(config, source: Path, contract: StyleContract, role: str, output: Path, report_path: Path) -> dict`
  - `factory.retro.canonical_glb_bytes(path: Path) -> bytes`
  - `factory.retro.RetroError(RuntimeError)`

- [ ] **Step 1: Write the failing test**

Create `tests/test_retro.py`:

```python
import json
import tempfile
import unittest
from pathlib import Path

from factory.blender import discover_blender
from factory.config import FactoryConfig
from factory.png import encode_rgba
from factory.retro import RetroError, canonical_glb_bytes, retro_pass
from factory.style_contract import StyleContract
from tests.fixtures import FixtureUnavailable, trenchgun_fbx

CONTRACT = {
    "schema_version": 1,
    "palette": "palette.png",
    "texture_size": 256,
    "filtering": "nearest",
    "polycount_bands": {"small": 400, "medium": 1000, "large": 2500},
    "grid_unit": 0.5,
    "up_axis": "Y",
    "drop_maps": ["normal", "roughness", "metallic"],
    "vertex_light_bake": True,
}


class RetroPassTest(unittest.TestCase):
    def setUp(self):
        self.config = FactoryConfig.load()
        if discover_blender(self.config) is None:
            self.skipTest("Blender is not available on this host")
        try:
            self.source = trenchgun_fbx()
        except FixtureUnavailable as error:
            self.skipTest(str(error))
        self.work = self.config.root / "tmp" / "factory" / "tests" / "retro"
        self.work.mkdir(parents=True, exist_ok=True)

    def _contract(self, temp: Path) -> StyleContract:
        rgba = bytearray()
        for colour in ((20, 18, 16), (104, 82, 56), (132, 138, 130), (188, 192, 186)):
            rgba.extend((*colour, 255))
        (temp / "palette.png").write_bytes(encode_rgba(4, 1, bytes(rgba)))
        path = temp / "contract.json"
        path.write_text(json.dumps(CONTRACT), encoding="utf-8")
        return StyleContract.load(self.config, path)

    def test_produces_byte_identical_output_for_identical_inputs(self):
        with tempfile.TemporaryDirectory(dir=self.work) as temp:
            temp_path = Path(temp)
            contract = self._contract(temp_path)
            first = temp_path / "first.glb"
            second = temp_path / "second.glb"
            retro_pass(
                self.config, self.source, contract, "large", first,
                temp_path / "first.json",
            )
            retro_pass(
                self.config, self.source, contract, "large", second,
                temp_path / "second.json",
            )
            self.assertEqual(canonical_glb_bytes(first), canonical_glb_bytes(second))

    def test_raises_on_blender_side_failure(self):
        with tempfile.TemporaryDirectory(dir=self.work) as temp:
            temp_path = Path(temp)
            contract = self._contract(temp_path)
            with self.assertRaisesRegex(RetroError, "colossal"):
                retro_pass(
                    self.config, self.source, contract, "colossal",
                    temp_path / "out.glb", temp_path / "report.json",
                )


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_retro -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'factory.retro'`

- [ ] **Step 3: Write minimal implementation**

Create `factory/retro.py`:

```python
from __future__ import annotations

import json
import struct
from pathlib import Path

from .blender import run_blender_script
from .config import FactoryConfig
from .style_contract import StyleContract

SCRIPT = Path(__file__).resolve().parent / "scripts" / "retro_pass.py"
CANONICAL_GENERATOR = "BlenderAssetFactory retro_pass"


class RetroError(RuntimeError):
    pass


def canonical_glb_bytes(path: Path) -> bytes:
    """Return GLB bytes with volatile metadata normalized.

    Blender writes its own version into asset.generator, which differs between
    installs. Everything else in the file must be reproducible.
    """
    data = path.read_bytes()
    json_length = struct.unpack_from("<I", data, 12)[0]
    document = json.loads(data[20 : 20 + json_length].decode("utf-8"))
    document.setdefault("asset", {})["generator"] = CANONICAL_GENERATOR
    document["asset"].pop("copyright", None)
    normalized = json.dumps(document, sort_keys=True, separators=(",", ":")).encode("utf-8")
    normalized += b" " * ((4 - len(normalized) % 4) % 4)
    binary = data[20 + json_length :]
    header = struct.pack("<III", 0x46546C67, 2, 12 + 8 + len(normalized) + len(binary))
    return header + struct.pack("<II", len(normalized), 0x4E4F534A) + normalized + binary


def retro_pass(
    config: FactoryConfig,
    source: Path,
    contract: StyleContract,
    role: str,
    output: Path,
    report_path: Path,
) -> dict:
    contract.band_for(role)
    payload = {
        "source": str(source),
        "output": str(output),
        "role": role,
        "palette": str(contract.palette),
        "contract": contract.as_payload(),
    }
    report = run_blender_script(config, SCRIPT, payload, report_path)
    if not report.get("ok"):
        raise RetroError(f"retro pass failed: {report.get('error')}")
    if not output.is_file():
        raise RetroError(f"retro pass reported success but {output} does not exist")
    report["contract_digest"] = contract.digest()
    return report
```

`retro_pass` calls `contract.band_for(role)` before spawning Blender so an
unknown role fails fast with `StyleContractError`. The test expects
`RetroError`, so catch and re-raise:

```python
    try:
        contract.band_for(role)
    except Exception as error:
        raise RetroError(str(error)) from error
```

Replace the bare `contract.band_for(role)` line with that block.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_retro -v`
Expected: PASS, 2 tests

If the determinism test fails, dump both canonical byte strings to files and
diff them. The usual causes are a timestamp in a texture's name, or Blender
iterating `bpy.data.materials` in hash order. Fix the source of the
nondeterminism in `retro_pass.py` by sorting the iteration; do not relax the
assertion.

- [ ] **Step 5: Commit**

```bash
git add factory/retro.py tests/test_retro.py
git commit -m "feat: run the retro pass deterministically from python"
```

---

### Task 9: Silhouette rendering and IoU

Gate 2 needs 8 fixed-view silhouettes of both the raw and converted meshes.
Rendering happens in Blender with a flat white emission shader on black, so
the mask is unambiguous and lighting-independent.

**Files:**
- Create: `factory/scripts/silhouette_render.py`
- Create: `factory/silhouette.py`
- Test: `tests/test_silhouette.py`

**Interfaces:**
- Consumes: `factory.blender.run_blender_script`, `factory.png.decode_rgba`.
- Produces:
  - `factory.silhouette.VIEWS` — tuple of 8 `(azimuth_degrees, elevation_degrees)` pairs
  - `factory.silhouette.render_masks(config, source: Path, output_dir: Path, report_path: Path) -> tuple[Path, ...]`
  - `factory.silhouette.mask_from_png(data: bytes) -> tuple[int, bytes]` returning `(width, mask_bits)` where each byte is 0 or 1
  - `factory.silhouette.iou(first: bytes, second: bytes) -> float`
  - `factory.silhouette.compare(raw_masks, ps1_masks) -> dict` returning
    `{"per_view": [float], "minimum": float, "mean": float}`
  - `factory.silhouette.SilhouetteError(RuntimeError)`

- [ ] **Step 1: Write the failing test**

Create `tests/test_silhouette.py`:

```python
import unittest

from factory.png import encode_rgba
from factory.silhouette import VIEWS, compare, iou, mask_from_png


def _mask_png(rows: list[str]) -> bytes:
    rgba = bytearray()
    for row in rows:
        for character in row:
            value = 255 if character == "#" else 0
            rgba.extend((value, value, value, 255))
    return encode_rgba(len(rows[0]), len(rows), bytes(rgba))


class SilhouetteMathTest(unittest.TestCase):
    def test_eight_fixed_views_are_declared(self):
        self.assertEqual(len(VIEWS), 8)
        self.assertEqual(len(set(VIEWS)), 8)

    def test_identical_masks_score_one(self):
        _width, mask = mask_from_png(_mask_png(["##..", ".##.", "...."]))
        self.assertEqual(iou(mask, mask), 1.0)

    def test_disjoint_masks_score_zero(self):
        _w1, first = mask_from_png(_mask_png(["##..", "....", "...."]))
        _w2, second = mask_from_png(_mask_png(["....", "....", "..##"]))
        self.assertEqual(iou(first, second), 0.0)

    def test_half_overlap_scores_one_third(self):
        _w1, first = mask_from_png(_mask_png(["##.."]))
        _w2, second = mask_from_png(_mask_png([".##."]))
        self.assertAlmostEqual(iou(first, second), 1 / 3, places=6)

    def test_compare_reports_minimum_and_mean(self):
        _w, full = mask_from_png(_mask_png(["##"]))
        _w2, half = mask_from_png(_mask_png(["#."]))
        result = compare([full, full], [full, half])
        self.assertEqual(result["per_view"][0], 1.0)
        self.assertAlmostEqual(result["per_view"][1], 0.5, places=6)
        self.assertAlmostEqual(result["minimum"], 0.5, places=6)
        self.assertAlmostEqual(result["mean"], 0.75, places=6)

    def test_compare_rejects_mismatched_view_counts(self):
        _w, full = mask_from_png(_mask_png(["##"]))
        with self.assertRaisesRegex(ValueError, "view count"):
            compare([full], [full, full])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_silhouette -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'factory.silhouette'`

- [ ] **Step 3: Write the host-side module**

Create `factory/silhouette.py`:

```python
from __future__ import annotations

from pathlib import Path

from .blender import run_blender_script
from .config import FactoryConfig
from .png import decode_rgba

SCRIPT = Path(__file__).resolve().parent / "scripts" / "silhouette_render.py"
RESOLUTION = 256
LUMA_THRESHOLD = 32

VIEWS: tuple[tuple[float, float], ...] = (
    (0.0, 0.0),
    (45.0, 20.0),
    (90.0, 0.0),
    (135.0, 20.0),
    (180.0, 0.0),
    (225.0, 20.0),
    (270.0, 0.0),
    (0.0, 89.0),
)


class SilhouetteError(RuntimeError):
    pass


def mask_from_png(data: bytes) -> tuple[int, bytes]:
    width, _height, rgba = decode_rgba(data)
    mask = bytearray(len(rgba) // 4)
    for index in range(0, len(rgba), 4):
        luma = (rgba[index] * 299 + rgba[index + 1] * 587 + rgba[index + 2] * 114) // 1000
        mask[index // 4] = 1 if luma >= LUMA_THRESHOLD else 0
    return width, bytes(mask)


def iou(first: bytes, second: bytes) -> float:
    if len(first) != len(second):
        raise ValueError(
            f"masks must be the same size: {len(first)} vs {len(second)} pixels"
        )
    intersection = 0
    union = 0
    for a, b in zip(first, second):
        if a and b:
            intersection += 1
        if a or b:
            union += 1
    if union == 0:
        return 1.0
    return intersection / union


def compare(raw_masks: list[bytes], ps1_masks: list[bytes]) -> dict:
    if len(raw_masks) != len(ps1_masks):
        raise ValueError(
            f"view count mismatch: {len(raw_masks)} raw vs {len(ps1_masks)} converted"
        )
    scores = [iou(raw, ps1) for raw, ps1 in zip(raw_masks, ps1_masks)]
    return {
        "per_view": scores,
        "minimum": min(scores),
        "mean": sum(scores) / len(scores),
    }


def render_masks(
    config: FactoryConfig,
    source: Path,
    output_dir: Path,
    report_path: Path,
) -> tuple[Path, ...]:
    config.require_owned_path(output_dir)
    payload = {
        "source": str(source),
        "output_dir": str(output_dir),
        "resolution": RESOLUTION,
        "views": [list(view) for view in VIEWS],
    }
    report = run_blender_script(config, SCRIPT, payload, report_path)
    if not report.get("ok"):
        raise SilhouetteError(f"silhouette render failed: {report.get('error')}")
    paths = tuple(Path(item) for item in report["renders"])
    if len(paths) != len(VIEWS):
        raise SilhouetteError(
            f"expected {len(VIEWS)} renders, got {len(paths)}"
        )
    return paths
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_silhouette -v`
Expected: PASS, 6 tests

- [ ] **Step 5: Write the Blender renderer**

Create `factory/scripts/silhouette_render.py`:

```python
"""Render fixed-view silhouettes. Runs inside Blender."""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector


def _arguments() -> tuple[Path, Path]:
    argv = sys.argv[sys.argv.index("--") + 1 :]
    return (
        Path(argv[argv.index("--payload") + 1]),
        Path(argv[argv.index("--report") + 1]),
    )


def _import(source: Path) -> list:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    suffix = source.suffix.lower()
    if suffix == ".fbx":
        bpy.ops.import_scene.fbx(filepath=str(source))
    elif suffix in (".glb", ".gltf"):
        bpy.ops.import_scene.gltf(filepath=str(source))
    elif suffix == ".obj":
        bpy.ops.wm.obj_import(filepath=str(source))
    else:
        raise ValueError(f"unsupported source format {suffix!r}")
    return [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]


def _flat_white(meshes: list) -> None:
    material = bpy.data.materials.new("SilhouetteWhite")
    material.use_nodes = True
    tree = material.node_tree
    tree.nodes.clear()
    emission = tree.nodes.new("ShaderNodeEmission")
    emission.inputs["Color"].default_value = (1.0, 1.0, 1.0, 1.0)
    emission.inputs["Strength"].default_value = 1.0
    output = tree.nodes.new("ShaderNodeOutputMaterial")
    tree.links.new(emission.outputs["Emission"], output.inputs["Surface"])
    for obj in meshes:
        obj.data.materials.clear()
        obj.data.materials.append(material)


def _bounds(meshes: list):
    points = [
        obj.matrix_world @ Vector(corner)
        for obj in meshes
        for corner in obj.bound_box
    ]
    xs = [p.x for p in points]
    ys = [p.y for p in points]
    zs = [p.z for p in points]
    centre = ((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2, (min(zs) + max(zs)) / 2)
    radius = max(max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs)) / 2
    return centre, max(radius, 1e-6)


def main() -> int:
    payload_path, report_path = _arguments()
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    report = {"ok": False, "renders": [], "error": None}
    try:
        meshes = _import(Path(payload["source"]))
        if not meshes:
            raise ValueError("source contains no mesh objects")
        _flat_white(meshes)
        centre, radius = _bounds(meshes)

        scene = bpy.context.scene
        scene.render.engine = "BLENDER_WORKBENCH"
        scene.display.shading.light = "FLAT"
        scene.display.shading.color_type = "MATERIAL"
        scene.render.film_transparent = False
        scene.world.color = (0.0, 0.0, 0.0)
        scene.render.resolution_x = payload["resolution"]
        scene.render.resolution_y = payload["resolution"]
        scene.render.image_settings.file_format = "PNG"
        scene.render.image_settings.color_mode = "RGBA"

        camera_data = bpy.data.cameras.new("SilhouetteCamera")
        camera_data.type = "ORTHO"
        camera_data.ortho_scale = radius * 2.4
        camera = bpy.data.objects.new("SilhouetteCamera", camera_data)
        scene.collection.objects.link(camera)
        scene.camera = camera

        output_dir = Path(payload["output_dir"])
        output_dir.mkdir(parents=True, exist_ok=True)
        for index, (azimuth, elevation) in enumerate(payload["views"]):
            theta = math.radians(azimuth)
            phi = math.radians(elevation)
            distance = radius * 4.0
            camera.location = (
                centre[0] + distance * math.cos(phi) * math.sin(theta),
                centre[1] + distance * math.cos(phi) * math.cos(theta) * -1,
                centre[2] + distance * math.sin(phi),
            )
            direction = (
                centre[0] - camera.location[0],
                centre[1] - camera.location[1],
                centre[2] - camera.location[2],
            )
            camera.rotation_euler = (
                math.atan2(
                    math.hypot(direction[0], direction[1]), direction[2]
                ) + math.pi,
                0.0,
                math.atan2(direction[1], direction[0]) + math.pi / 2,
            )
            target = output_dir / f"view_{index:02d}.png"
            scene.render.filepath = str(target)
            bpy.ops.render.render(write_still=True)
            report["renders"].append(str(target))
        report["ok"] = True
    except Exception as error:
        report["error"] = f"{type(error).__name__}: {error}"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 6: Write the integration test**

Append to `tests/test_silhouette.py`:

```python
import tempfile
import unittest as _unittest
from pathlib import Path as _Path

from factory.blender import discover_blender
from factory.config import FactoryConfig
from factory.silhouette import VIEWS as _VIEWS, mask_from_png as _mask, render_masks
from tests.fixtures import FixtureUnavailable, trenchgun_fbx


class SilhouetteRenderTest(_unittest.TestCase):
    def test_renders_one_mask_per_view_with_visible_coverage(self):
        config = FactoryConfig.load()
        if discover_blender(config) is None:
            self.skipTest("Blender is not available on this host")
        try:
            source = trenchgun_fbx()
        except FixtureUnavailable as error:
            self.skipTest(str(error))
        work = config.root / "tmp" / "factory" / "tests" / "silhouette"
        work.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=work) as temp:
            temp_path = _Path(temp)
            renders = render_masks(
                config, source, temp_path / "views", temp_path / "report.json"
            )
            self.assertEqual(len(renders), len(_VIEWS))
            for path in renders:
                _width, mask = _mask(path.read_bytes())
                coverage = sum(mask) / len(mask)
                self.assertGreater(coverage, 0.01, f"{path.name} is essentially empty")
                self.assertLess(coverage, 0.99, f"{path.name} is essentially solid")
```

- [ ] **Step 7: Run the full silhouette test module**

Run: `python -m unittest tests.test_silhouette -v`
Expected: PASS, 7 tests

If a view renders empty, the camera orientation maths is wrong for that
azimuth. Verify by opening one render manually. Fix the camera rotation, not
the coverage bounds.

- [ ] **Step 8: Commit**

```bash
git add factory/silhouette.py factory/scripts/silhouette_render.py tests/test_silhouette.py
git commit -m "feat: measure silhouette iou across eight fixed views"
```

---

### Task 10: Gate 1 and Gate 2

**Files:**
- Create: `factory/gates.py`
- Test: `tests/test_gates.py`

**Interfaces:**
- Consumes: `factory.palette.conformance`, `factory.silhouette.compare`,
  `factory.style_contract.StyleContract`.
- Produces:
  - `factory.gates.GATE2_PASS = 0.95`, `factory.gates.GATE2_FLAG = 0.90`
  - `factory.gates.gate1(glb_bytes: bytes, contract: StyleContract, role: str, triangles: int, validator_ok: bool, preview_ok: bool) -> dict`
  - `factory.gates.gate2(comparison: dict) -> dict`
  - `factory.gates.verdict(gate1_report: dict, gate2_report: dict) -> str` returning
    `"pass"`, `"flag"` or `"reject"`

- [ ] **Step 1: Write the failing test**

Create `tests/test_gates.py`:

```python
import json
import struct
import tempfile
import unittest
from pathlib import Path

from factory.config import FactoryConfig
from factory.gates import GATE2_FLAG, GATE2_PASS, gate1, gate2, verdict
from factory.png import encode_rgba
from factory.style_contract import StyleContract
from tests.temp_paths import temporary_root

PALETTE = ((20, 18, 16), (104, 82, 56), (188, 192, 186))
CONTRACT = {
    "schema_version": 1,
    "palette": "palette.png",
    "texture_size": 4,
    "filtering": "nearest",
    "polycount_bands": {"small": 400, "medium": 1000, "large": 2500},
    "grid_unit": 0.5,
    "up_axis": "Y",
    "drop_maps": ["normal", "roughness", "metallic"],
    "vertex_light_bake": True,
}


def _glb(texture: bytes, materials: list[dict]) -> bytes:
    document = {
        "asset": {"version": "2.0"},
        "images": [{"bufferView": 0, "mimeType": "image/png"}],
        "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": len(texture)}],
        "buffers": [{"byteLength": len(texture)}],
        "materials": materials,
    }
    body = json.dumps(document, separators=(",", ":")).encode("utf-8")
    body += b" " * ((4 - len(body) % 4) % 4)
    binary = texture + b"\x00" * ((4 - len(texture) % 4) % 4)
    total = 12 + 8 + len(body) + 8 + len(binary)
    return (
        struct.pack("<III", 0x46546C67, 2, total)
        + struct.pack("<II", len(body), 0x4E4F534A)
        + body
        + struct.pack("<II", len(binary), 0x004E4942)
        + binary
    )


def _texture(colours) -> bytes:
    rgba = bytearray()
    for index in range(16):
        rgba.extend((*colours[index % len(colours)], 255))
    return encode_rgba(4, 4, bytes(rgba))


class GateTest(unittest.TestCase):
    def setUp(self):
        self.config = FactoryConfig.load()
        self.temp = tempfile.TemporaryDirectory(dir=temporary_root())
        temp_path = Path(self.temp.name)
        rgba = bytearray()
        for colour in PALETTE:
            rgba.extend((*colour, 255))
        (temp_path / "palette.png").write_bytes(encode_rgba(len(PALETTE), 1, bytes(rgba)))
        path = temp_path / "contract.json"
        path.write_text(json.dumps(CONTRACT), encoding="utf-8")
        self.contract = StyleContract.load(self.config, path)

    def tearDown(self):
        self.temp.cleanup()

    def test_gate1_passes_a_conforming_asset(self):
        report = gate1(
            _glb(_texture(PALETTE), [{"name": "flat"}]),
            self.contract, "small", triangles=380,
            validator_ok=True, preview_ok=True,
        )
        self.assertTrue(report["ok"], report["failures"])

    def test_gate1_fails_over_budget_triangles(self):
        report = gate1(
            _glb(_texture(PALETTE), [{"name": "flat"}]),
            self.contract, "small", triangles=401,
            validator_ok=True, preview_ok=True,
        )
        self.assertFalse(report["ok"])
        self.assertIn("triangle_budget", report["failures"])

    def test_gate1_fails_off_palette_texture(self):
        report = gate1(
            _glb(_texture([(1, 2, 3)]), [{"name": "flat"}]),
            self.contract, "small", triangles=100,
            validator_ok=True, preview_ok=True,
        )
        self.assertFalse(report["ok"])
        self.assertIn("palette_conformance", report["failures"])

    def test_gate1_fails_forbidden_material_texture(self):
        report = gate1(
            _glb(_texture(PALETTE), [{"name": "flat", "normalTexture": {"index": 0}}]),
            self.contract, "small", triangles=100,
            validator_ok=True, preview_ok=True,
        )
        self.assertFalse(report["ok"])
        self.assertIn("dropped_maps", report["failures"])

    def test_gate1_fails_when_validator_or_preview_failed(self):
        report = gate1(
            _glb(_texture(PALETTE), [{"name": "flat"}]),
            self.contract, "small", triangles=100,
            validator_ok=False, preview_ok=True,
        )
        self.assertIn("gltf_validator", report["failures"])

    def test_gate2_thresholds(self):
        self.assertEqual(gate2({"minimum": 0.97, "mean": 0.98})["verdict"], "pass")
        self.assertEqual(gate2({"minimum": 0.92, "mean": 0.95})["verdict"], "flag")
        self.assertEqual(gate2({"minimum": 0.80, "mean": 0.90})["verdict"], "reject")
        self.assertEqual(GATE2_PASS, 0.95)
        self.assertEqual(GATE2_FLAG, 0.90)

    def test_verdict_combines_both_gates(self):
        good = {"ok": True, "failures": []}
        bad = {"ok": False, "failures": ["triangle_budget"]}
        self.assertEqual(verdict(good, {"verdict": "pass"}), "pass")
        self.assertEqual(verdict(good, {"verdict": "flag"}), "flag")
        self.assertEqual(verdict(good, {"verdict": "reject"}), "reject")
        self.assertEqual(verdict(bad, {"verdict": "pass"}), "reject")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_gates -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'factory.gates'`

- [ ] **Step 3: Write minimal implementation**

Create `factory/gates.py`:

```python
from __future__ import annotations

import json
import struct

from .palette import conformance, load_palette
from .style_contract import StyleContract

GATE2_PASS = 0.95
GATE2_FLAG = 0.90

_MAP_TEXTURES = {
    "normal": "normalTexture",
    "occlusion": "occlusionTexture",
    "emissive": "emissiveTexture",
}


def _glb_parts(data: bytes) -> tuple[dict, list[bytes]]:
    json_length = struct.unpack_from("<I", data, 12)[0]
    document = json.loads(data[20 : 20 + json_length].decode("utf-8"))
    binary_offset = 20 + json_length + 8
    images: list[bytes] = []
    for image in document.get("images", []):
        if "bufferView" not in image:
            continue
        view = document["bufferViews"][image["bufferView"]]
        start = binary_offset + view.get("byteOffset", 0)
        images.append(data[start : start + view["byteLength"]])
    return document, images


def gate1(
    glb_bytes: bytes,
    contract: StyleContract,
    role: str,
    triangles: int,
    validator_ok: bool,
    preview_ok: bool,
) -> dict:
    failures: list[str] = []
    details: dict = {}

    budget = contract.band_for(role)
    details["triangles"] = triangles
    details["budget"] = budget
    if triangles > budget:
        failures.append("triangle_budget")

    if not validator_ok:
        failures.append("gltf_validator")
    if not preview_ok:
        failures.append("runtime_preview")

    document, images = _glb_parts(glb_bytes)

    palette = load_palette(contract.palette)
    details["palette_colours"] = len(palette)
    if not images:
        failures.append("missing_texture")
    conformance_reports = []
    for image in images:
        result = conformance(image, palette)
        conformance_reports.append(result)
        if not result["ok"]:
            failures.append("palette_conformance")
            break
    details["palette_conformance"] = conformance_reports

    forbidden = [
        _MAP_TEXTURES[name]
        for name in contract.drop_maps
        if name in _MAP_TEXTURES
    ]
    offenders = [
        key
        for material in document.get("materials", [])
        for key in forbidden
        if key in material
    ]
    if offenders:
        failures.append("dropped_maps")
    details["forbidden_textures_present"] = sorted(set(offenders))

    return {
        "ok": not failures,
        "failures": sorted(set(failures)),
        "details": details,
    }


def gate2(comparison: dict) -> dict:
    minimum = comparison["minimum"]
    if minimum >= GATE2_PASS:
        result = "pass"
    elif minimum >= GATE2_FLAG:
        result = "flag"
    else:
        result = "reject"
    return {
        "verdict": result,
        "minimum": minimum,
        "mean": comparison.get("mean"),
        "thresholds": {"pass": GATE2_PASS, "flag": GATE2_FLAG},
    }


def verdict(gate1_report: dict, gate2_report: dict) -> str:
    if not gate1_report["ok"]:
        return "reject"
    return gate2_report["verdict"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_gates -v`
Expected: PASS, 7 tests

- [ ] **Step 5: Commit**

```bash
git add factory/gates.py tests/test_gates.py
git commit -m "feat: gate ps1 assets on measurements not opinions"
```

---

### Task 11: Pack orchestrator over local sources

Runs a whole catalog offline. Each entry maps to a local source mesh supplied
by the caller, which is exactly the offline replay the spec's end-to-end test
requires. Provider generation arrives in the next plan and slots in where the
`sources` mapping is read.

**Files:**
- Create: `factory/pack.py`
- Test: `tests/test_pack.py`

**Interfaces:**
- Consumes: `factory.catalog.Catalog`, `factory.style_contract.StyleContract`,
  `factory.retro.retro_pass`, `factory.silhouette.render_masks`,
  `factory.silhouette.compare`, `factory.gates.gate1`, `factory.gates.gate2`,
  `factory.gates.verdict`, `factory.gltf_validation.validate_glb`,
  `factory.io.atomic_write_json`.
- Produces:
  - `factory.pack.build_pack(config, catalog: Catalog, contract: StyleContract, sources: dict[str, Path], output_root: Path, validate: bool = True) -> dict`
  - `factory.pack.PackError(RuntimeError)`

`build_pack` must never raise for a single failing asset. Failures are
recorded per entry and the run continues.

- [ ] **Step 1: Write the failing test**

Create `tests/test_pack.py`:

```python
import json
import tempfile
import unittest
from pathlib import Path

from factory.blender import discover_blender
from factory.catalog import Catalog
from factory.config import FactoryConfig
from factory.pack import build_pack
from factory.png import encode_rgba
from factory.style_contract import StyleContract
from tests.fixtures import FixtureUnavailable, trenchgun_fbx

CONTRACT = {
    "schema_version": 1,
    "palette": "palette.png",
    "texture_size": 256,
    "filtering": "nearest",
    "polycount_bands": {"small": 400, "medium": 1000, "large": 2500},
    "grid_unit": 0.5,
    "up_axis": "Y",
    "drop_maps": ["normal", "roughness", "metallic"],
    "vertex_light_bake": True,
}


class PackBuildTest(unittest.TestCase):
    def setUp(self):
        self.config = FactoryConfig.load()
        if discover_blender(self.config) is None:
            self.skipTest("Blender is not available on this host")
        try:
            self.source = trenchgun_fbx()
        except FixtureUnavailable as error:
            self.skipTest(str(error))
        self.work = self.config.root / "tmp" / "factory" / "tests" / "pack"
        self.work.mkdir(parents=True, exist_ok=True)

    def _catalog(self, temp: Path, assets: list[dict]):
        rgba = bytearray()
        for colour in ((20, 18, 16), (104, 82, 56), (132, 138, 130), (188, 192, 186)):
            rgba.extend((*colour, 255))
        (temp / "palette.png").write_bytes(encode_rgba(4, 1, bytes(rgba)))
        contract_path = temp / "contract.json"
        contract_path.write_text(json.dumps(CONTRACT), encoding="utf-8")
        contract = StyleContract.load(self.config, contract_path)
        catalog_path = temp / "catalog.json"
        catalog_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "pack_id": "test_kit",
                    "style_contract": "contract.json",
                    "max_generations": 10,
                    "max_rerolls": 3,
                    "assets": assets,
                }
            ),
            encoding="utf-8",
        )
        return Catalog.load(self.config, catalog_path, contract), contract

    def test_builds_every_entry_and_reports_verdicts(self):
        with tempfile.TemporaryDirectory(dir=self.work) as temp:
            temp_path = Path(temp)
            catalog, contract = self._catalog(
                temp_path,
                [{"id": "hero", "lane": "A", "role": "large", "prompt": "a shotgun"}],
            )
            report = build_pack(
                self.config, catalog, contract,
                {"hero": self.source},
                temp_path / "out",
                validate=False,
            )
            self.assertEqual(report["pack_id"], "test_kit")
            self.assertEqual(len(report["assets"]), 1)
            entry = report["assets"][0]
            self.assertEqual(entry["id"], "hero")
            self.assertIn(entry["verdict"], ("pass", "flag", "reject"))
            self.assertIn("silhouette", entry)
            self.assertIn("gate1", entry)

    def test_missing_source_is_recorded_without_aborting_the_run(self):
        with tempfile.TemporaryDirectory(dir=self.work) as temp:
            temp_path = Path(temp)
            catalog, contract = self._catalog(
                temp_path,
                [
                    {"id": "hero", "lane": "A", "role": "large", "prompt": "a shotgun"},
                    {"id": "absent", "lane": "A", "role": "small", "prompt": "nothing"},
                ],
            )
            report = build_pack(
                self.config, catalog, contract,
                {"hero": self.source},
                temp_path / "out",
                validate=False,
            )
            self.assertEqual(len(report["assets"]), 2)
            failed = next(item for item in report["assets"] if item["id"] == "absent")
            self.assertEqual(failed["verdict"], "reject")
            self.assertIn("no source", failed["error"])
            succeeded = next(item for item in report["assets"] if item["id"] == "hero")
            self.assertIsNone(succeeded["error"])
            self.assertFalse(report["ok"])

    def test_writes_a_run_report_to_disk(self):
        with tempfile.TemporaryDirectory(dir=self.work) as temp:
            temp_path = Path(temp)
            catalog, contract = self._catalog(
                temp_path,
                [{"id": "hero", "lane": "A", "role": "large", "prompt": "a shotgun"}],
            )
            report = build_pack(
                self.config, catalog, contract,
                {"hero": self.source},
                temp_path / "out",
                validate=False,
            )
            written = Path(report["report_path"])
            self.assertTrue(written.is_file())
            self.assertEqual(
                json.loads(written.read_text(encoding="utf-8"))["pack_id"], "test_kit"
            )


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_pack -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'factory.pack'`

- [ ] **Step 3: Write minimal implementation**

Create `factory/pack.py`:

```python
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from .catalog import Catalog
from .config import FactoryConfig
from .gates import gate1, gate2, verdict
from .gltf_validation import validate_glb
from .io import atomic_write_json
from .retro import retro_pass
from .silhouette import compare, mask_from_png, render_masks
from .style_contract import StyleContract


class PackError(RuntimeError):
    pass


def _asset_record(identifier: str) -> dict:
    return {
        "id": identifier,
        "verdict": "reject",
        "error": None,
        "triangles": None,
        "gate1": None,
        "gate2": None,
        "silhouette": None,
        "output": None,
    }


def build_pack(
    config: FactoryConfig,
    catalog: Catalog,
    contract: StyleContract,
    sources: dict[str, Path],
    output_root: Path,
    validate: bool = True,
) -> dict:
    started = datetime.now(timezone.utc)
    run_id = started.strftime("%Y%m%dT%H%M%S.%fZ")
    records: list[dict] = []

    for entry in catalog.entries:
        record = _asset_record(entry.id)
        asset_dir = output_root / entry.id
        try:
            source = sources.get(entry.id)
            if source is None or not Path(source).is_file():
                raise PackError(f"no source mesh was supplied for {entry.id!r}")
            source = Path(source)

            work = asset_dir / "work"
            work.mkdir(parents=True, exist_ok=True)
            output = asset_dir / f"{entry.id}.glb"

            retro_report = retro_pass(
                config, source, contract, entry.role, output, work / "retro.json"
            )
            record["triangles"] = retro_report["triangles_out"]
            record["output"] = str(output)

            raw_masks = [
                mask_from_png(path.read_bytes())[1]
                for path in render_masks(
                    config, source, work / "masks-raw", work / "masks-raw.json"
                )
            ]
            ps1_masks = [
                mask_from_png(path.read_bytes())[1]
                for path in render_masks(
                    config, output, work / "masks-ps1", work / "masks-ps1.json"
                )
            ]
            comparison = compare(raw_masks, ps1_masks)
            record["silhouette"] = comparison

            validator_ok = True
            if validate:
                validation = validate_glb(config, output, work / "validation.json")
                validator_ok = bool(validation.get("ok", False))

            first = gate1(
                output.read_bytes(),
                contract,
                entry.role,
                triangles=retro_report["triangles_out"],
                validator_ok=validator_ok,
                preview_ok=True,
            )
            second = gate2(comparison)
            record["gate1"] = first
            record["gate2"] = second
            record["verdict"] = verdict(first, second)
        except Exception as error:
            record["error"] = f"{type(error).__name__}: {error}"
        records.append(record)

    report = {
        "schema_version": 1,
        "pack_id": catalog.pack_id,
        "run_id": run_id,
        "started_at": started.isoformat(),
        "contract_digest": contract.digest(),
        "ok": all(item["verdict"] == "pass" for item in records),
        "counts": {
            name: sum(1 for item in records if item["verdict"] == name)
            for name in ("pass", "flag", "reject")
        },
        "assets": records,
    }
    report_path = config.reports_root / "packs" / catalog.pack_id / run_id / "pack.json"
    report["report_path"] = str(report_path)
    atomic_write_json(report_path, report)
    return report
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_pack -v`
Expected: PASS, 3 tests

- [ ] **Step 5: Commit**

```bash
git add factory/pack.py tests/test_pack.py
git commit -m "feat: build a whole pack from local source meshes"
```

---

### Task 12: CLI command

**Files:**
- Modify: `factory/cli.py`
- Test: `tests/test_cli_pack.py`

**Interfaces:**
- Consumes: `factory.pack.build_pack`, `factory.catalog.Catalog`,
  `factory.style_contract.StyleContract`, the existing `factory.cli.envelope`
  and `factory.cli._option` helpers.
- Produces: a `pack` command registered in `_handlers()`, invoked as
  `factory.ps1 pack --catalog <path> --sources <path> --out <path>` where
  `--sources` is a JSON object mapping asset id to source mesh path.

- [ ] **Step 1: Write the failing test**

Create `tests/test_cli_pack.py`:

```python
import json
import tempfile
import unittest
from pathlib import Path

from factory.blender import discover_blender
from factory.cli import run
from factory.config import FactoryConfig
from factory.png import encode_rgba
from tests.fixtures import FixtureUnavailable, trenchgun_fbx


class CliPackTest(unittest.TestCase):
    def setUp(self):
        self.config = FactoryConfig.load()
        if discover_blender(self.config) is None:
            self.skipTest("Blender is not available on this host")
        try:
            self.source = trenchgun_fbx()
        except FixtureUnavailable as error:
            self.skipTest(str(error))
        self.work = self.config.root / "tmp" / "factory" / "tests" / "cli-pack"
        self.work.mkdir(parents=True, exist_ok=True)

    def test_pack_command_returns_an_envelope_with_counts(self):
        with tempfile.TemporaryDirectory(dir=self.work) as temp:
            temp_path = Path(temp)
            rgba = bytearray()
            for colour in ((20, 18, 16), (104, 82, 56), (188, 192, 186)):
                rgba.extend((*colour, 255))
            (temp_path / "palette.png").write_bytes(encode_rgba(3, 1, bytes(rgba)))
            (temp_path / "contract.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "palette": "palette.png",
                        "texture_size": 256,
                        "filtering": "nearest",
                        "polycount_bands": {"small": 400, "medium": 1000, "large": 2500},
                        "grid_unit": 0.5,
                        "up_axis": "Y",
                        "drop_maps": ["normal", "roughness", "metallic"],
                        "vertex_light_bake": True,
                    }
                ),
                encoding="utf-8",
            )
            (temp_path / "catalog.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "pack_id": "cli_kit",
                        "style_contract": "contract.json",
                        "max_generations": 10,
                        "max_rerolls": 3,
                        "assets": [
                            {"id": "hero", "lane": "A", "role": "large",
                             "prompt": "a shotgun"}
                        ],
                    }
                ),
                encoding="utf-8",
            )
            (temp_path / "sources.json").write_text(
                json.dumps({"hero": str(self.source)}), encoding="utf-8"
            )
            code, payload, _ = run(
                [
                    "pack",
                    "--catalog", str(temp_path / "catalog.json"),
                    "--sources", str(temp_path / "sources.json"),
                    "--out", str(temp_path / "out"),
                    "--skip-validate",
                ]
            )
            self.assertEqual(code, 0, payload)
            self.assertEqual(payload["data"]["pack_id"], "cli_kit")
            self.assertIn("counts", payload["data"])

    def test_pack_command_reports_a_missing_catalog(self):
        code, payload, _ = run(
            ["pack", "--catalog", "absent.json", "--sources", "absent.json",
             "--out", "out"]
        )
        self.assertEqual(code, 1)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["errors"][0]["type"], "FileNotFoundError")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_cli_pack -v`
Expected: FAIL — `run` rejects `pack` as an unknown command

- [ ] **Step 3: Confirm the handler contract**

The existing conventions in `factory/cli.py`, which the new handler must match
exactly:

```python
Handler = Callable[[list[str]], tuple[int, dict]]

def envelope(
    command: str,
    ok: bool,
    summary: str,
    data: dict | None = None,
    errors: list[dict] | None = None,
) -> dict
```

`summary` is a **required positional** argument and `errors` is a **list of
dicts**, not a string. `_handlers()` returns an alphabetically ordered dict, so
`"pack"` belongs between `"optimize"` and `"preview"`.

- [ ] **Step 4: Add the handler**

In `factory/cli.py`, add these imports near the existing `from .` imports:

```python
from .catalog import Catalog
from .pack import build_pack
from .style_contract import StyleContract
```

Then add the handler function, placed immediately before `_verify`:

```python
def _pack(args: list[str]) -> tuple[int, dict]:
    config = FactoryConfig.load()
    catalog_path = Path(_option(args, "--catalog")).resolve(strict=False)
    sources_path = Path(_option(args, "--sources")).resolve(strict=False)
    output_root = Path(_option(args, "--out")).resolve(strict=False)
    validate = "--skip-validate" not in args
    try:
        if not catalog_path.is_file():
            raise FileNotFoundError(f"catalog does not exist: {catalog_path}")
        if not sources_path.is_file():
            raise FileNotFoundError(f"sources map does not exist: {sources_path}")
        contract_hint = json.loads(catalog_path.read_text(encoding="utf-8-sig"))
        contract = StyleContract.load(
            config, catalog_path.parent / contract_hint["style_contract"]
        )
        catalog = Catalog.load(config, catalog_path, contract)
        sources = {
            key: Path(value)
            for key, value in json.loads(
                sources_path.read_text(encoding="utf-8-sig")
            ).items()
        }
        report = build_pack(
            config, catalog, contract, sources, output_root, validate=validate
        )
    except Exception as error:
        return 1, envelope(
            "pack",
            False,
            "Pack build could not start",
            errors=[{"type": type(error).__name__, "detail": str(error)}],
        )
    counts = report["counts"]
    summary = (
        f"{catalog.pack_id}: {counts['pass']} pass, "
        f"{counts['flag']} flag, {counts['reject']} reject"
    )
    return (
        0 if report["ok"] else 2,
        envelope("pack", report["ok"], summary, data=report),
    )
```

- [ ] **Step 5: Register the command**

In `_handlers()` in `factory/cli.py`, add to the returned dict, keeping the
existing entries and alphabetical placement if the dict is ordered:

```python
        "pack": _pack,
```

- [ ] **Step 6: Run test to verify it passes**

Run: `python -m unittest tests.test_cli_pack -v`
Expected: PASS, 2 tests

- [ ] **Step 7: Run the whole suite**

Run: `python -m unittest discover -s tests -p "test_*.py"`
Expected: PASS, no regressions. `tests/test_cli.py` may assert the exact set
of registered commands; if it fails, add `pack` to its expected list.

- [ ] **Step 8: Commit**

```bash
git add factory/cli.py tests/test_cli_pack.py
git commit -m "feat: expose pack builds through the factory cli"
```

---

## Definition of Done

- `.\factory.ps1 doctor` reports `blender: available` on this Windows host.
- `python -m unittest discover -s tests -p "test_*.py"` passes with no
  regressions in the pre-existing modules.
- `.\factory.ps1 pack --catalog <catalog> --sources <map> --out <dir>` converts
  the `trenchgun.fbx` fixture into a palette-conformant PS1 GLB and reports a
  Gate 1 result, a Gate 2 silhouette IoU, and a verdict.
- `retro_pass` produces byte-identical output across two runs with identical
  inputs, after `canonical_glb_bytes` normalization.
- No file under any `raw/` directory is modified after creation.
- Unrelated dirty work in `factory/` and `knowledge/` is preserved.

## Deferred to the Next Plan

Phases 4-7 of the spec, to be planned after Sloyd's API documentation has been
read and its request and response shapes verified:

- `factory/providers/sloyd.py` with injected transports, content-addressed
  generation caching, and the hard spend cap.
- Lane B: FLUX concept generation via the existing `bfl.py`, then Sloyd
  image-to-3D.
- Multi-candidate generation, the independent vision judge, and re-roll reason
  codes.
- Contact sheet assembly over pack results and the persisted approval state.
- `factory/provenance.py` and the shipped licence ledger.
- Applying `vertex_light_bake`: baking ambient occlusion and lighting into
  vertex colours. The style contract already validates the flag and
  `retro_pass` reports it as `False`; nothing reads it yet.
- The `ww2_diorama_kit_01` catalog with all 30 assets, the 48-colour palette,
  gltfpack derivation, `release.py` packaging, and the demo-scene hero render.
