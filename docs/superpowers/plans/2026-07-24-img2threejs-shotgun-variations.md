# img2threejs Shotgun Variations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Install `hoainho/img2threejs` in the workspace and use its complete quality-gated pipeline to deliver three directly rendered procedural Three.js shotgun variations.

**Architecture:** Keep the upstream repository as an unmodified nested clone under `tools/`, and keep all experiment-owned inputs, specs, reviews, generated factories, tests, and previews under one project directory. Each variation runs an independent `img2threejs` intake, strict spec, locked-pass generation, browser render, comparison, and review cycle; a shared Vite/Vitest harness type-checks and renders the resulting factories without converting them to mesh files.

**Tech Stack:** Python 3.12 standard library, upstream `img2threejs`, TypeScript 5, Three.js 0.185.1, Vite, Vitest, Playwright Core, portable Node.js 24.17.0, Chromium/Edge.

## Global Constraints

- Use the upstream repository at `tools/img2threejs`; do not replace it with a reimplementation.
- Record the exact installed upstream commit SHA in project documentation.
- Keep upstream tracked files unmodified.
- Copy the temporary reference to `projects/img2threejs-shotgun-variations/reference/shotgun-reference.png`.
- Produce procedural TypeScript `THREE.Group` factories only; do not create Blender, GLB, FBX, or OBJ deliverables.
- Run the complete locked pass sequence independently for Field, Compact Breacher, and Trench.
- Preserve the PS1-era faceted style, fictionalized identity, and absence of manufacturer markings or extremist symbols.
- Expose named nodes, sockets, colliders, and destruction groups through `root.userData.sculptRuntime`.
- Target at most 1,200 triangles, four materials, and 30 draw calls per model; report exact measured exceptions.
- Use deterministic generated geometry and locally generated materials only.
- Do not modify unrelated dirty workspace files.
- The stale Python path used by `factory.ps1 doctor` is outside this experiment; invoke `py -3.12` directly for upstream Python scripts.

---

### Task 1: Install and pin the upstream tool

**Files:**
- Create: `.gitmodules`
- Create: `tools/img2threejs/` as a pinned Git submodule
- Create: `projects/img2threejs-shotgun-variations/upstream.json`
- Create: `projects/img2threejs-shotgun-variations/reference/shotgun-reference.png`
- Create: `projects/img2threejs-shotgun-variations/README.md`

**Interfaces:**
- Consumes: `<path-to-reference-image>.png`
- Produces: a pinned upstream clone, a durable reference path, and an experiment manifest consumed by every later task

- [ ] **Step 1: Verify exact installation and input targets**

Run:

```powershell
Test-Path 'tools\img2threejs'
Test-Path '<path-to-reference-image>.png'
```

Expected: the first command returns `False`; the second returns `True`. If the tool directory already exists, inspect its remote and HEAD instead of overwriting it.

- [ ] **Step 2: Clone the repository without modifying upstream content**

Run:

```powershell
git submodule add https://github.com/hoainho/img2threejs.git tools/img2threejs
git -C tools/img2threejs checkout --detach 7b1c62ccf34957ac5d68b7863718af9eab777c7e
git -C tools/img2threejs remote get-url origin
git -C tools/img2threejs rev-parse HEAD
git -C tools/img2threejs status --short
```

Expected: origin is `https://github.com/hoainho/img2threejs.git`, HEAD is
`7b1c62ccf34957ac5d68b7863718af9eab777c7e`, and upstream status is empty.

- [ ] **Step 3: Read the installed skill completely before using it**

Run:

```powershell
Get-Content -Raw 'tools\img2threejs\SKILL.md'
```

Expected: the complete installed `img2threejs` workflow is available, including its intake, strict-quality, locked-pass, render-review, and correction-loop rules.

- [ ] **Step 4: Create durable project inputs**

Use `apply_patch` to create `projects/img2threejs-shotgun-variations/README.md` with:

```markdown
# img2threejs Shotgun Variations

This experiment uses the unmodified `hoainho/img2threejs` workflow installed at
`../../tools/img2threejs` to reconstruct one user-supplied PS1-style pump
shotgun reference into three procedural Three.js assets.

Deliverables:

- Field Model
- Compact Breacher
- Trench Model

The source image is user-supplied reference material. This project records no
claim about third-party redistribution rights.
```

Copy the image with:

