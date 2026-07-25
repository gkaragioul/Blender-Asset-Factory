## Recommended production stack

For a **Linux-native, mostly autonomous, commercially usable pipeline**, use:

1. **Blender 4.x headless** as the authoritative scene, repair, baking, collision, and export environment.
2. **Trimesh** for inexpensive preflight inspection and reporting.
3. **Blender Voxel Remesh / QuadriFlow / Decimate** selected by asset class — not one universal remesher.
4. **xatlas** for deterministic automatic UVs when Blender Smart UV is insufficient.
5. **Blender Cycles** for high-to-low normal/AO/material baking.
6. **Material Maker** or scripted Blender materials for open-source procedural PBR sources.
7. **CoACD** for complex convex collision decomposition.
8. **meshoptimizer/gltfpack** for final runtime optimization and optional LOD generation.
9. **glTF Transform** for inspection, targeted transformations, metadata-preserving custom workflows, and texture processing.
10. **Khronos glTF Validator + a real headless Three.js renderer** for release validation.
11. **UniRig/SkinTokens only as an optional rigging candidate generator**, followed by mandatory deformation QA.

Do **not** require quad topology for static game props. Good indexed triangles are the runtime product; quads matter mainly for deformation, subdivision, or future editing.

---

## Proposed automatic pipeline

### 1. Preserve and classify the generated input

Keep the generator output immutable:

```text
source/
  raw.glb
working/
  canonical.blend
  high.blend
  low.blend
release/
  asset_authoring.glb
  asset_runtime.glb
  asset_lod1.glb
  asset_lod2.glb
  validation.json
  manifest.json
```

Classify each asset before processing:

- rigid hard-surface prop;
- organic static prop;
- deforming character;
- environment/architectural mesh;
- hero asset versus background asset.

A single automatic retopology policy will damage at least some of these classes.

### 2. Preflight and canonicalization

Use Trimesh for diagnostics, then Blender for authoritative edits:

- finite vertices and normals;
- zero-area and duplicate triangles;
- disconnected components;
- boundary and non-manifold edges;
- winding consistency;
- self-intersection indicators;
- material and texture inventory;
- dimensions, origin, scale, and orientation;
- triangle/material/draw-call budgets.

In Blender:

- apply scale before resolution-dependent operations;
- duplicate the high-resolution object before destructive processing;
- remove loose geometry and exact/epsilon duplicates;
- recalculate normals;
- run mesh validation;
- retain meaningful disconnected pieces instead of blindly joining everything.

Automation command:

```bash
blender --background --python cleanup_pipeline.py -- \
  --input source/raw.glb \
  --job job.json \
  --output working/canonical.blend
```

Prefer Blender data APIs and `bmesh` over context-sensitive `bpy.ops`; where operators are necessary, establish explicit active object, selection, mode, and context overrides.

### 3. Repair decision tree

#### Minor defects

Use Blender/BMesh or Trimesh:

- merge-by-distance;
- delete loose vertices/edges;
- recalculate winding/normals;
- remove degenerate faces;
- fill only small, clearly bounded holes.

Trimesh explicitly warns that fan-filled non-convex holes can produce bad answers, so it should not be treated as a general surface reconstruction system.

#### Severe non-manifold or self-intersecting input

Use **Blender Voxel Remesh** to reconstruct a manifold volume. It is the most automation-friendly recovery option, but:

- rounds corners and thin features;
- closes intentional openings;
- can merge nearby disconnected parts;
- loses UVs, materials, vertex groups, shape keys, and other mesh layers;
- resolution is scale-dependent.

Blender documents that `voxel_remesh()` creates a new manifold mesh and loses all data layers.

#### Intermediate repair fallback

Use **PyMeshLab** or Open3D only for narrowly specified filters.

- Open3D’s non-manifold repair works by deleting adjacent triangles until each edge has at most two, which can remove visible geometry.
- PyMeshLab is powerful for batch filtering, but filter names and defaults should be pinned to a tested release.
- MeshLab is GPL; invoking it as an external tool is operationally useful, but embedding/distributing it needs license review.

### 4. Retopology

#### Static assets — recommended default

Avoid quad remeshing unless there is a demonstrated need:

