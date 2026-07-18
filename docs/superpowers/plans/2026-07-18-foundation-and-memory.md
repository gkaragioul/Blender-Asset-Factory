# Foundation and Durable Memory Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the style-neutral factory control plane that keeps all owned runtime data on `G:`, reports verified capabilities, stores durable project knowledge, and hands the exact active task to a new Codex conversation.

**Architecture:** A repository-local PowerShell launcher invokes a standard-library Python package from a uv-managed interpreter under `.tooling`. The package loads one versioned configuration, rejects unsafe roots, returns a common JSON result envelope, probes capabilities without mutating them, maintains atomic state files, and promotes lessons only through explicit evidence. Markdown bootstrap files are generated from machine-readable state so conversations remain portable without treating prose as a database.

**Tech Stack:** Windows PowerShell 5.1+, uv 0.11.29, uv-managed CPython 3.12.11, Python standard library, JSON Schema documents, `unittest`, Git.

## Global Constraints

- Canonical root: `G:\DevWork\GameDev\BlenderAssetFactory`.
- Model root: `G:\LLMs`.
- Every factory-owned writable path resolves to drive `G:`.
- Third-party environments live under `.tooling` and remain untracked.
- Model binaries remain beneath `G:\LLMs` and remain untracked; manifests are tracked.
- The style-neutral core contains no PS1, WWII, fantasy, or realism defaults.
- Existing M42 Task 3 changes in `.worktrees\codex-ps1-ww2-pump-shotgun` are read-only during this phase.
- `learn` cannot train models or modify bridge identity, path restrictions, recovery logic, or transactional publication.
- Every public command emits a versioned JSON envelope and returns nonzero on failure.
- Atomic state writes use a sibling temporary file followed by `os.replace`.

---

## File Structure

### New tracked files

- `factory.ps1` - stable PowerShell entry point.
- `bootstrap/setup.ps1` - idempotent repository-local uv/Python bootstrap.
- `factory/__init__.py` - package version.
- `factory/__main__.py` - module entry point.
- `factory/cli.py` - command parsing and result-envelope output.
- `factory/config.py` - configuration loading and `G:` path enforcement.
- `factory/io.py` - atomic JSON/text writes and hashing.
- `factory/doctor.py` - read-only capability probes.
- `factory/state.py` - active project, factory state, resume, and bootstrap generation.
- `factory/learning.py` - candidate lesson recording and promotion policy.
- `factory/transfer.py` - model/tool inventory and transfer manifest generation.
- `factory/config.json` - canonical roots and tool discovery candidates.
- `factory/schemas/*.schema.json` - machine-readable contracts.
- `knowledge/START_HERE.md` - generated conversation bootstrap.
- `knowledge/FACTORY_STATE.md` - generated verified state summary.
- `knowledge/active-project.json` - authoritative active-project pointer.
- `knowledge/factory-state.json` - authoritative verified capability state.
- `knowledge/lessons/.gitkeep` and `knowledge/failures/.gitkeep` - knowledge roots.
- `knowledge/project-summaries/.gitkeep` - closeout summaries.
- `tools/manifests/toolchain.json` - pinned bootstrap toolchain.
- `tools/manifests/transfer.json` - generated excluded-dependency inventory.
- `G:\LLMs\manifests/model-index.json` - generated external model index; not committed.
- `tests/test_bootstrap.py` - setup and storage contract tests.
- `tests/test_config.py` - configuration and path-safety tests.
- `tests/test_cli.py` - command protocol tests.
- `tests/test_doctor.py` - capability-probe tests.
- `tests/test_state.py` - state, bootstrap, and resume tests.
- `tests/test_learning.py` - learning-policy tests.
- `tests/test_transfer.py` - deterministic inventory tests.
- `tests/test_continuity.py` - end-to-end new-conversation continuity test.

### Existing files modified

- `.gitignore` - ignore local tool/runtime/report state while preserving tracked knowledge.
- `README.md` - document bootstrap, doctor, verify, and resume commands.
- `AGENTS.md` - require future Codex sessions to load and refresh factory memory.

---

### Task 1: Repository-Local Runtime Bootstrap

**Files:**
- Create: `tests/test_bootstrap.py`
- Create: `bootstrap/setup.ps1`
- Create: `tools/manifests/toolchain.json`
- Modify: `.gitignore`

**Interfaces:**
- Produces: `.tooling/uv/uv.exe`, `.tooling/python/**/python.exe`, `.tooling/runtime.json`.
- Produces: `bootstrap/setup.ps1 -DryRun` JSON with keys `schema_version`, `root`, `model_root`, `uv_version`, `python_version`, and `actions`.
- Consumed by: `factory.ps1` and every later test command.

- [ ] **Step 1: Write the failing bootstrap contract test**