```powershell
New-Item -ItemType Directory -Force 'projects\img2threejs-shotgun-variations\reference'
Copy-Item -LiteralPath '<path-to-reference-image>.png' -Destination 'projects\img2threejs-shotgun-variations\reference\shotgun-reference.png'
```

Create `upstream.json`:

```json
{
  "repository": "https://github.com/hoainho/img2threejs.git",
  "path": "tools/img2threejs",
  "commit": "7b1c62ccf34957ac5d68b7863718af9eab777c7e",
  "reference": "reference/shotgun-reference.png"
}
```

- [ ] **Step 5: Run upstream intake smoke checks**

Run:

```powershell
py -3.12 tools\img2threejs\forge\stage1_intake\probe_image.py projects\img2threejs-shotgun-variations\reference\shotgun-reference.png
py -3.12 tools\img2threejs\forge\stage1_intake\check_reference_admission.py projects\img2threejs-shotgun-variations\reference\shotgun-reference.png
```

Expected: the PNG is decoded, dimensions are reported, and reference admission does not reject it.

- [ ] **Step 6: Commit the pinned installation metadata and reference**

Run:

```powershell
git add .gitmodules tools/img2threejs projects/img2threejs-shotgun-variations/README.md projects/img2threejs-shotgun-variations/upstream.json projects/img2threejs-shotgun-variations/reference/shotgun-reference.png
git commit -m "chore: install img2threejs experiment"
```

Expected: only `.gitmodules`, the pinned submodule pointer, and experiment
input files are committed.

---

### Task 2: Establish the TypeScript contract test and preview toolchain

**Files:**
- Create: `projects/img2threejs-shotgun-variations/package.json`
- Create: `projects/img2threejs-shotgun-variations/tsconfig.json`
- Create: `projects/img2threejs-shotgun-variations/tests/generated-models.test.ts`
- Create: `projects/img2threejs-shotgun-variations/src/index.ts`

**Interfaces:**
- Consumes: generated functions `createFieldShotgunModel`, `createCompactBreacherModel`, and `createTrenchShotgunModel`
- Produces: `ShotgunFactory`, `SHOTGUN_FACTORIES`, and a failing executable contract that all generated models must satisfy

- [ ] **Step 1: Add the project package configuration**

Use `apply_patch` to create `package.json`:

```json
{
  "name": "img2threejs-shotgun-variations",
  "version": "1.0.0",
  "private": true,
  "type": "module",
  "scripts": {
    "test": "vitest run",
    "typecheck": "tsc --noEmit",
    "build": "vite build",
    "dev": "vite"
  },
  "dependencies": {
    "three": "0.185.1"
  },
  "devDependencies": {
    "@types/three": "0.185.0",
    "typescript": "5.9.3",
    "vite": "7.2.2",
    "vitest": "4.0.8"
  }
}
```

Create `tsconfig.json`:

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "ESNext",
    "moduleResolution": "Bundler",
    "strict": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "types": ["vitest/globals"]
  },
  "include": ["src/**/*.ts", "preview/**/*.ts", "tests/**/*.ts"]
}
```

Install through the portable runtime:

```powershell
& '.\.tooling\node\node-v24.17.0-win-x64\npm.cmd' install --prefix 'projects\img2threejs-shotgun-variations'
```

Expected: `package-lock.json` and project-local `node_modules` are created.

- [ ] **Step 2: Write the failing generated-model contract**

Create `tests/generated-models.test.ts`:

```typescript
import * as THREE from 'three';
import { describe, expect, it } from 'vitest';
import {
  SHOTGUN_FACTORIES,
  type ShotgunFactory,
} from '../src/index.js';

type Runtime = {
  nodes: Record<string, THREE.Object3D>;
  sockets: Record<string, THREE.Object3D>;
  colliders: Record<string, unknown>;
  destructionGroups: Record<string, THREE.Object3D[]>;
};

function metrics(root: THREE.Object3D) {
  let triangles = 0;
  let drawCalls = 0;
  const materials = new Set<string>();
  root.traverse((object) => {
    if (!(object instanceof THREE.Mesh)) return;
    drawCalls += 1;
    const geometry = object.geometry;
    triangles += geometry.index
      ? geometry.index.count / 3
      : geometry.attributes.position.count / 3;
    const meshMaterials = Array.isArray(object.material)
      ? object.material
      : [object.material];
    for (const material of meshMaterials) materials.add(material.uuid);
  });
  return { triangles, drawCalls, materials: materials.size };
}

