# img2threejs Shotgun Variations Design

Date: 2026-07-24
Status: Approved design awaiting written-spec review

## Objective

Install `hoainho/img2threejs` inside this workspace and use that repository's
quality-gated reconstruction workflow to create three procedural Three.js
shotgun assets from the user-supplied reference image.

This is a focused evaluation of `img2threejs`. The deliverables are
TypeScript `THREE.Group` factories and browser-rendered evidence. Blender,
GLB conversion, and the factory's existing mesh-generation pipeline are
outside scope.

## Source and Installation Boundaries

- Install the upstream repository at `tools/img2threejs`.
- Record the exact upstream commit SHA selected from `main` at installation
  time so the experiment is reproducible.
- Preserve the upstream Git history and do not modify its tracked files merely
  to make the generated assets pass.
- Copy the supplied reference image into
  `projects/img2threejs-shotgun-variations/reference/shotgun-reference.png`
  so the build does not depend on a temporary clipboard path.
- Store every generated assessment, spec, review artifact, factory, test, and
  preview beneath `projects/img2threejs-shotgun-variations`.
- Treat the image as user-supplied reference material. Do not infer or claim
  redistribution rights.

## Visual Direction

All three assets retain the supplied image's deliberately low-resolution,
faceted PS1-era presentation: dark steel, subdued wood or polymer, strong
silhouette, simplified mechanical detail, and no manufacturer markings.
They are fictionalized game props rather than replicas of a specific firearm.

### Variation A: Field Model

The reference-faithful baseline:

- full shoulder stock with a narrow wrist;
- long single barrel;
- tubular magazine beneath the barrel;
- long ribbed pump;
- compact receiver with a top ejection port;
- trigger, trigger guard, front bead, and muzzle opening.

This model establishes the shared proportion language and is the primary
reference-comparison target.

### Variation B: Compact Breacher

A short, aggressive gameplay silhouette:

- shortened barrel and magazine tube;
- shortened stock with a compact grip transition;
- wider reinforced pump;
- heavy muzzle collar;
- compact receiver and enlarged trigger guard;
- attachment socket near the muzzle for optional effects.

It must be visibly distinct at thumbnail scale and may not be produced by
scaling the complete Field Model uniformly.

### Variation C: Trench Model

A reinforced wartime configuration:

- full stock and long barrel;
- perforated heat-shield silhouette;
- reinforced ribbed pump;
- front and rear sling sockets;
- bayonet-lug silhouette without a blade;
- heavier receiver bands and a protected front bead.

The design remains fictionalized and contains no logos, unit marks, extremist
symbols, or copied decorative engraving.

## Reconstruction Approach

Run the complete `img2threejs` workflow independently for each variation.
Do not generate one finished factory and hand-edit two derivatives.

For each variation:

1. Probe and admit the reference image.
2. Write a pre-spec assessment classifying it as a complex hard-surface object.
3. Build a detail inventory covering silhouette, receiver, stock, pump,
   barrel, magazine, trigger assembly, muzzle, and variation-specific details.
4. Author and strict-validate an `ObjectSculptSpec`.
5. Execute the repository's locked build sequence:
   `blockout`, `structural-pass`, `form-refinement`, `material-pass`,
   `surface-pass`, `lighting-pass`, `interaction-pass`, and
   `optimization-pass`.
6. Generate only the currently unlocked factory pass.
7. Render standardized reference and orbit views in a browser.
8. Produce comparison sheets, record evidence-bearing reviews, and correct
   failed passes within the repository's bounded correction loop.

The Field Model uses the supplied reference directly for visual comparison.
The Compact Breacher and Trench Model use it for shared anatomy and material
language; their intentional silhouette differences are assessed against their
own locked specs and multi-angle self-consistency rather than penalized for
departing from the baseline outline.

## Generated Factory Contract

Each factory:

- is TypeScript using plain Three.js;
- exports a creation function returning `THREE.Group`;
- constructs geometry from primitives, generated profiles, extrusions, tubes,
  and instancing supported by `img2threejs`;
- uses deterministic values with no runtime randomness;
- uses a modular hierarchy instead of one inert mesh;
- exposes `root.userData.sculptRuntime`.

The runtime metadata must provide:

