# PS1 WWII Pump Shotgun Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a visibly staged, fictional WWII pump-action shotgun in the open Blender viewport and export a validated sub-450-triangle GLB asset.

**Architecture:** A JSON specification defines immutable asset constraints. A Blender Python builder exposes deterministic stage functions and a timer-driven live entry point; the same stages can run synchronously for headless verification. A separate validator imports the exported GLB into a clean Blender process and enforces geometry, materials, orientation, and output requirements.

**Tech Stack:** Blender 5.2 LTS, Blender Python API (`bpy`/`mathutils`), JSON, glTF 2.0/GLB, Python `unittest`, Blender MCP localhost bridge.

## Global Constraints

- Canonical root: `G:\DevWork\GameDev\BlenderAssetFactory`.
- Canonical output: `assets\ps1_ww2_pump_shotgun_01`.
- Visual mesh triangle budget: 450 maximum.
- Scale: one Blender unit equals one metre; target overall length approximately 1.02 metres.
- Orientation: barrel along positive X, Z up; glTF export uses Y-up.
- Materials: exactly three lightweight colour materials and no image textures.
- Live build: recognizable stages appear every 0.7–1.0 seconds without blocking the Blender interface.
- Safety: fictional external game prop only; no internal mechanism or manufacturing geometry.

---

### Task 1: Asset Specification and Contract Test

**Files:**
- Create: `specs/ps1_ww2_pump_shotgun_01.json`
- Create: `tests/test_ps1_ww2_pump_shotgun_spec.py`

**Interfaces:**
- Produces: JSON keys `asset_id`, `generator`, `triangle_budget`, `target_length_m`, `stage_interval_seconds`, `palette`, and `output_directory`.
- Consumed by: `scripts/live_build_ps1_shotgun.py` and `scripts/validate_ps1_shotgun_glb.py`.

- [ ] **Step 1: Write the failing contract test**

```python
import json
import unittest
from pathlib import Path

ROOT = Path(r"G:\DevWork\GameDev\BlenderAssetFactory")
SPEC = ROOT / "specs" / "ps1_ww2_pump_shotgun_01.json"

class ShotgunSpecTest(unittest.TestCase):
    def test_contract(self):
        data = json.loads(SPEC.read_text(encoding="utf-8"))
        self.assertEqual(data["asset_id"], "ps1_ww2_pump_shotgun_01")
        self.assertEqual(data["generator"], "ps1_ww2_pump_shotgun")
        self.assertLessEqual(data["triangle_budget"], 450)
        self.assertAlmostEqual(data["target_length_m"], 1.02, places=2)
        self.assertGreaterEqual(data["stage_interval_seconds"], 0.7)
        self.assertLessEqual(data["stage_interval_seconds"], 1.0)
        self.assertEqual(set(data["palette"]), {"walnut", "steel", "accent"})
        self.assertEqual(
            data["output_directory"],
            "G:/DevWork/GameDev/BlenderAssetFactory/assets",
        )

if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the test and verify the missing spec fails**

Run:

```powershell
py -3.12 tests\test_ps1_ww2_pump_shotgun_spec.py -v
```

Expected: `FileNotFoundError` for `ps1_ww2_pump_shotgun_01.json`.

- [ ] **Step 3: Add the minimal specification**

```json
{
  "schema_version": 1,
  "asset_id": "ps1_ww2_pump_shotgun_01",
  "display_name": "PS1 WWII Pump Shotgun 01",
  "generator": "ps1_ww2_pump_shotgun",
  "style": "ps1_ww2_survival_horror",
  "triangle_budget": 450,
  "target_length_m": 1.02,
  "stage_interval_seconds": 0.85,
  "palette": {
    "walnut": [0.20, 0.075, 0.025, 1.0],
    "steel": [0.055, 0.07, 0.085, 1.0],
    "accent": [0.012, 0.014, 0.018, 1.0]
  },
  "output_directory": "G:/DevWork/GameDev/BlenderAssetFactory/assets"
}
```

- [ ] **Step 4: Run the contract test**

Expected: one test passes.

- [ ] **Step 5: Commit**

```powershell
git add specs/ps1_ww2_pump_shotgun_01.json tests/test_ps1_ww2_pump_shotgun_spec.py
git commit -m "test: define PS1 shotgun asset contract"
```

### Task 2: Deterministic Geometry and Live Stage Orchestrator

**Files:**
- Create: `scripts/live_build_ps1_shotgun.py`
- Test: `tests/test_ps1_ww2_pump_shotgun_spec.py`

**Interfaces:**
- Consumes: the Task 1 JSON contract.
- Produces: `build_stage(index: int) -> float | None`, `run_all_sync() -> dict`, and timer entry point `start_live_build() -> dict`.
- Scene contract: collection `SHOTGUN_BUILD`, scene property `ps1_shotgun_build_status`, final object `Asset_PS1_WW2_Pump_Shotgun_01`, collision object `COLLISION_PS1_WW2_Pump_Shotgun_01`.

- [ ] **Step 1: Extend the contract test with static builder requirements**

```python
BUILDER = ROOT / "scripts" / "live_build_ps1_shotgun.py"

def test_builder_contract(self):
    source = BUILDER.read_text(encoding="utf-8")
    for token in (
        "def build_stage(",
        "def run_all_sync(",
        "def start_live_build(",
        "bpy.app.timers.register",
        '"Asset_PS1_WW2_Pump_Shotgun_01"',
        '"COLLISION_PS1_WW2_Pump_Shotgun_01"',
    ):
        self.assertIn(token, source)