function createTwice(factory: ShotgunFactory) {
  const first = factory();
  const second = factory();
  first.updateMatrixWorld(true);
  second.updateMatrixWorld(true);
  return { first, second };
}

describe('generated shotgun factories', () => {
  it('exports exactly three distinct factories', () => {
    expect(Object.keys(SHOTGUN_FACTORIES)).toEqual([
      'field',
      'compact-breacher',
      'trench',
    ]);
  });

  it.each(Object.entries(SHOTGUN_FACTORIES))(
    '%s exposes the action-ready runtime contract',
    (_id, factory) => {
      const root = factory();
      const runtime = root.userData.sculptRuntime as Runtime;
      expect(root).toBeInstanceOf(THREE.Group);
      expect(runtime).toBeDefined();
      expect(Object.keys(runtime.nodes)).toEqual(
        expect.arrayContaining([
          'stock',
          'receiver',
          'barrel',
          'magazine',
          'pump',
          'trigger',
          'trigger-guard',
        ]),
      );
      expect(Object.keys(runtime.sockets)).toEqual(
        expect.arrayContaining([
          'muzzle',
          'right-hand',
          'left-hand',
          'shell-ejection',
        ]),
      );
      expect(Object.keys(runtime.colliders)).toEqual(
        expect.arrayContaining(['stock', 'receiver', 'barrel-assembly']),
      );
      expect(Object.keys(runtime.destructionGroups)).toEqual(
        expect.arrayContaining(['stock', 'receiver', 'barrel-assembly', 'pump']),
      );
    },
  );

  it.each(Object.entries(SHOTGUN_FACTORIES))(
    '%s is deterministic and within the runtime budget',
    (_id, factory) => {
      const { first, second } = createTwice(factory);
      expect(new THREE.Box3().setFromObject(first)).toEqual(
        new THREE.Box3().setFromObject(second),
      );
      const result = metrics(first);
      expect(result.triangles).toBeLessThanOrEqual(1200);
      expect(result.drawCalls).toBeLessThanOrEqual(30);
      expect(result.materials).toBeLessThanOrEqual(4);
    },
  );

  it('uses visibly distinct proportions', () => {
    const bounds = Object.values(SHOTGUN_FACTORIES).map((factory) =>
      new THREE.Box3().setFromObject(factory()).getSize(new THREE.Vector3()),
    );
    expect(bounds[1].x).toBeLessThan(bounds[0].x * 0.82);
    expect(bounds[2].z).toBeGreaterThan(bounds[0].z);
  });
});
```

- [ ] **Step 3: Add the intended registry API before factories exist**

Create `src/index.ts`:

```typescript
import type * as THREE from 'three';
import { createFieldShotgunModel } from './createFieldShotgunModel.js';
import { createCompactBreacherModel } from './createCompactBreacherModel.js';
import { createTrenchShotgunModel } from './createTrenchShotgunModel.js';

export type ShotgunFactory = () => THREE.Group;

export const SHOTGUN_FACTORIES = {
  field: createFieldShotgunModel,
  'compact-breacher': createCompactBreacherModel,
  trench: createTrenchShotgunModel,
} satisfies Record<string, ShotgunFactory>;