```python
import json
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class BootstrapContractTest(unittest.TestCase):
    def test_dry_run_keeps_every_owned_path_on_g(self):
        completed = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy", "Bypass",
                "-File", str(ROOT / "bootstrap" / "setup.ps1"),
                "-DryRun",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        result = json.loads(completed.stdout)
        self.assertEqual(result["schema_version"], 1)
        self.assertEqual(Path(result["root"]), ROOT)
        self.assertEqual(result["model_root"], r"G:\LLMs")
        self.assertEqual(result["uv_version"], "0.11.29")
        self.assertEqual(result["python_version"], "3.12.11")
        for action in result["actions"]:
            self.assertEqual(Path(action["target"]).drive.upper(), "G:")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the test and verify RED**

Run from the canonical root using the currently available host Python:

```powershell
python -m unittest tests.test_bootstrap -v
```

Expected: FAIL because `bootstrap/setup.ps1` does not exist.

- [ ] **Step 3: Add the pinned toolchain manifest**

```json
{
  "schema_version": 1,
  "uv": {
    "version": "0.11.29",
    "installer": "https://astral.sh/uv/0.11.29/install.ps1"
  },
  "python": {
    "implementation": "cpython",
    "version": "3.12.11"
  }
}
```

- [ ] **Step 4: Implement the idempotent bootstrap**

```powershell
param([switch]$DryRun)
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$modelRoot = 'G:\LLMs'
$tooling = Join-Path $root '.tooling'
$uvDir = Join-Path $tooling 'uv'
$pythonDir = Join-Path $tooling 'python'
$cacheDir = Join-Path $tooling 'cache\uv'
$manifest = Get-Content -Raw (Join-Path $root 'tools\manifests\toolchain.json') | ConvertFrom-Json
$actions = @(
    @{ name = 'install_uv'; target = (Join-Path $uvDir 'uv.exe') },
    @{ name = 'install_python'; target = $pythonDir },
    @{ name = 'create_model_root'; target = $modelRoot }
)
$result = [ordered]@{
    schema_version = 1
    root = $root
    model_root = $modelRoot
    uv_version = $manifest.uv.version
    python_version = $manifest.python.version
    actions = $actions
}
if ($DryRun) { $result | ConvertTo-Json -Depth 5; exit 0 }
foreach ($target in @($tooling, $uvDir, $pythonDir, $cacheDir, $modelRoot, (Join-Path $modelRoot 'manifests'))) {
    if (-not $target.StartsWith('G:\', [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing non-G target: $target"
    }
    New-Item -ItemType Directory -Force -Path $target | Out-Null
}
$uvExe = Join-Path $uvDir 'uv.exe'
if (-not (Test-Path -LiteralPath $uvExe)) {
    $installer = Join-Path $tooling 'uv-install.ps1'
    Invoke-WebRequest -UseBasicParsing -Uri $manifest.uv.installer -OutFile $installer
    $env:UV_UNMANAGED_INSTALL = $uvDir
    $env:UV_NO_MODIFY_PATH = '1'
    & powershell -NoProfile -ExecutionPolicy Bypass -File $installer
}
$env:UV_PYTHON_INSTALL_DIR = $pythonDir
$env:UV_CACHE_DIR = $cacheDir
& $uvExe python install $manifest.python.version --install-dir $pythonDir
if ($LASTEXITCODE -ne 0) { throw "uv python install failed: $LASTEXITCODE" }
$pythonExe = (& $uvExe python find $manifest.python.version --managed-python).Trim()
$runtime = [ordered]@{
    schema_version = 1
    uv = $uvExe
    python = $pythonExe
    uv_version = (& $uvExe --version).Trim()
    python_version = (& $pythonExe --version).Trim()
}
$runtime | ConvertTo-Json | Set-Content -Encoding UTF8 (Join-Path $tooling 'runtime.json')
$result | ConvertTo-Json -Depth 5
```

- [ ] **Step 5: Extend `.gitignore`**

Append exactly:

```gitignore
.tooling/
reports/runs/
tmp/factory/
*.tmp
```

- [ ] **Step 6: Run RED-to-GREEN verification**

```powershell
python -m unittest tests.test_bootstrap -v
powershell -NoProfile -ExecutionPolicy Bypass -File bootstrap\setup.ps1
$runtime = Get-Content -Raw .tooling\runtime.json | ConvertFrom-Json
& $runtime.python -m unittest tests.test_bootstrap -v
```

Expected: bootstrap test passes before and after installation; runtime JSON resolves uv and Python under `G:\DevWork\GameDev\BlenderAssetFactory\.tooling`.

- [ ] **Step 7: Commit**

```powershell
git add .gitignore bootstrap/setup.ps1 tools/manifests/toolchain.json tests/test_bootstrap.py
git commit -m "build: bootstrap factory runtime on G drive"
```

---

### Task 2: Canonical Configuration and Path Safety

**Files:**
- Create: `tests/test_config.py`
- Create: `factory/__init__.py`
- Create: `factory/config.py`
- Create: `factory/config.json`
- Create: `factory/schemas/config.schema.json`

**Interfaces:**
- Produces: `FactoryConfig.load(path: Path | None = None) -> FactoryConfig`.
- Produces: `FactoryConfig.require_owned_path(path: Path) -> Path`.
- Produces fields `root`, `model_root`, `tooling_root`, `reports_root`, `blender_candidates`, and `bridge_url`.
- Consumed by: all commands and adapters.

- [ ] **Step 1: Write failing configuration tests**

```python
import json
import tempfile
import unittest
from pathlib import Path

from factory.config import ConfigurationError, FactoryConfig


class FactoryConfigTest(unittest.TestCase):
    def test_loads_canonical_roots(self):
        config = FactoryConfig.load()
        self.assertEqual(config.root, Path(__file__).resolve().parents[1])
        self.assertEqual(config.model_root, Path(r"G:\LLMs"))
        self.assertEqual(config.bridge_url, "http://127.0.0.1:9876")

    def test_rejects_owned_write_outside_g(self):
        config = FactoryConfig.load()
        with self.assertRaisesRegex(ConfigurationError, "drive G"):
            config.require_owned_path(Path(r"C:\temp\forbidden"))

    def test_rejects_configuration_root_mismatch(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "config.json"
            path.write_text(json.dumps({
                "schema_version": 1,
                "root": "C:/wrong",
                "model_root": "G:/LLMs",
                "tooling_root": "G:/safe",
                "reports_root": "G:/safe/reports",
                "bridge_url": "http://127.0.0.1:9876",
                "blender_candidates": []
            }), encoding="utf-8")
            with self.assertRaises(ConfigurationError):
                FactoryConfig.load(path)
```

- [ ] **Step 2: Run the tests and verify RED**

```powershell
$runtime = Get-Content -Raw .tooling\runtime.json | ConvertFrom-Json
& $runtime.python -m unittest tests.test_config -v
```

Expected: FAIL because `factory.config` does not exist.

- [ ] **Step 3: Add the configuration document**

```json
{
  "schema_version": 1,
  "root": ".",
  "model_root": "G:/LLMs",
  "tooling_root": ".tooling",
  "reports_root": "reports",
  "bridge_url": "http://127.0.0.1:9876",
  "blender_candidates": [
    "C:/Program Files/Blender Foundation/Blender 5.2/blender.exe",
    "G:/Tools/Blender/blender.exe"
  ]
}
```

The `C:` Blender candidate is read-only discovery of an existing application; every factory-owned write target remains on `G:`.

- [ ] **Step 4: Add package version and minimal implementation**

```python
# factory/__init__.py
__version__ = "0.1.0"
```

```python
# factory/config.py
from __future__ import annotations
import json
from dataclasses import dataclass
from pathlib import Path

CANONICAL_ROOT = Path(r"G:\DevWork\GameDev\BlenderAssetFactory")
PACKAGE_ROOT = Path(__file__).resolve().parents[1]


class ConfigurationError(ValueError):
    pass


@dataclass(frozen=True)
class FactoryConfig:
    root: Path
    model_root: Path
    tooling_root: Path
    reports_root: Path
    bridge_url: str
    blender_candidates: tuple[Path, ...]

    @classmethod
    def load(cls, path: Path | None = None) -> "FactoryConfig":
        source = path or PACKAGE_ROOT / "factory" / "config.json"
        data = json.loads(source.read_text(encoding="utf-8-sig"))
        source_root = source.resolve().parents[1]
        def owned(value: str) -> Path:
            candidate = Path(value)
            return candidate if candidate.is_absolute() else source_root / candidate
        config = cls(
            root=owned(data["root"]).resolve(strict=False),
            model_root=Path(data["model_root"]),
            tooling_root=owned(data["tooling_root"]).resolve(strict=False),
            reports_root=owned(data["reports_root"]).resolve(strict=False),
            bridge_url=data["bridge_url"],
            blender_candidates=tuple(Path(item) for item in data["blender_candidates"]),
        )
        trusted_worktrees = CANONICAL_ROOT / ".worktrees"
        if config.root != CANONICAL_ROOT and trusted_worktrees not in config.root.parents:
            raise ConfigurationError(f"root must be canonical or a trusted worktree beneath {trusted_worktrees}")
        for owned in (config.root, config.model_root, config.tooling_root, config.reports_root):
            config.require_owned_path(owned)
        if config.bridge_url != "http://127.0.0.1:9876":
            raise ConfigurationError("bridge must bind to loopback port 9876")
        return config

    def require_owned_path(self, path: Path) -> Path:
        resolved = path.resolve(strict=False)
        if resolved.drive.upper() != "G:":
            raise ConfigurationError(f"factory-owned path must be on drive G: {resolved}")
        return resolved
```

- [ ] **Step 5: Add the exact configuration schema**

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://local.blender-asset-factory/schemas/config.schema.json",
  "type": "object",
  "additionalProperties": false,
  "required": ["schema_version", "root", "model_root", "tooling_root", "reports_root", "bridge_url", "blender_candidates"],
  "properties": {
    "schema_version": {"const": 1},
    "root": {"const": "."},
    "model_root": {"const": "G:/LLMs"},
    "tooling_root": {"const": ".tooling"},
    "reports_root": {"const": "reports"},
    "bridge_url": {"const": "http://127.0.0.1:9876"},
    "blender_candidates": {"type": "array", "items": {"type": "string"}, "uniqueItems": true}
  }
}
```

Schema validation is structural documentation in Phase 1; runtime validation remains dependency-free and explicit.

- [ ] **Step 6: Run tests and commit**

```powershell
$runtime = Get-Content -Raw .tooling\runtime.json | ConvertFrom-Json
& $runtime.python -m unittest tests.test_config -v
git add factory tests/test_config.py
git commit -m "feat: enforce canonical factory configuration"
```

Expected: three tests pass.

---

### Task 3: Result Protocol and Factory CLI

**Files:**
- Create: `tests/test_cli.py`
- Create: `factory/io.py`
- Create: `factory/cli.py`
- Create: `factory/__main__.py`
- Create: `factory.ps1`

**Interfaces:**
- Produces: `ResultEnvelope` JSON with `schema_version`, `command`, `ok`, `summary`, `data`, and `errors`.
- Produces: `python -m factory <command> --json`.
- Produces: `factory.ps1 <command> [arguments]` using `.tooling/runtime.json`.
- Initially supports `version`; later tasks register `doctor`, `resume`, `learn`, `index-models`, and `verify`.

- [ ] **Step 1: Write failing CLI tests**

```python
import json
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class FactoryCliTest(unittest.TestCase):
    def test_version_returns_result_envelope(self):
        completed = subprocess.run(
            [str(Path(__import__("sys").executable)), "-m", "factory", "version", "--json"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        result = json.loads(completed.stdout)
        self.assertEqual(result["schema_version"], 1)
        self.assertEqual(result["command"], "version")
        self.assertTrue(result["ok"])
        self.assertEqual(result["data"]["version"], "0.1.0")
        self.assertEqual(result["errors"], [])

    def test_unknown_command_is_structured_failure(self):
        completed = subprocess.run(
            [str(Path(__import__("sys").executable)), "-m", "factory", "missing", "--json"],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(completed.returncode, 0)
        result = json.loads(completed.stdout)
        self.assertFalse(result["ok"])
        self.assertEqual(result["errors"][0]["code"], "unknown_command")
```

- [ ] **Step 2: Run the tests and verify RED**

Expected: FAIL because `factory.__main__` is missing.

- [ ] **Step 3: Implement atomic I/O and result envelopes**

`factory/io.py` must implement:

```python
from __future__ import annotations
import hashlib, json, os
from pathlib import Path
from typing import Any


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(text, encoding="utf-8", newline="\n")
    os.replace(temporary, path)


def atomic_write_json(path: Path, value: Any) -> None:
    atomic_write_text(path, json.dumps(value, indent=2, sort_keys=True) + "\n")
```

Implement the initial `factory/cli.py` exactly as this minimal protocol; later tasks extend the `handlers` mapping without changing the envelope:

```python
from __future__ import annotations
import json, sys
from collections.abc import Callable
from . import __version__


def envelope(command: str, ok: bool, summary: str, data: dict | None = None, errors: list[dict] | None = None) -> dict:
    return {
        "schema_version": 1,
        "command": command,
        "ok": ok,
        "summary": summary,
        "data": data or {},
        "errors": errors or [],
    }


def _version(_args: list[str]) -> tuple[int, dict]:
    return 0, envelope("version", True, f"Blender Asset Factory {__version__}", {"version": __version__})


def run(argv: list[str]) -> tuple[int, dict, bool]:
    json_output = "--json" in argv
    args = [item for item in argv if item != "--json"]
    command = args[0] if args else ""
    handlers: dict[str, Callable[[list[str]], tuple[int, dict]]] = {"version": _version}
    if command not in handlers:
        result = envelope(command or "unknown", False, "Unknown factory command", errors=[{
            "code": "unknown_command", "message": command or "command required"
        }])
        return 2, result, json_output
    code, result = handlers[command](args[1:])
    return code, result, json_output


def main(argv: list[str] | None = None) -> int:
    code, result, json_output = run(list(sys.argv[1:] if argv is None else argv))
    print(json.dumps(result, indent=2) if json_output else result["summary"])
    return code
```

- [ ] **Step 4: Add module and PowerShell entry points**

```python
# factory/__main__.py
from .cli import main
raise SystemExit(main())
```

```powershell
# factory.ps1
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$runtimePath = Join-Path $root '.tooling\runtime.json'
if (-not (Test-Path -LiteralPath $runtimePath)) {
    throw 'Factory runtime missing. Run .\bootstrap\setup.ps1 first.'
}
$runtime = Get-Content -Raw $runtimePath | ConvertFrom-Json
& $runtime.python -m factory @args
exit $LASTEXITCODE
```

- [ ] **Step 5: Run tests and commit**

```powershell
& (Get-Content -Raw .tooling\runtime.json | ConvertFrom-Json).python -m unittest tests.test_cli -v
.\factory.ps1 version --json
git add factory.ps1 factory tests/test_cli.py
git commit -m "feat: add factory command protocol"
```

Expected: two tests pass and the wrapper returns version `0.1.0`.

---

### Task 4: Read-Only Capability Doctor

**Files:**
- Create: `tests/test_doctor.py`
- Create: `factory/doctor.py`
- Modify: `factory/cli.py`
- Create: `factory/schemas/doctor.schema.json`

**Interfaces:**
- Produces: `probe(config: FactoryConfig, urlopen=urllib.request.urlopen) -> dict`.
- Produces capability statuses `available`, `unavailable`, or `degraded` for `blender`, `bridge`, `uv`, `python`, `model_root`, `comfyui`, `material_maker`, `armorpaint`, `gltf_validator`, `gltfpack`, and `threejs_viewer`.
- `doctor` is strictly read-only and never installs, launches, or repairs tools.

- [ ] **Step 1: Write failing doctor tests**

```python
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from factory.config import FactoryConfig
from factory.doctor import probe


class DoctorTest(unittest.TestCase):
    def test_finds_blender_candidate_and_reports_missing_optionals(self):
        with tempfile.TemporaryDirectory(dir=r"G:\") as temp:
            blender = Path(temp) / "blender.exe"
            blender.write_bytes(b"fixture")
            config = FactoryConfig(
                root=Path(r"G:\DevWork\GameDev\BlenderAssetFactory"),
                model_root=Path(r"G:\LLMs"),
                tooling_root=Path(temp),
                reports_root=Path(r"G:\DevWork\GameDev\BlenderAssetFactory\reports"),
                bridge_url="http://127.0.0.1:9876",
                blender_candidates=(blender,),
            )
            with patch("factory.doctor._probe_bridge", return_value=(False, "connection refused")), patch(
                "factory.doctor._run_version", return_value="Blender 5.2.0"
            ):
                report = probe(config)
        self.assertEqual(report["capabilities"]["blender"]["status"], "available")
        self.assertEqual(report["capabilities"]["bridge"]["status"], "unavailable")
        self.assertIn(report["capabilities"]["comfyui"]["status"], {"unavailable", "degraded"})

    def test_doctor_does_not_create_missing_model_root(self):
        missing = Path(r"G:\factory-doctor-missing-fixture")
        base = FactoryConfig.load()
        config = FactoryConfig(
            root=base.root,
            model_root=missing,
            tooling_root=base.tooling_root,
            reports_root=base.reports_root,
            bridge_url=base.bridge_url,
            blender_candidates=base.blender_candidates,
        )
        probe(config)
        self.assertFalse(missing.exists())
```

- [ ] **Step 2: Run tests and verify RED**

Expected: FAIL because `factory.doctor` does not exist.

- [ ] **Step 3: Implement explicit capability probes**

`factory/doctor.py` must:

- Locate the first existing Blender candidate and run `--version` with a five-second timeout.
- Read `.tooling/runtime.json` and probe its uv/Python executables.
- Attempt `GET http://127.0.0.1:9876/health` with a one-second timeout; treat connection refusal as unavailable.
- Probe optional tools only at paths declared beneath `.tooling`.
- Probe ComfyUI at `.tooling/comfyui/main.py` and report AMD backend status from `.tooling/comfyui/backend.json` when present.
- Report `G:\LLMs` existence and free disk space through `shutil.disk_usage`.
- Return `checked_at` in UTC ISO 8601, but keep the capability ordering deterministic.
- Never call `mkdir`, install, launch, or write files.

Status objects use exactly:

```python
{"status": "available", "path": "...", "version": "...", "detail": "..."}
```

Use these concrete helpers and probe assembly:

```python
from __future__ import annotations
import json, shutil, subprocess, urllib.request
from datetime import datetime, timezone
from pathlib import Path
from .config import FactoryConfig


def _cap(status: str, path: Path | None = None, version: str | None = None, detail: str = "") -> dict:
    return {"status": status, "path": str(path) if path else None, "version": version, "detail": detail}


def _run_version(path: Path, *args: str) -> str:
    completed = subprocess.run([str(path), *args], capture_output=True, text=True, timeout=5, check=True)
    return (completed.stdout or completed.stderr).splitlines()[0].strip()


def _probe_bridge(url: str) -> tuple[bool, str]:
    try:
        with urllib.request.urlopen(url + "/health", timeout=1) as response:
            return 200 <= response.status < 300, f"HTTP {response.status}"
    except Exception as error:
        return False, str(error)


def probe(config: FactoryConfig) -> dict:
    capabilities: dict[str, dict] = {}
    blender = next((path for path in config.blender_candidates if path.is_file()), None)
    if blender:
        try:
            capabilities["blender"] = _cap("available", blender, _run_version(blender, "--version"))
        except Exception as error:
            capabilities["blender"] = _cap("degraded", blender, detail=str(error))
    else:
        capabilities["blender"] = _cap("unavailable", detail="No configured Blender executable exists")
    bridge_ok, bridge_detail = _probe_bridge(config.bridge_url)
    capabilities["bridge"] = _cap("available" if bridge_ok else "unavailable", detail=bridge_detail)
    runtime_path = config.tooling_root / "runtime.json"
    runtime = json.loads(runtime_path.read_text(encoding="utf-8-sig")) if runtime_path.is_file() else {}
    for name in ("uv", "python"):
        path = Path(runtime[name]) if runtime.get(name) else None
        capabilities[name] = _cap("available", path, runtime.get(name + "_version")) if path and path.is_file() else _cap("unavailable")
    if config.model_root.is_dir():
        free = shutil.disk_usage(config.model_root).free
        capabilities["model_root"] = _cap("available", config.model_root, detail=f"free_bytes={free}")
    else:
        capabilities["model_root"] = _cap("unavailable", config.model_root, detail="Model root does not exist")
    optional = {
        "comfyui": config.tooling_root / "comfyui" / "main.py",
        "material_maker": config.tooling_root / "material-maker" / "material_maker.exe",
        "armorpaint": config.tooling_root / "armorpaint" / "ArmorPaint.exe",
        "gltf_validator": config.tooling_root / "gltf-validator" / "gltf_validator.exe",
        "gltfpack": config.tooling_root / "gltfpack" / "gltfpack.exe",
        "threejs_viewer": config.root / "tools" / "threejs-viewer" / "package.json",
    }
    for name, path in optional.items():
        capabilities[name] = _cap("available" if path.is_file() else "unavailable", path)
    backend = config.tooling_root / "comfyui" / "backend.json"
    if capabilities["comfyui"]["status"] == "available" and not backend.is_file():
        capabilities["comfyui"] = _cap("degraded", optional["comfyui"], detail="AMD backend not verified")
    return {
        "schema_version": 1,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "capabilities": {name: capabilities[name] for name in sorted(capabilities)},
    }
```

- [ ] **Step 4: Register `doctor` in the CLI**

The command loads `FactoryConfig`, calls `probe`, and returns exit code `0` when mandatory capabilities `python`, `uv`, `blender`, and `model_root` are available. A missing bridge is degraded but does not fail a read-only/background-capable factory.

- [ ] **Step 5: Run tests and manual probe**

```powershell
.\factory.ps1 doctor --json
& (Get-Content -Raw .tooling\runtime.json | ConvertFrom-Json).python -m unittest tests.test_doctor -v
```

Expected on this workstation: RX 7900 XTX system remains supported, Blender resolves to `C:\Program Files\Blender Foundation\Blender 5.2\blender.exe`, and the inactive bridge reports unavailable without a crash.

- [ ] **Step 6: Commit**

```powershell
git add factory/doctor.py factory/cli.py factory/schemas/doctor.schema.json tests/test_doctor.py
git commit -m "feat: report factory capability health"
```

---

### Task 5: Durable State, Resume, and Generated Conversation Bootstrap

**Files:**
- Create: `tests/test_state.py`
- Create: `factory/state.py`
- Modify: `factory/cli.py`
- Create: `factory/schemas/active-project.schema.json`
- Create: `knowledge/active-project.json`
- Create: `knowledge/factory-state.json`
- Create: `knowledge/START_HERE.md`
- Create: `knowledge/FACTORY_STATE.md`
- Create: `knowledge/lessons/.gitkeep`
- Create: `knowledge/failures/.gitkeep`
- Create: `knowledge/project-summaries/.gitkeep`

**Interfaces:**
- Produces: `load_active_project(config) -> dict`.
- Produces: `save_factory_state(config, doctor_report) -> None`.
- Produces: `render_bootstrap(config) -> str` and `refresh_bootstrap(config) -> None`.
- Produces: `resume_action(config) -> dict` with exact `summary`, `working_directory`, `next_action`, `required_reads`, and `blocked_by`.

- [ ] **Step 1: Write failing state tests**

```python
import json
import tempfile
import unittest
from pathlib import Path

from factory.config import FactoryConfig
from factory.state import refresh_bootstrap, resume_action


class StateTest(unittest.TestCase):
    def make_config(self, root: Path) -> FactoryConfig:
        return FactoryConfig(
            root=root,
            model_root=Path(r"G:\LLMs"),
            tooling_root=root / ".tooling",
            reports_root=root / "reports",
            bridge_url="http://127.0.0.1:9876",
            blender_candidates=(),
        )

    def test_resume_returns_exact_m42_continuation(self):
        with tempfile.TemporaryDirectory(dir=r"G:\") as temp:
            root = Path(temp)
            (root / "knowledge").mkdir()
            (root / "knowledge" / "active-project.json").write_text(json.dumps({
                "schema_version": 1,
                "project_id": "ps1_ww2_pump_shotgun_01",
                "status": "active",
                "working_directory": "G:/DevWork/GameDev/BlenderAssetFactory/.worktrees/codex-ps1-ww2-pump-shotgun",
                "next_action": "finish_task_3_atlas_uv_wear",
                "required_reads": [".superpowers/sdd/task-3-brief.md"],
                "blocked_by": []
            }), encoding="utf-8")
            action = resume_action(self.make_config(root))
        self.assertEqual(action["project_id"], "ps1_ww2_pump_shotgun_01")
        self.assertEqual(action["next_action"], "finish_task_3_atlas_uv_wear")

    def test_refresh_bootstrap_is_deterministic(self):
        with tempfile.TemporaryDirectory(dir=r"G:\") as temp:
            root = Path(temp)
            knowledge = root / "knowledge"
            knowledge.mkdir()
            (knowledge / "active-project.json").write_text('{"schema_version":1,"project_id":null,"status":"idle","working_directory":null,"next_action":null,"required_reads":[],"blocked_by":[]}', encoding="utf-8")
            (knowledge / "factory-state.json").write_text('{"schema_version":1,"capabilities":{}}', encoding="utf-8")
            config = self.make_config(root)
            refresh_bootstrap(config)
            first = (knowledge / "START_HERE.md").read_text(encoding="utf-8")
            refresh_bootstrap(config)
            second = (knowledge / "START_HERE.md").read_text(encoding="utf-8")
        self.assertEqual(first, second)
        self.assertIn("Run `factory.ps1 doctor` before mutations", first)
```

- [ ] **Step 2: Run tests and verify RED**

Expected: FAIL because `factory.state` does not exist.

- [ ] **Step 3: Implement atomic state and bootstrap generation**

`factory/state.py` must validate required keys explicitly, use `atomic_write_json` and `atomic_write_text`, sort capability names, and render these bootstrap sections:

1. `# Blender Asset Factory - Start Here`
2. `## Mandatory startup`
3. `## Active project`
4. `## Verified capabilities`
5. `## Required reading`
6. `## Completion discipline`

It must not include timestamps in `START_HERE.md`; timestamps belong only in machine state so repeated generation from unchanged state is byte-identical.

Implement the state core with these concrete functions:

```python
from __future__ import annotations
import json
from pathlib import Path
from .config import FactoryConfig
from .io import atomic_write_json, atomic_write_text

ACTIVE_KEYS = {"schema_version", "project_id", "status", "working_directory", "next_action", "required_reads", "blocked_by"}


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def load_active_project(config: FactoryConfig) -> dict:
    state = _read_json(config.root / "knowledge" / "active-project.json")
    missing = ACTIVE_KEYS - state.keys()
    if missing:
        raise ValueError(f"active project missing keys: {sorted(missing)}")
    return state


def save_factory_state(config: FactoryConfig, doctor_report: dict) -> None:
    atomic_write_json(config.root / "knowledge" / "factory-state.json", doctor_report)


def resume_action(config: FactoryConfig) -> dict:
    active = load_active_project(config)
    return {
        "project_id": active["project_id"],
        "summary": "No active project" if active["status"] == "idle" else f"Resume {active['project_id']}",
        "working_directory": active["working_directory"],
        "next_action": active["next_action"],
        "required_reads": active["required_reads"],
        "blocked_by": active["blocked_by"],
    }


def render_bootstrap(config: FactoryConfig) -> str:
    active = load_active_project(config)
    factory_state_path = config.root / "knowledge" / "factory-state.json"
    factory_state = _read_json(factory_state_path) if factory_state_path.is_file() else {"capabilities": {}}
    capabilities = factory_state.get("capabilities", {})
    lines = [
        "# Blender Asset Factory - Start Here", "", "## Mandatory startup", "",
        "Run `factory.ps1 doctor` before mutations.", "", "## Active project", "",
        f"- Project: `{active['project_id']}`", f"- Status: `{active['status']}`",
        f"- Working directory: `{active['working_directory']}`", f"- Next action: `{active['next_action']}`",
        "", "## Verified capabilities", "",
    ]
    lines.extend(f"- {name}: `{capabilities[name]['status']}`" for name in sorted(capabilities))
    lines.extend(["", "## Required reading", ""])
    lines.extend(f"- `{path}`" for path in active["required_reads"])
    lines.extend(["", "## Completion discipline", "", "Run the required validations, record evidence, refresh memory, and preserve the next safe action.", ""])
    return "\n".join(lines)


def refresh_bootstrap(config: FactoryConfig) -> None:
    text = render_bootstrap(config)
    atomic_write_text(config.root / "knowledge" / "START_HERE.md", text)
    atomic_write_text(config.root / "knowledge" / "FACTORY_STATE.md", text.replace("Start Here", "Verified State", 1))
```

- [ ] **Step 4: Seed the real active-project state**

```json
{
  "schema_version": 1,
  "project_id": "ps1_ww2_pump_shotgun_01",
  "status": "active",
  "working_directory": "G:/DevWork/GameDev/BlenderAssetFactory/.worktrees/codex-ps1-ww2-pump-shotgun",
  "next_action": "finish_task_3_atlas_uv_wear",
  "required_reads": [
    ".superpowers/sdd/task-3-brief.md",
    "docs/superpowers/specs/2026-07-18-ps1-ww2-pump-shotgun-premium-polish-design.md",
    "specs/ps1_ww2_pump_shotgun_01.json"
  ],
  "blocked_by": []
}
```

`knowledge/factory-state.json` begins with schema version `1`, an empty `capabilities` object, and `last_verified_at: null` until `doctor --save` succeeds.

- [ ] **Step 5: Register state commands**

- `doctor --save` writes the doctor report and refreshes both Markdown summaries.
- `resume --json` returns the active-project continuation without executing it.
- `refresh-memory --json` regenerates bootstrap files from machine state.

- [ ] **Step 6: Run tests and real refresh**

```powershell
.\factory.ps1 doctor --save --json
.\factory.ps1 refresh-memory --json
.\factory.ps1 resume --json
& (Get-Content -Raw .tooling\runtime.json | ConvertFrom-Json).python -m unittest tests.test_state -v
```

Expected: two tests pass; resume points to the dirty M42 Task 3 worktree; generated Markdown contains no stale 450-triangle geometry claim.

- [ ] **Step 7: Commit**

```powershell
git add factory/cli.py factory/state.py factory/schemas/active-project.schema.json knowledge tests/test_state.py
git commit -m "feat: persist factory state and conversation handoff"
```

---

### Task 6: Codex Operating Memory

**Files:**
- Create: `tests/test_codex_memory.py`
- Create: `AGENTS.md`
- Modify: `README.md`

**Interfaces:**
- `AGENTS.md` is the mandatory human-readable contract for future Codex sessions.
- `README.md` is the operator entry point for setup, health, resume, and verification.

- [ ] **Step 1: Write the failing memory contract test**

```python
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class CodexMemoryContractTest(unittest.TestCase):
    def test_agents_requires_durable_startup_and_closeout(self):
        text = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        for phrase in (
            "knowledge/START_HERE.md",
            "factory.ps1 doctor",
            "knowledge/active-project.json",
            "Do not modify trusted bridge safety boundaries through learning",
            "factory.ps1 learn closeout",
        ):
            self.assertIn(phrase, text)

    def test_readme_documents_portable_entry_points(self):
        text = (ROOT / "README.md").read_text(encoding="utf-8")
        for command in ("bootstrap\\setup.ps1", "factory.ps1 doctor", "factory.ps1 resume", "factory.ps1 verify"):
            self.assertIn(command, text)
```

- [ ] **Step 2: Run tests and verify RED**

Expected: FAIL because root `AGENTS.md` does not exist and README lacks the new commands.

- [ ] **Step 3: Write the exact `AGENTS.md` operating contract**

```markdown
# Blender Asset Factory Agent Contract

## Startup

Read `knowledge/START_HERE.md` and `knowledge/active-project.json` before project work. Run `factory.ps1 doctor` before mutations and report any mandatory capability failure.

## Scope

Load the applicable style profile and asset contract. Keep universal, profile, and asset knowledge separate. Do not promote an asset-specific decision into a universal rule without accepted evidence.

## Safety

Preserve builder identity enforcement, canonical/worktree path restrictions, recovery snapshots, and transactional publication. Do not modify trusted bridge safety boundaries through learning. Never permit a staged AI source or optimized derivative to replace an authoritative asset directly.

## Implementation

Use test-first changes for factory behavior. Preserve unrelated dirty work. Keep all factory-owned writable paths on `G:` and model weights under `G:\LLMs`.

## Verification

Run the technical and visual gates required by the active contract before claiming completion. Blender export success alone is not runtime validation.

## Closeout

Run `factory.ps1 learn closeout` with a reviewed summary, regenerate durable memory, and record the exact next safe action in `knowledge/active-project.json`.
```

- [ ] **Step 4: Rewrite README as the operator entry point**

Keep the existing Blender 5.2 and loopback bridge facts, replace the claim that the factory is PS1-specific, and add exact setup/doctor/resume/verify commands plus links to the approved design and `knowledge/START_HERE.md`.

- [ ] **Step 5: Run tests and commit**

```powershell
& (Get-Content -Raw .tooling\runtime.json | ConvertFrom-Json).python -m unittest tests.test_codex_memory -v
git add AGENTS.md README.md tests/test_codex_memory.py
git commit -m "docs: make repository memory authoritative"
```

Expected: two tests pass.

---

### Task 7: Controlled Learning and Project Closeout

**Files:**
- Create: `tests/test_learning.py`
- Create: `factory/learning.py`
- Modify: `factory/cli.py`
- Create: `factory/schemas/lesson.schema.json`

**Interfaces:**
- Produces: `record_candidate(config, candidate: dict) -> Path`.
- Produces: `promote_candidate(config, lesson_id: str, evidence: dict) -> Path`.
- Produces: `closeout_project(config, summary: dict) -> dict`.
- Candidate scopes: `asset`, `profile`, or `universal`.
- Evidence types: `regression`, `repeated_success`, `user_approval`, or `asset_exception`.

- [ ] **Step 1: Write failing learning-policy tests**

```python
import tempfile
import unittest
from pathlib import Path

from factory.config import FactoryConfig
from factory.learning import LearningPolicyError, promote_candidate, record_candidate


class LearningPolicyTest(unittest.TestCase):
    def config(self, root: Path) -> FactoryConfig:
        return FactoryConfig(root, Path(r"G:\LLMs"), root / ".tooling", root / "reports", "http://127.0.0.1:9876", ())

    def test_candidate_does_not_become_lesson_without_evidence(self):
        with tempfile.TemporaryDirectory(dir=r"G:\") as temp:
            root = Path(temp)
            path = record_candidate(self.config(root), {
                "lesson_id": "localized-wear-001",
                "scope": "profile",
                "title": "Localize functional wear",
                "statement": "Wear follows handling and mechanisms.",
                "source_projects": ["m42"],
            })
            self.assertIn("candidates", path.parts)
            with self.assertRaises(LearningPolicyError):
                promote_candidate(self.config(root), "localized-wear-001", {})

    def test_user_approval_promotes_profile_lesson(self):
        with tempfile.TemporaryDirectory(dir=r"G:\") as temp:
            root = Path(temp)
            config = self.config(root)
            record_candidate(config, {
                "lesson_id": "localized-wear-001", "scope": "profile", "title": "Localize wear",
                "statement": "Wear follows contact zones.", "source_projects": ["m42"]
            })
            promoted = promote_candidate(config, "localized-wear-001", {
                "type": "user_approval", "reference": "conversation-2026-07-18"
            })
            self.assertEqual(promoted.parent.name, "profile")
```

- [ ] **Step 2: Run tests and verify RED**

Expected: FAIL because `factory.learning` does not exist.

- [ ] **Step 3: Implement the promotion policy**

`record_candidate` validates exact required keys, rejects duplicate IDs, adds `status: candidate`, and writes to `knowledge/lessons/candidates/<lesson_id>.json`. `promote_candidate` accepts only the four evidence types, adds immutable evidence and source links, writes to `knowledge/lessons/<scope>/<lesson_id>.json`, and updates the candidate status to `promoted`. Universal promotion using `repeated_success` requires at least two distinct source projects.

`closeout_project` writes `knowledge/project-summaries/<project_id>.json`, records candidate lessons supplied by the summary, updates `knowledge/active-project.json`, and calls `refresh_bootstrap`. It does not infer lessons from free-form logs.

Use this policy core:

```python
from __future__ import annotations
import json
from pathlib import Path
from .config import FactoryConfig
from .io import atomic_write_json
from .state import refresh_bootstrap

REQUIRED = {"lesson_id", "scope", "title", "statement", "source_projects"}
SCOPES = {"asset", "profile", "universal"}
EVIDENCE = {"regression", "repeated_success", "user_approval", "asset_exception"}


class LearningPolicyError(ValueError):
    pass


def record_candidate(config: FactoryConfig, candidate: dict) -> Path:
    missing = REQUIRED - candidate.keys()
    if missing or candidate.get("scope") not in SCOPES:
        raise LearningPolicyError(f"invalid candidate: missing={sorted(missing)} scope={candidate.get('scope')}")
    path = config.root / "knowledge" / "lessons" / "candidates" / f"{candidate['lesson_id']}.json"
    if path.exists():
        raise LearningPolicyError(f"duplicate lesson id: {candidate['lesson_id']}")
    atomic_write_json(path, {**candidate, "status": "candidate", "evidence": []})
    return path


def promote_candidate(config: FactoryConfig, lesson_id: str, evidence: dict) -> Path:
    source = config.root / "knowledge" / "lessons" / "candidates" / f"{lesson_id}.json"
    if not source.is_file():
        raise LearningPolicyError(f"unknown lesson: {lesson_id}")
    candidate = json.loads(source.read_text(encoding="utf-8-sig"))
    evidence_type = evidence.get("type")
    if evidence_type not in EVIDENCE or not evidence.get("reference"):
        raise LearningPolicyError("accepted evidence type and reference are required")
    if candidate["scope"] == "universal" and evidence_type == "repeated_success" and len(set(candidate["source_projects"])) < 2:
        raise LearningPolicyError("universal repeated_success requires two source projects")
    promoted = {**candidate, "status": "promoted", "evidence": [evidence]}
    destination = config.root / "knowledge" / "lessons" / candidate["scope"] / f"{lesson_id}.json"
    atomic_write_json(destination, promoted)
    atomic_write_json(source, promoted)
    return destination


def closeout_project(config: FactoryConfig, summary: dict) -> dict:
    required = {"project_id", "status", "next_action", "candidate_lessons"}
    missing = required - summary.keys()
    if missing:
        raise LearningPolicyError(f"closeout missing keys: {sorted(missing)}")
    atomic_write_json(config.root / "knowledge" / "project-summaries" / f"{summary['project_id']}.json", summary)
    for candidate in summary["candidate_lessons"]:
        record_candidate(config, candidate)
    active_path = config.root / "knowledge" / "active-project.json"
    active = json.loads(active_path.read_text(encoding="utf-8-sig"))
    active.update({"status": summary["status"], "next_action": summary["next_action"]})
    atomic_write_json(active_path, active)
    refresh_bootstrap(config)
    return {"project_id": summary["project_id"], "status": summary["status"], "candidate_count": len(summary["candidate_lessons"])}
```

- [ ] **Step 4: Register learning commands**

```text
factory.ps1 learn candidate --input <candidate.json> --json
factory.ps1 learn promote --lesson-id <id> --evidence <evidence.json> --json
factory.ps1 learn closeout --input <summary.json> --json
```

All subcommands reject paths outside `G:` and return structured policy errors.

- [ ] **Step 5: Run tests and commit**

```powershell
& (Get-Content -Raw .tooling\runtime.json | ConvertFrom-Json).python -m unittest tests.test_learning -v
git add factory/learning.py factory/cli.py factory/schemas/lesson.schema.json tests/test_learning.py
git commit -m "feat: promote only evidenced factory lessons"
```

Expected: two tests pass.

---

### Task 8: Model Index and Transfer Manifest

**Files:**
- Create: `tests/test_transfer.py`
- Create: `factory/transfer.py`
- Modify: `factory/cli.py`
- Create: `factory/schemas/transfer.schema.json`
- Create: `tools/manifests/transfer.json`

**Interfaces:**
- Produces: `index_models(config, hash_files: bool = False) -> dict`.
- Produces: `build_transfer_manifest(config) -> dict`.
- Model entries contain `relative_path`, `size`, `sha256`, and optional sidecar metadata.
- Transfer entries contain `kind`, `path`, `version`, `source`, `license`, `size`, and `sha256`.

- [ ] **Step 1: Write failing deterministic inventory tests**

```python
import tempfile
import unittest
from pathlib import Path

from factory.config import FactoryConfig
from factory.transfer import TransferError, index_models


class TransferTest(unittest.TestCase):
    def test_model_index_is_sorted_and_relative(self):
        with tempfile.TemporaryDirectory(dir=r"G:\") as temp:
            model_root = Path(temp)
            (model_root / "checkpoints").mkdir()
            (model_root / "vae").mkdir()
            (model_root / "vae" / "b.safetensors").write_bytes(b"b")
            (model_root / "checkpoints" / "a.safetensors").write_bytes(b"a")
            root = Path(r"G:\DevWork\GameDev\BlenderAssetFactory")
            config = FactoryConfig(root, model_root, root / ".tooling", root / "reports", "http://127.0.0.1:9876", ())
            index = index_models(config, hash_files=True)
        paths = [entry["relative_path"] for entry in index["models"]]
        self.assertEqual(paths, sorted(paths))
        self.assertEqual(paths, ["checkpoints/a.safetensors", "vae/b.safetensors"])
        self.assertTrue(all(len(entry["sha256"]) == 64 for entry in index["models"]))

    def test_symlinks_outside_model_root_are_rejected(self):
        with tempfile.TemporaryDirectory(dir=r"G:\") as model_temp, tempfile.TemporaryDirectory(dir=r"G:\") as outside_temp:
            model_root = Path(model_temp)
            outside = Path(outside_temp) / "outside.safetensors"
            outside.write_bytes(b"outside")
            link = model_root / "escaped.safetensors"
            try:
                link.symlink_to(outside)
            except OSError as error:
                self.skipTest(f"Windows symlink permission unavailable: {error}")
            root = Path(r"G:\DevWork\GameDev\BlenderAssetFactory")
            config = FactoryConfig(root, model_root, root / ".tooling", root / "reports", "http://127.0.0.1:9876", ())
            with self.assertRaisesRegex(TransferError, "escapes model root"):
                index_models(config, hash_files=True)
```

- [ ] **Step 2: Run tests and verify RED**

Expected: FAIL because `factory.transfer` does not exist.

- [ ] **Step 3: Implement safe inventories**

`index_models` recursively indexes only regular files under `model_root`, excludes the `manifests` directory, rejects reparse points whose resolved targets escape `model_root`, normalizes paths to POSIX separators, optionally hashes content, and sorts by relative path. The generated index is written to `G:\LLMs\manifests\model-index.json` only when invoked through the CLI.

`build_transfer_manifest` inventories the pinned toolchain, `.tooling/runtime.json`, active Blender discovery, and model index metadata without copying binaries. Missing licenses or sources use explicit `null`, never invented values.

Use this deterministic index core:

```python
from __future__ import annotations
import json
from pathlib import Path
from .config import FactoryConfig
from .io import sha256_file


class TransferError(ValueError):
    pass


def index_models(config: FactoryConfig, hash_files: bool = False) -> dict:
    root = config.model_root.resolve(strict=True)
    models = []
    for path in sorted(config.model_root.rglob("*"), key=lambda item: item.as_posix().lower()):
        relative = path.relative_to(config.model_root)
        if relative.parts and relative.parts[0].lower() == "manifests":
            continue
        if path.is_symlink() and not path.resolve(strict=True).is_relative_to(root):
            raise TransferError(f"model link escapes model root: {relative.as_posix()}")
        if not path.is_file():
            continue
        entry = {"relative_path": relative.as_posix(), "size": path.stat().st_size, "sha256": sha256_file(path) if hash_files else None}
        sidecar = path.with_suffix(path.suffix + ".json")
        entry["metadata"] = json.loads(sidecar.read_text(encoding="utf-8-sig")) if sidecar.is_file() else None
        models.append(entry)
    return {"schema_version": 1, "model_root": str(config.model_root), "models": models}


def build_transfer_manifest(config: FactoryConfig) -> dict:
    runtime_path = config.tooling_root / "runtime.json"
    runtime = json.loads(runtime_path.read_text(encoding="utf-8-sig")) if runtime_path.is_file() else {}
    entries = [{
        "kind": "runtime", "path": value, "version": runtime.get(name + "_version"),
        "source": None, "license": None, "size": Path(value).stat().st_size if Path(value).is_file() else None,
        "sha256": sha256_file(Path(value)) if Path(value).is_file() else None,
    } for name, value in sorted((key, runtime[key]) for key in ("python", "uv") if runtime.get(key))]
    return {"schema_version": 1, "root": str(config.root), "model_root": str(config.model_root), "entries": entries}
```

- [ ] **Step 4: Register commands**

```text
factory.ps1 index-models --hash --json
factory.ps1 transfer-manifest --json
```

- [ ] **Step 5: Run tests and generate manifests**

```powershell
.\factory.ps1 index-models --hash --json
.\factory.ps1 transfer-manifest --json
& (Get-Content -Raw .tooling\runtime.json | ConvertFrom-Json).python -m unittest tests.test_transfer -v
```

Expected: deterministic model index beneath `G:\LLMs\manifests`; tracked transfer manifest contains no model binaries or credentials.

- [ ] **Step 6: Commit**

```powershell
git add factory/transfer.py factory/cli.py factory/schemas/transfer.schema.json tools/manifests/transfer.json tests/test_transfer.py
git commit -m "feat: inventory transferable factory dependencies"
```

---

### Task 9: End-to-End Continuity and Phase Verification

**Files:**
- Create: `tests/test_continuity.py`
- Create: `factory/verification.py`
- Modify: `factory/cli.py`
- Modify: `knowledge/FACTORY_STATE.md`
- Modify: `knowledge/START_HERE.md`

**Interfaces:**
- Produces: `factory.ps1 verify --json`.
- Verification runs the standard-library test suite, read-only doctor, bootstrap freshness check, transfer-manifest freshness check, and resume-state validation.
- Produces: `reports/runs/<run-id>/phase-1-verification.json`.

- [ ] **Step 1: Write the failing continuity test**

```python
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ContinuityTest(unittest.TestCase):
    def test_repository_memory_recovers_active_task(self):
        completed = subprocess.run(
            [str(Path(__import__("sys").executable)), "-m", "factory", "resume", "--json"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        result = json.loads(completed.stdout)
        self.assertTrue(result["ok"])
        self.assertEqual(result["data"]["project_id"], "ps1_ww2_pump_shotgun_01")
        self.assertEqual(result["data"]["next_action"], "finish_task_3_atlas_uv_wear")
        start = (ROOT / "knowledge" / "START_HERE.md").read_text(encoding="utf-8")
        self.assertIn("ps1_ww2_pump_shotgun_01", start)
        self.assertIn("finish_task_3_atlas_uv_wear", start)

    @unittest.skipIf(os.environ.get("BAF_VERIFY_CHILD") == "1", "avoid recursive verify child")
    def test_verify_command_records_success_on_g(self):
        completed = subprocess.run(
            [str(Path(__import__("sys").executable)), "-m", "factory", "verify", "--json"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        result = json.loads(completed.stdout)
        self.assertTrue(result["ok"])
        self.assertEqual(Path(result["data"]["report_path"]).drive.upper(), "G:")
```

- [ ] **Step 2: Run the continuity tests and verify RED**

Expected: first test may pass after Task 5; second fails because `verify` is not registered.

- [ ] **Step 3: Implement `verify` without recursive self-invocation**

The verification module must launch the suite with:

```powershell
<runtime-python> -m unittest discover -s tests -p "test_*.py" -v
```

When `verify` itself is under test, set environment variable `BAF_VERIFY_CHILD=1`; the child path skips `tests/test_continuity.py::test_verify_command_records_success_on_g` through a test-visible guard so verification cannot recursively launch itself. Record command, exit code, stdout/stderr summaries, doctor result, state checks, Git commit, and UTC timestamp in the report.

Implement `factory/verification.py` as:

```python
from __future__ import annotations
import os, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path
from .config import FactoryConfig
from .doctor import probe
from .io import atomic_write_json
from .state import refresh_bootstrap, resume_action


def verify(config: FactoryConfig) -> tuple[bool, dict]:
    environment = os.environ.copy()
    environment["BAF_VERIFY_CHILD"] = "1"
    command = [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py", "-v"]
    completed = subprocess.run(command, cwd=config.root, capture_output=True, text=True, env=environment)
    doctor_report = probe(config)
    resume = resume_action(config)
    refresh_bootstrap(config)
    checked_at = datetime.now(timezone.utc)
    run_id = checked_at.strftime("%Y%m%dT%H%M%S.%fZ")
    report_path = config.reports_root / "runs" / run_id / "phase-1-verification.json"
    mandatory = ("python", "uv", "blender", "model_root")
    mandatory_ok = all(doctor_report["capabilities"][name]["status"] == "available" for name in mandatory)
    ok = completed.returncode == 0 and mandatory_ok and bool(resume.get("next_action"))
    report = {
        "schema_version": 1,
        "ok": ok,
        "checked_at": checked_at.isoformat(),
        "command": command,
        "test_exit_code": completed.returncode,
        "stdout": completed.stdout[-12000:],
        "stderr": completed.stderr[-12000:],
        "doctor": doctor_report,
        "resume": resume,
        "report_path": str(report_path),
    }
    atomic_write_json(report_path, report)
    return ok, report
```

Register the command handler in `factory/cli.py` using:

```python
def _verify(_args: list[str]) -> tuple[int, dict]:
    from .config import FactoryConfig
    from .verification import verify
    ok, report = verify(FactoryConfig.load())
    result = envelope("verify", ok, "Phase 1 verification passed" if ok else "Phase 1 verification failed", {
        "report_path": report["report_path"], "test_exit_code": report["test_exit_code"]
    }, [] if ok else [{"code": "verification_failed", "message": "Inspect the verification report"}])
    return (0 if ok else 1), result
```

- [ ] **Step 4: Refresh generated knowledge from verified state**

Run `doctor --save`, regenerate both Markdown files, and confirm they report:

- Canonical and model roots on `G:`
- Blender 5.2 discovery
- Current bridge availability
- Active M42 Task 3 continuation
- Optional tool capabilities not yet installed
- Last successful Phase 1 verification commit

- [ ] **Step 5: Run the complete phase gate**

```powershell
.\factory.ps1 verify --json
git diff --check
git status --short
git -C .worktrees\codex-ps1-ww2-pump-shotgun status --short --branch
```

Expected:

- All Phase 1 tests pass.
- Verification report is beneath `G:\DevWork\GameDev\BlenderAssetFactory\reports\runs`.
- Root worktree contains only intended Phase 1 changes.
- M42 worktree still contains exactly its pre-existing Task 3 modifications.

- [ ] **Step 6: Commit**

```powershell
git add factory/cli.py tests/test_continuity.py knowledge/START_HERE.md knowledge/FACTORY_STATE.md
git commit -m "test: verify portable factory continuity"
```

---

## Phase 1 Completion Gate

Before moving to the Release Pipeline plan, verify all of the following:

- [ ] `.tooling` runtime, caches, reports, and models stay on `G:`.
- [ ] `factory.ps1 doctor --json` returns structured mandatory and optional capability statuses.
- [ ] `factory.ps1 resume --json` identifies the M42 Task 3 continuation exactly.
- [ ] `knowledge/START_HERE.md` is deterministic and sufficient for a fresh Codex conversation.
- [ ] Candidate lessons cannot self-promote without accepted evidence.
- [ ] Transfer manifests inventory excluded dependencies without copying or committing them.
- [ ] `factory.ps1 verify --json` passes and records its report on `G:`.
- [ ] The dirty M42 worktree remains untouched.
- [ ] Root `git diff --check` is clean.
- [ ] Every new Python behavior was introduced through a witnessed RED-to-GREEN test cycle.