1. repair;
2. preserve sharp boundaries and UV seams;
3. use Blender Decimate or meshoptimizer simplification;
4. triangulate deterministically before the final normal bake/export.

This retains shape more predictably than rebuilding the surface as generic quads.

#### Organic or editable assets

Use Blender’s integrated QuadriFlow:

```python
bpy.ops.object.quadriflow_remesh(
    mode='FACES',
    target_faces=target,
    use_preserve_sharp=True,
    use_preserve_boundary=True,
    seed=0,
)
```

Limitations:

- slow on large or complicated meshes;
- output is not animation-aware semantic topology;
- edge flow may be unsuitable around shoulders, mouths, eyes, hands, and joints;
- all data layers are lost;
- topology can vary with target and seed.

#### Tool comparison

| Tool | Recommendation | Main limitations |
|---|---|---|
| [Blender QuadriFlow API](https://docs.blender.org/api/4.0/bpy.ops.object.html#bpy.ops.object.quadriflow_remesh) | Primary automatic quad candidate because it is integrated and scriptable | Slow, loses layers, not semantic/deformation-aware |
| [QuadriFlow upstream](https://github.com/hjwdzh/QuadriFlow) | Useful standalone CLI: `quadriflow -i … -o … -f …` | Upstream is old; sharp preservation is optional; SAT watertight mode adds dependencies |
| [Instant Meshes](https://github.com/wjakob/instant-meshes) | Good interactive field-guided retopology reference/tool | GUI-oriented workflow, no well-supported documented batch API, old upstream, loses attributes |
| Blender Voxel Remesh | Severe-repair/manifold reconstruction | Changes silhouette, closes openings, destroys attributes |
| Blender Decimate | Static LODs and rigid props | Produces triangles; can damage silhouette, UVs, and shading at aggressive ratios |
| meshoptimizer simplify | Runtime LODs | Triangle simplification, not authoring topology or semantic retopology |

For animated hero characters, automatic quad output should be considered a **candidate**, not an accepted production result.

### 5. UV generation and packing

Recommended order:

1. Preserve supplied UVs if they pass overlap, bounds, and texel-density tests.
2. Otherwise use authored seams plus Blender `unwrap`.
3. For generic autonomous props, use Blender `smart_project` and `pack_islands`.
4. Use xatlas when a deterministic standalone atlas is preferred.

Important tests:

- no missing UVs or NaNs;
- no unintended overlaps;
- adequate gutter after mip generation;
- consistent texel density;
- mirrored/stacked islands allowed only by policy;
- material-specific charts kept together where required.

| Tool | Assessment |
|---|---|
| [Blender UV API](https://docs.blender.org/api/4.0/bpy.ops.uv.html) | Built-in, scriptable, good default; Smart UV is generic and often creates too many arbitrary seams |
| [xatlas](https://github.com/jpcy/xatlas) | MIT, deterministic, generates unique UVs suitable for baking/lightmaps |
| [xatlas-python](https://github.com/mworchel/xatlas-python) | Convenient Python binding; unofficial and must be version-pinned |
| [UVPackmaster](https://uvpackmaster.com/) / [docs](https://uvpackmaster.com/doc3/) | Superior utilization, grouping, locking, UDIM, and production controls | Paid/proprietary, Blender-version and license deployment concerns, extra headless-worker setup |
| Blender native packer | Best no-cost UVPackmaster alternative inside Blender | Usually lower utilization and fewer production grouping controls |
| xatlas packing | Best open standalone alternative | Can duplicate vertices and does not understand artistic seam intent |

xatlas returns a new vertex mapping because parameterization may duplicate vertices at seams; the pipeline must remap attributes correctly.

### 6. Baking and PBR creation

Use **Cycles selected-to-active baking** from preserved high-resolution geometry to the accepted low mesh:

- tangent-space normal;
- ambient occlusion;
- base color;
- roughness;
- metallic;
- emissive;
- optional curvature/thickness masks.

Blender baking documentation:  
https://docs.blender.org/manual/en/4.0/render/cycles/baking.html  
API: https://docs.blender.org/api/4.0/bpy.ops.object.html#bpy.ops.object.bake

Requirements:

- explicit low/high object pairing;
- cage mesh or validated ray distance;
- triangulate low mesh before the final normal bake;
- bake at higher resolution, then downsample;
- dilate beyond the intended mip chain;
- use sRGB for base color/emissive and linear data for normal/roughness/metal/AO;
- pack glTF ORM as **AO=R, roughness=G, metallic=B**.

#### PBR source options

- **Scripted Blender node materials:** best default for deterministic automation.
- **[Material Maker](https://github.com/RodZill4/material-maker):** MIT, Linux-native, procedural material authoring, with batch export:
  ```bash
  material_maker --export-material --target Blender \
    -o output materials/*.ptex
  ```
  Docs: https://rodzill4.github.io/material-maker/doc/command_line.html  
  Limitation: exports PNG/EXR for Blender; it does not automatically build the Blender material or create asset-specific semantic wear.
- **[ArmorPaint](https://github.com/armory3d/armorpaint):** useful interactive painting alternative, but not the preferred headless factory component; automation and current licensing/build distribution require separate review.
- **Adobe Substance Painter/Baker/Automation Toolkit:** strongest mature commercial baking and painting option if budget and deployment licensing are acceptable. It is proprietary and less suitable for a fully open, unattended farm.

Neither procedural textures nor baking can infer where a real object should be scratched, painted, oily, dirty, or manufactured. Those are artistic and semantic decisions.

### 7. LOD generation

Generate each LOD independently from the accepted LOD0, not recursively:

- LOD0: accepted retopology;
- LOD1: approximately 40–60% of LOD0;
- LOD2: approximately 10–25%;
- optional billboard/impostor for large scenes.

Use silhouette/error thresholds rather than triangle ratio alone.

Options:

- Blender Decimate when material boundaries, seams, modifiers, or local vertex groups must be controlled.
- `gltfpack -si R` for simple automatic runtime derivatives.
- glTF Transform `simplify()` for a programmable meshoptimizer-based workflow.

Do not assume that a glTF LOD extension will work in Three.js. The robust choices are:

- separate GLBs; or
- named `LOD0`, `LOD1`, `LOD2` objects assembled into [`THREE.LOD`](https://threejs.org/docs/pages/LOD.html) at runtime.

### 8. Collision

glTF has no universal core collision semantic.

Recommended convention:

- primitives for common shapes;
- one Blender convex hull for simple rigid props;
- **[CoACD](https://github.com/SarahWeiii/CoACD)** for complex concave static objects;
- capsules/boxes authored from bones for characters.

CoACD supports Linux and Python:

```python
import coacd
parts = coacd.run_coacd(mesh, threshold=0.01, real_metric=True)
```

Store collision as named nodes such as `COLLIDER_box_00` or in a separate collision GLB. Preserve names/extras during optimization.

Do not begin new work with V-HACD: its repository explicitly marks it deprecated and directs users to CoACD:  
https://github.com/kmammou/v-hacd

### 9. glTF/GLB optimization

#### Primary optimizer: gltfpack

Repository/docs:

- https://github.com/zeux/meshoptimizer
- https://meshoptimizer.org/gltf/

Example derivative:

```bash
gltfpack \
  -i asset_authoring.glb \
  -o asset_runtime.glb \
  -cc -tc -kn -km -ke
```

- `-cc`: meshopt compression;
- `-tc`: KTX2/Basis textures;
- `-kn`: preserve named nodes;
- `-km`: preserve named materials;
- `-ke`: preserve extras.

Limitations:

- defaults may merge unanimated meshes and collapse scene hierarchy;
- custom/unknown extensions can be discarded;
- quantization can add dequantization transforms;
- compressed assets require Three.js Meshopt and KTX2 decoder setup.

Never overwrite the authoritative GLB.

#### glTF Transform

- Docs: https://gltf-transform.dev/
- Repository: https://github.com/donmccurdy/glTF-Transform
- Simplification: https://gltf-transform.dev/modules/functions/functions/simplify

Use it for:

- `inspect`;
- dedup/prune/weld;
- explicit quantization;
- custom Node.js transforms;
- texture compression;
- extension-aware metadata work;
- fine-grained pipeline reports.

Do not run gltfpack and a broad glTF Transform `optimize` blindly in series. Decide which tool owns simplification, compression, and texture conversion, then use the other only for targeted operations.

### 10. Release validation

#### Static validator

Run the [Khronos glTF Validator](https://github.com/KhronosGroup/glTF-Validator) on both authoring and optimized GLBs:

- zero errors;
- warnings explicitly allow-listed;
- no missing resources;
- extension declarations correct;
- accessors, indices, animation times, and bounds valid.

#### Real Three.js runtime test

Use [`GLTFLoader`](https://threejs.org/docs/pages/GLTFLoader.html) through an HTTP server in Playwright/Chromium.

For optimized files:

```js
loader.setMeshoptDecoder(MeshoptDecoder);
loader.setKTX2Loader(
  new KTX2Loader()
    .setTranscoderPath('/basis/')
    .detectSupport(renderer)
);
```

Automated runtime gates should:

- fail on loader or browser-console errors;
- verify finite transforms, positions, normals, tangents, and UVs;
- assert expected named nodes, materials, clips, and collision proxies;
- compile shaders and render multiple frames;
- exercise every animation and LOD;
- record `renderer.info` draw calls, triangles, textures, and geometry;
- verify texture decode and color-space assignment;
- detect black/magenta/transparent output;
- capture deterministic turntable screenshots;
- compare optimized bounds and screenshots against the authoritative export;
- test disposal/reload to catch leaks.

Three.js supports `KHR_meshopt_compression` and `KHR_texture_basisu`, but the corresponding decoders still need to be configured.

---

## Automatic rigging assessment

| Tool | Suitability |
|---|---|
| [Blender Rigify](https://docs.blender.org/manual/en/4.0/addons/rigging/rigify/index.html) | Production rig generator after a human or system correctly positions a metarig; not automatic skeleton inference or topology repair |
| [UniRig](https://github.com/VAST-AI-Research/UniRig) | Promising MIT Linux research pipeline for skeleton and skinning candidates |
| [SkinTokens](https://github.com/VAST-AI-Research/SkinTokens) | Newer MIT successor integrating skeleton and skinning prediction; still requires production evaluation |
| [RigAnything](https://github.com/Isabella98Liu/RigAnything) | Technically convenient GLB-in/rigged-GLB-out workflow, but Adobe Research License restricts it to noncommercial research — reject for commercial production |
| [RigNet](https://github.com/zhan-xu/RigNet) | Old Python/CUDA stack, no clear repository license, research-grade — reject as a production dependency |
| Mixamo | Useful manual SaaS fallback, but not Linux-native, reproducibly headless, or supported by a public batch API |

For UniRig/SkinTokens, separately review checkpoint and training-dataset terms. An MIT code or model-card license does not prove that every generated rig or training source is risk-free.

Rig acceptance must include:

- normalized bone hierarchy and naming;
- maximum influences per vertex;
- weights sum to one;
- no unweighted vertices;
- joint limits and rest-pose sanity;
- automated extreme-pose renders;
- shoulder, hip, elbow, knee, finger, face, and tail deformation checks;
- self-intersection and volume-loss metrics.

---

## Technical cleanup versus sellable quality

The pipeline can automatically prove:

- structural validity;
- manifold status;
- finite attributes;
- triangle/material/texture budgets;
- valid UV coverage;
- successful bake and compression;
- glTF conformance;
- Three.js loading and rendering.

It cannot reliably prove:

- recognizable or appealing silhouette;
- correct proportions;
- good animation edge flow;
- purposeful UV seams;
- believable material identity and wear;
- preservation of important thin features;
- useful collision semantics;
- marketplace-level presentation quality.

A technically perfect GLB can still be commercially poor. The release process therefore needs a separate multi-view **art-direction gate** — human review or a bounded visual-scoring/regeneration loop — and should label technical-only passes as `prototype_validated_not_sellable`.

## Outcome

- Researched the requested Blender, remeshing, UV, repair, material, optimization, collision, runtime, and rigging tools against current official docs/repos.
- Recommended a Blender-centered Linux pipeline with Trimesh, xatlas, Cycles, CoACD, gltfpack, glTF Transform, Khronos Validator, and Three.js runtime QA.
- No files were created or modified.
- UVPackmaster documentation blocked automated access with HTTP 403, and Adobe documentation repeatedly timed out; tool positioning was therefore based on their accessible official product pages plus upstream project documentation.