export {
  createFieldShotgunModel,
  createCompactBreacherModel,
  createTrenchShotgunModel,
};
```

- [ ] **Step 4: Run the test and verify the expected red state**

Run:

```powershell
& '.\.tooling\node\node-v24.17.0-win-x64\npm.cmd' test --prefix 'projects\img2threejs-shotgun-variations'
```

Expected: FAIL because the three generated factory modules do not exist.

- [ ] **Step 5: Commit the red contract**

Run:

```powershell
git add projects/img2threejs-shotgun-variations/package.json projects/img2threejs-shotgun-variations/package-lock.json projects/img2threejs-shotgun-variations/tsconfig.json projects/img2threejs-shotgun-variations/src/index.ts projects/img2threejs-shotgun-variations/tests/generated-models.test.ts
git commit -m "test: define procedural shotgun contract"
```

---

### Task 3: Generate and review the Field Model

**Files:**
- Create: `projects/img2threejs-shotgun-variations/field/assessment.json`
- Create: `projects/img2threejs-shotgun-variations/field/detail-inventory.json`
- Create: `projects/img2threejs-shotgun-variations/field/object-sculpt-spec.json`
- Create: `projects/img2threejs-shotgun-variations/field/renders/`
- Create: `projects/img2threejs-shotgun-variations/field/reviews/`
- Create: `projects/img2threejs-shotgun-variations/src/createFieldShotgunModel.ts`

**Interfaces:**
- Consumes: the durable reference and upstream intake/spec/build/review scripts
- Produces: `createFieldShotgunModel(): THREE.Group` with the baseline proportions and runtime contract

- [ ] **Step 1: Generate intake artifacts using upstream scripts**

Run:

```powershell
New-Item -ItemType Directory -Force 'projects\img2threejs-shotgun-variations\field\renders','projects\img2threejs-shotgun-variations\field\reviews'
py -3.12 tools\img2threejs\forge\stage2_spec\new_pre_spec_assessment.py "Field Shotgun" --image projects\img2threejs-shotgun-variations\reference\shotgun-reference.png --complexity complex --out projects\img2threejs-shotgun-variations\field\assessment.json
py -3.12 tools\img2threejs\forge\stage1_intake\build_detail_inventory.py projects\img2threejs-shotgun-variations\reference\shotgun-reference.png --mode grid-3x3 --out-dir projects\img2threejs-shotgun-variations\field\detail-zones --out projects\img2threejs-shotgun-variations\field\detail-inventory.json
py -3.12 tools\img2threejs\forge\stage2_spec\new_sculpt_spec.py "Field Shotgun" --image projects\img2threejs-shotgun-variations\reference\shotgun-reference.png --assessment projects\img2threejs-shotgun-variations\field\assessment.json --out projects\img2threejs-shotgun-variations\field\object-sculpt-spec.json
```

Expected: assessment, zone crops, detail inventory, and starter spec are created by the installed repository.

- [ ] **Step 2: Author the exact Field Model spec**

Edit only the generated assessment/spec artifacts. Set `objectClass.primaryDomain` to `object`; declare macro components `stock`, `receiver`, `barrel`, `magazine`, `pump`, `trigger`, and `trigger-guard`; add the ejection port, muzzle opening, front bead, pump ribs, receiver pins, butt plate, and stock facets to the detail inventory and map each entry to a component or material override.

Use three materials: `field-wood`, `blued-steel`, and `mechanical-black`. Add sockets `muzzle`, `right-hand`, `left-hand`, and `shell-ejection`; colliders `stock`, `receiver`, and `barrel-assembly`; destruction groups `stock`, `receiver`, `barrel-assembly`, and `pump`. Set the pump pivot axis to the barrel axis and the trigger pivot to its pin.

- [ ] **Step 3: Run both upstream spec gates**

Run:

```powershell
py -3.12 tools\img2threejs\forge\stage2_spec\validate_sculpt_spec.py projects\img2threejs-shotgun-variations\field\object-sculpt-spec.json
py -3.12 tools\img2threejs\forge\stage2_spec\validate_sculpt_spec.py projects\img2threejs-shotgun-variations\field\object-sculpt-spec.json --strict-quality
```

Expected: both commands exit zero. Refine the generated spec until strict-quality passes; do not use a bypass flag.

- [ ] **Step 4: Execute every locked build and review pass**

For each pass in this exact order:

```text
blockout
structural-pass
form-refinement
material-pass
surface-pass
lighting-pass
interaction-pass
optimization-pass
```

For each literal pass name, run the upstream status/check/generate sequence
and render the current factory in the project browser harness. Use this
PowerShell loop for the deterministic comparison and diagnostic commands:

```powershell
$passIds = @(
  'blockout',
  'structural-pass',
  'form-refinement',
  'material-pass',
  'surface-pass',
  'lighting-pass',
  'interaction-pass',
  'optimization-pass'
)
foreach ($passId in $passIds) {
  $renderPath = "projects\img2threejs-shotgun-variations\field\renders\$passId.png"
  $comparisonPath = "projects\img2threejs-shotgun-variations\field\reviews\$passId-comparison.png"
  py -3.12 tools\img2threejs\forge\stage4_review\make_comparison_sheet.py --reference projects\img2threejs-shotgun-variations\reference\shotgun-reference.png --render $renderPath --out $comparisonPath --json
  py -3.12 tools\img2threejs\forge\stage4_review\diagnose_render.py $renderPath --spec projects\img2threejs-shotgun-variations\field\object-sculpt-spec.json --in-place
  py -3.12 tools\img2threejs\forge\stage3_build\orchestrate_passes.py check projects\img2threejs-shotgun-variations\field\object-sculpt-spec.json --pass-id $passId
}
```

Execute the loop one pass at a time because later passes remain locked until
the current review is appended. Inspect each comparison visually, write
feature-review JSON with evidence for silhouette, receiver/stock transition,
barrel/magazine spacing, pump placement, and the current pass's detail target,
then append a `continue`, `refine-spec`, or `refine-code` review using
`append_review.py`. A `continue` decision requires the upstream thresholds and
real screenshot paths.

- [ ] **Step 5: Generate the final Field factory**

Run:

```powershell
py -3.12 tools\img2threejs\forge\stage3_build\generate_threejs_factory.py projects\img2threejs-shotgun-variations\field\object-sculpt-spec.json --out projects\img2threejs-shotgun-variations\src\createFieldShotgunModel.ts --force
```

Expected: the final factory is generated from the fully reviewed spec.

- [ ] **Step 6: Run the contract test and confirm partial progress**

Run the project test command from Task 2.

Expected: resolution now succeeds for the Field module and still fails because Compact Breacher and Trench modules do not exist.

- [ ] **Step 7: Commit Field evidence and output**

Run:

```powershell
git add projects/img2threejs-shotgun-variations/field projects/img2threejs-shotgun-variations/src/createFieldShotgunModel.ts
git commit -m "feat: generate field shotgun with img2threejs"
```

---

### Task 4: Generate and review the Compact Breacher

**Files:**
- Create: `projects/img2threejs-shotgun-variations/compact-breacher/`
- Create: `projects/img2threejs-shotgun-variations/src/createCompactBreacherModel.ts`

**Interfaces:**
- Consumes: the same durable reference, but an independent assessment, detail inventory, spec, and pass history
- Produces: `createCompactBreacherModel(): THREE.Group` with a length below 82% of the Field Model

- [ ] **Step 1: Run the same upstream intake commands with the Compact Breacher paths and name**

Use `Compact Breacher` and
`projects/img2threejs-shotgun-variations/compact-breacher` in the Task 3
intake commands.

Expected: independent assessment, detail inventory, and spec files are created; no Field file is copied as the finished result.

- [ ] **Step 2: Author and strict-validate the Compact Breacher spec**

Keep the shared required components and runtime contract. Shorten the barrel and magazine together, shorten the stock with a compact grip transition, widen the pump, add a heavy muzzle collar, enlarge the trigger guard, and add a `muzzle-attachment` socket. Use `breacher-grip`, `worn-steel`, and `mechanical-black` materials. The bounding-box length target is less than 82% of the Field Model.

Run both validation commands from Task 3 against the Compact Breacher spec.

Expected: strict-quality exits zero without weakening the detail inventory.

- [ ] **Step 3: Complete all eight locked passes with real render evidence**

Use the Task 3 pass sequence and upstream review commands with
`compact-breacher` paths. Compare shared anatomy to the source image, but judge
the intentionally shortened silhouette against the locked Compact Breacher
spec and multi-angle self-consistency.

Expected: every pass reaches an evidence-backed `continue`; failed passes are corrected before proceeding.

- [ ] **Step 4: Generate the final Compact Breacher factory**

Run:

```powershell
py -3.12 tools\img2threejs\forge\stage3_build\generate_threejs_factory.py projects\img2threejs-shotgun-variations\compact-breacher\object-sculpt-spec.json --out projects\img2threejs-shotgun-variations\src\createCompactBreacherModel.ts --force
```

- [ ] **Step 5: Run tests and commit**

Run the Task 2 test command.

Expected: only the missing Trench module prevents the full suite from executing.

Commit:

```powershell
git add projects/img2threejs-shotgun-variations/compact-breacher projects/img2threejs-shotgun-variations/src/createCompactBreacherModel.ts
git commit -m "feat: generate compact breacher with img2threejs"
```

---

### Task 5: Generate and review the Trench Model

**Files:**
- Create: `projects/img2threejs-shotgun-variations/trench/`
- Create: `projects/img2threejs-shotgun-variations/src/createTrenchShotgunModel.ts`

**Interfaces:**
- Consumes: the durable reference and an independent full upstream pipeline
- Produces: `createTrenchShotgunModel(): THREE.Group` with heat shield, sling sockets, and bayonet-lug silhouette

- [ ] **Step 1: Run the same upstream intake commands with the Trench paths and name**

Use `Trench Shotgun` and
`projects/img2threejs-shotgun-variations/trench` in the Task 3 intake commands.

- [ ] **Step 2: Author and strict-validate the Trench spec**

Keep the baseline full-stock and long-barrel anatomy. Add a perforated heat
shield, reinforced ribbed pump, front and rear sling sockets, bayonet-lug
silhouette without a blade, receiver bands, and protected front bead.
Represent repeated shield holes and pump ribs as repetition systems. Use
`trench-walnut`, `parkerized-steel`, `mechanical-black`, and
`worn-edge-accent` materials. The heat shield must make the Trench Model's
vertical bound larger than the Field Model's.

Run both upstream validation commands against the Trench spec.

- [ ] **Step 3: Complete all eight locked passes with real render evidence**

Use the Task 3 pass/review cycle with `trench` paths. Judge intentional heat
shield and lug differences against the locked Trench spec, and use at least two
orbit views to reject flat or floating shield geometry.

- [ ] **Step 4: Generate the final Trench factory**

Run:

```powershell
py -3.12 tools\img2threejs\forge\stage3_build\generate_threejs_factory.py projects\img2threejs-shotgun-variations\trench\object-sculpt-spec.json --out projects\img2threejs-shotgun-variations\src\createTrenchShotgunModel.ts --force
```

- [ ] **Step 5: Run the full contract test**

Run the Task 2 test command.

Expected: all imports resolve. Fix generated spec/code through the upstream correction path until all hierarchy, deterministic-bounds, distinct-proportion, and runtime-budget assertions pass.

- [ ] **Step 6: Commit Trench evidence and output**

```powershell
git add projects/img2threejs-shotgun-variations/trench projects/img2threejs-shotgun-variations/src/createTrenchShotgunModel.ts
git commit -m "feat: generate trench shotgun with img2threejs"
```

---

### Task 6: Build the direct Three.js browser gallery

**Files:**
- Create: `projects/img2threejs-shotgun-variations/index.html`
- Create: `projects/img2threejs-shotgun-variations/preview/main.ts`
- Create: `projects/img2threejs-shotgun-variations/preview/style.css`
- Create: `projects/img2threejs-shotgun-variations/tests/preview.test.ts`

**Interfaces:**
- Consumes: `SHOTGUN_FACTORIES`
- Produces: a direct TypeScript browser gallery with model switching, orbit controls, fixed views, evaluation rendering, and measured metrics

- [ ] **Step 1: Write the failing preview-source test**

Create `tests/preview.test.ts`:

```typescript
import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