```

- [ ] **Step 2: Run the test and verify the missing builder fails**

Expected: `FileNotFoundError` for `live_build_ps1_shotgun.py`.

- [ ] **Step 3: Implement focused construction helpers**

Implement these exact helpers in `live_build_ps1_shotgun.py`:

```python
def make_material(name: str, rgba: list[float]) -> bpy.types.Material: ...
def add_box(name: str, location: tuple, dimensions: tuple, material) -> bpy.types.Object: ...
def add_cylinder(name: str, location: tuple, radius: float, depth: float, material, vertices: int = 8) -> bpy.types.Object: ...
def add_wedge(name: str, vertices: list[tuple], material) -> bpy.types.Object: ...
def select_and_focus(obj: bpy.types.Object) -> None: ...
def triangle_count(obj: bpy.types.Object) -> int: ...
```

`add_box` uses a unit cube with applied scale. `add_cylinder` uses eight radial vertices and rotates the cylinder 90 degrees around Y so its length follows X. `add_wedge` accepts eight corner vertices and creates twelve triangular faces. Every polygon uses flat shading.

- [ ] **Step 4: Implement the twelve visible stages**

Create `STAGES`, containing functions in this order:

```python
STAGES = [
    stage_reset,
    stage_receiver,
    stage_barrel,
    stage_magazine_tube,
    stage_stock,
    stage_pump,
    stage_heat_shield,
    stage_controls,
    stage_sights_and_lug,
    stage_material_finish,
    stage_collision,
    stage_finalize_export,
]
```

Each stage sets `scene["ps1_shotgun_build_status"]`, selects its newest component, calls `select_and_focus`, and returns without sleeping.

- [ ] **Step 5: Implement non-blocking timer orchestration**

```python
def build_stage(index: int):
    STAGES[index]()
    next_index = index + 1
    if next_index >= len(STAGES):
        return None
    bpy.app.timers.register(
        lambda: build_stage(next_index),
        first_interval=SPEC["stage_interval_seconds"],
    )
    return None

def start_live_build():
    bpy.app.timers.register(lambda: build_stage(0), first_interval=0.25)
    return {"scheduled": True, "stages": len(STAGES)}
```

- [ ] **Step 6: Implement synchronous execution for verification**

```python
def run_all_sync():
    for stage in STAGES:
        stage()
    return REPORT

if globals().get("args", {}).get("mode") == "live":
    __result__ = start_live_build()
elif __name__ == "__main__" or globals().get("args", {}).get("mode") == "sync":
    __result__ = run_all_sync()
```

- [ ] **Step 7: Run contract tests**

Expected: two tests pass.

- [ ] **Step 8: Commit**

```powershell
git add scripts/live_build_ps1_shotgun.py tests/test_ps1_ww2_pump_shotgun_spec.py
git commit -m "feat: add staged PS1 shotgun builder"
```

### Task 3: Export, Portability Validation, and Live Acceptance

**Files:**
- Create: `scripts/validate_ps1_shotgun_glb.py`
- Create during execution: `assets/ps1_ww2_pump_shotgun_01/*`

**Interfaces:**
- Consumes: generated GLB and manifest from Task 2.
- Produces: console marker `SHOTGUN_GLB_VALIDATION_OK` and exit code zero.

- [ ] **Step 1: Write the validator before generating output**

```python
import json
from pathlib import Path
import bpy

ROOT = Path(r"G:\DevWork\GameDev\BlenderAssetFactory")
OUT = ROOT / "assets" / "ps1_ww2_pump_shotgun_01"
manifest = json.loads((OUT / "manifest.json").read_text(encoding="utf-8"))

bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)
bpy.ops.import_scene.gltf(filepath=str(OUT / "ps1_ww2_pump_shotgun_01.glb"))
meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
assert manifest["triangles"] <= 450
assert manifest["material_count"] == 3
assert manifest["within_budget"] is True
assert any(obj.name.startswith("Asset_PS1_WW2_Pump_Shotgun_01") for obj in meshes)
print(f"SHOTGUN_GLB_VALIDATION_OK meshes={len(meshes)} triangles={manifest['triangles']}")
```

- [ ] **Step 2: Verify validation fails before output exists**

Run Blender headlessly with `validate_ps1_shotgun_glb.py`.

Expected: missing `manifest.json` or GLB.

- [ ] **Step 3: Run a synchronous factory build**

```powershell
& 'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe' `
  --background --factory-startup `
  --python 'G:\DevWork\GameDev\BlenderAssetFactory\scripts\live_build_ps1_shotgun.py' `
  -- --mode sync
```

Expected: `.blend`, `.glb`, preview PNG, and `manifest.json` exist; manifest reports at most 450 triangles.

- [ ] **Step 4: Run portability validation**

Expected: `SHOTGUN_GLB_VALIDATION_OK` and exit code zero.

- [ ] **Step 5: Launch the live build through Blender MCP**

Call `blender_python_exec` with:

```json
{
  "script_path": "G:\\DevWork\\GameDev\\BlenderAssetFactory\\scripts\\live_build_ps1_shotgun.py",
  "args": {"mode": "live"},
  "timeout_seconds": 30
}
```

Expected: immediate scheduling response while the open Blender viewport remains responsive and shows all twelve stages.

- [ ] **Step 6: Verify live completion and MCP health**

Poll scene property `ps1_shotgun_build_status` until it equals `complete`. Then call `blender_scene_get_info` and confirm the bridge responds without error.

- [ ] **Step 7: Commit**

```powershell
git add scripts/validate_ps1_shotgun_glb.py assets/ps1_ww2_pump_shotgun_01
git commit -m "feat: export validated PS1 WWII pump shotgun"
```