- named nodes for stock, receiver, barrel, magazine, pump, trigger, and guard;
- a pump translation pivot constrained to the magazine axis;
- a trigger rotation pivot;
- muzzle, right-hand, left-hand, and shell-ejection sockets;
- simple collider descriptors for stock, receiver, and barrel assembly;
- destruction groups separating stock, receiver, barrel assembly, and pump.

The Trench Model additionally exposes front and rear sling sockets. The Compact
Breacher exposes a reinforced muzzle attachment socket.

## Materials and Performance

Use lightweight procedural materials:

- dark blued or parkerized steel;
- near-black mechanical cavities;
- dark walnut or subdued grip material appropriate to each variation;
- restrained edge and wear modulation generated in code.

No external downloaded texture packs are allowed. Any generated texture must
be deterministic and created locally by the factory.

Targets per model:

- no more than 1,200 rendered triangles where the generated geometry permits
  reliable measurement;
- no more than four runtime materials;
- no more than 30 draw calls;
- repeated ribs, shield holes, and fasteners use instancing or merged geometry;
- no presentation-only light is embedded in the gameplay model.

If the upstream generator cannot satisfy a target without an upstream change,
record the measured result and the exact limitation instead of silently
claiming compliance.

## Project Layout

```text
tools/
  img2threejs/                         # unmodified upstream clone
projects/
  img2threejs-shotgun-variations/
    README.md
    reference/
      shotgun-reference.png
    field/
      assessment.json
      detail-inventory.json
      object-sculpt-spec.json
      reviews/
      renders/
    compact-breacher/
      assessment.json
      detail-inventory.json
      object-sculpt-spec.json
      reviews/
      renders/
    trench/
      assessment.json
      detail-inventory.json
      object-sculpt-spec.json
      reviews/
      renders/
    src/
      createFieldShotgunModel.ts
      createCompactBreacherModel.ts
      createTrenchShotgunModel.ts
      index.ts
    preview/
      index.html
      main.ts
    tests/
      generated-models.test.ts
    package.json
    tsconfig.json
```

## Browser Preview

Provide one local browser preview with:

- a selector for the three variations;
- orbit controls;
- neutral lighting and a non-black background;
- a model-only evaluation mode without bloom or depth of field;
- a small metrics display for triangles, draw calls, materials, and bounds;
- stable camera presets for reference, opposite side, muzzle, top, and
  three-quarter views.

The preview exists to verify generated TypeScript directly. It must not convert
or replace the factories with GLB files.

## Validation

Completion requires:

- the upstream repository exists at the agreed workspace path;
- its required Python scripts run from the local clone;
- all three strict specs validate;
- all locked passes contain real render and review evidence;
- TypeScript type-check and production build succeed;
- each factory constructs a non-empty `THREE.Group`;
- required nodes, sockets, colliders, and destruction groups are present;
- pump and trigger pivots move without detaching child geometry;
- all three models load and render in the browser;
- standardized multi-angle screenshots show three distinct, coherent
  silhouettes;
- measured performance data is recorded without invented scores.

Tests should cover the public factory contract, hierarchy, metadata, distinct
bounds/proportions, deterministic reconstruction, and the performance targets
that can be measured in a headless Three.js environment.

## Error Handling

- If the temporary source image becomes unavailable before it is copied,
  stop and request it again.
- If strict-quality validation rejects a spec, refine the spec rather than
  bypassing the gate.
- If a visual pass fails, record `refine-spec` or `refine-code` with concrete
  evidence and rerun that pass.
- If an intentional variation conflicts with reference-image scoring, use its
  locked variation spec and multi-angle self-consistency as the acceptance
  authority while preserving the baseline reference evidence.
- If the upstream tool has a reproducible defect, keep upstream code unchanged,
  document the defect, and implement only a project-local adapter when possible.
- Bound correction attempts according to the upstream correction-loop rules;
  report an unresolved limitation rather than loop indefinitely.

## Non-Goals

- Blender source files or automation.
- GLB, FBX, OBJ, or skeletal-rig export.
- Photoreal reconstruction.
- Exact reproduction of a real manufacturer or model.
- Firing behavior, ammunition simulation, damage logic, or gameplay code.
- Reworking unrelated dirty factory files or repairing its stale global Python
  configuration as part of this experiment.