const html = readFileSync(new URL('../index.html', import.meta.url), 'utf8');
const source = readFileSync(new URL('../preview/main.ts', import.meta.url), 'utf8');

describe('preview gallery', () => {
  it('offers all model and camera choices', () => {
    expect(html).toContain('model-select');
    expect(source).toContain('SHOTGUN_FACTORIES');
    for (const view of ['reference', 'opposite', 'muzzle', 'top', 'three-quarter']) {
      expect(source).toContain(`'${view}'`);
    }
  });

  it('reports runtime metrics without presentation post-processing', () => {
    expect(source).toContain('triangleCount');
    expect(source).toContain('drawCalls');
    expect(source).toContain('materialCount');
    expect(source).not.toContain('UnrealBloomPass');
    expect(source).not.toContain('BokehPass');
  });
});
```

- [ ] **Step 2: Run the preview test and verify red**

Run the Task 2 test command.

Expected: FAIL because `index.html` and `preview/main.ts` do not exist.

- [ ] **Step 3: Implement the smallest gallery satisfying the design**

Create a semantic `index.html` containing a model selector, camera-view
selector, metrics panel, and full-window canvas mount. In `preview/main.ts`,
create a `WebGLRenderer`, `Scene`, `PerspectiveCamera`, neutral hemisphere and
directional lights, `OrbitControls`, model-switch disposal, bounding-box
auto-framing, stable view vectors for the five required view names, and a
traversal that computes triangles, mesh draw calls, unique materials, and
bounds. Import only `SHOTGUN_FACTORIES`, Three.js, OrbitControls, and
`preview/style.css`; do not add post-processing.

- [ ] **Step 4: Run test, type-check, and build**

Run:

```powershell
& '.\.tooling\node\node-v24.17.0-win-x64\npm.cmd' test --prefix 'projects\img2threejs-shotgun-variations'
& '.\.tooling\node\node-v24.17.0-win-x64\npm.cmd' run typecheck --prefix 'projects\img2threejs-shotgun-variations'
& '.\.tooling\node\node-v24.17.0-win-x64\npm.cmd' run build --prefix 'projects\img2threejs-shotgun-variations'
```

Expected: tests and type-check pass; Vite emits `dist/index.html` and bundled assets.

- [ ] **Step 5: Commit the gallery**

```powershell
git add projects/img2threejs-shotgun-variations/index.html projects/img2threejs-shotgun-variations/preview projects/img2threejs-shotgun-variations/tests/preview.test.ts
git commit -m "feat: add img2threejs shotgun gallery"
```

---

### Task 7: Capture final runtime evidence and close the experiment

**Files:**
- Create: `projects/img2threejs-shotgun-variations/evidence/field.png`
- Create: `projects/img2threejs-shotgun-variations/evidence/compact-breacher.png`
- Create: `projects/img2threejs-shotgun-variations/evidence/trench.png`
- Create: `projects/img2threejs-shotgun-variations/evidence/contact-sheet.png`
- Create: `projects/img2threejs-shotgun-variations/evidence/metrics.json`
- Modify: `projects/img2threejs-shotgun-variations/README.md`

**Interfaces:**
- Consumes: the production Vite build and all three factories
- Produces: browser proof, measured performance, visual comparison, and documented usage

- [ ] **Step 1: Serve the production build on loopback**

Run the Vite preview server with the portable Node runtime on an available
loopback port and keep its process ID for cleanup.

Expected: the gallery responds over `127.0.0.1` and does not require external network access.

- [ ] **Step 2: Capture one stable three-quarter screenshot and metrics for each model**

Use Playwright Core with the installed Chrome or Edge executable. For each
selector value, choose the three-quarter camera, wait for
`renderer.info.render.frame` to advance, read the metrics panel, and save a PNG
under `evidence/`.

Expected: all three screenshots are non-empty and the reported model name,
triangles, draw calls, materials, and bounds match the selected factory.

- [ ] **Step 3: Inspect all screenshots visually**

Verify:

- Field retains the source's long full-stock pump-shotgun silhouette.
- Compact Breacher is materially shorter rather than uniformly rescaled.
- Trench exposes a coherent volumetric shield, reinforced pump, and lug.
- No part floats, collapses from an orbit view, or intersects implausibly.
- Materials remain legible against the neutral background.

If a defect appears, return to the owning variation's upstream
`refine-spec`/`refine-code` cycle and regenerate its final factory.

- [ ] **Step 4: Package comparison evidence**

Use the upstream comparison-sheet utility or the factory's existing
contact-sheet tool to place the three final screenshots in one labeled sheet.
Write `metrics.json` with exact values read from the runtime, the upstream SHA,
the reference hash, and the final factory paths.

- [ ] **Step 5: Document direct usage**

Append to the project README:

```typescript
import { createFieldShotgunModel } from './src/index.js';

const shotgun = createFieldShotgunModel();
scene.add(shotgun);

const runtime = shotgun.userData.sculptRuntime;
runtime.nodes.pump.position.x -= 0.08;
```

Also list the Compact Breacher and Trench factory names, preview command, test
command, exact upstream SHA, and any measured target exceptions.

- [ ] **Step 6: Run the complete verification suite**

Run:

```powershell
git -C tools/img2threejs status --short
& '.\.tooling\node\node-v24.17.0-win-x64\npm.cmd' test --prefix 'projects\img2threejs-shotgun-variations'
& '.\.tooling\node\node-v24.17.0-win-x64\npm.cmd' run typecheck --prefix 'projects\img2threejs-shotgun-variations'
& '.\.tooling\node\node-v24.17.0-win-x64\npm.cmd' run build --prefix 'projects\img2threejs-shotgun-variations'
git diff --check
```

Expected: upstream status is empty; tests, type-check, and build pass; the repository diff has no whitespace errors.

- [ ] **Step 7: Commit final evidence and documentation**

```powershell
git add projects/img2threejs-shotgun-variations/README.md projects/img2threejs-shotgun-variations/evidence
git commit -m "docs: verify img2threejs shotgun variations"
```
