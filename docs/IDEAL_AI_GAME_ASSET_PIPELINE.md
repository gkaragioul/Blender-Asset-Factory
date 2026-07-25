# Ideal Autonomous AI Game-Asset Pipeline

**Status:** Research-backed replacement architecture  
**Date:** 2026-07-22  
**Target:** Commercially sellable, lightweight Three.js/GLB game assets generated with AI and automated tooling on a Linux-native production system.

## Executive conclusion

The current system failed because it used Blender primitives and deterministic Python assembly as the *artist*. That is the wrong abstraction. Procedural scripts are excellent for validation, pivots, naming, collisions, LODs, baking, export, and packaging. They are not a substitute for learned shape priors, reference-driven design, or art direction.

The replacement must be **reference-first, image-first, high-detail-first, candidate-based, and independently judged**:

1. curate legally usable real references and an explicit asset brief;
2. generate and approve a coherent concept/multi-view sheet;
3. generate several high-detail 3D candidates using current image-to-3D foundation models or APIs;
4. render every candidate from standardized views and rank them using independent vision models plus geometric metrics;
5. retopologize the winning high-detail shape to the game budget;
6. transfer/bake PBR detail to the low-poly mesh;
7. optimize and validate the GLB in Three.js;
8. require a user visual-approval gate before expanding the design language to a full pack.

The existing factory remains useful as the production backend, but its primitive geometry generators and self-authored visual scores must no longer be treated as art-generation or quality evidence.

---

## Why the previous approach failed

- It built recognizable *labels* (`Stock`, `Receiver`, `Barrel`) rather than believable forms.
- Primitive dimensions were selected from code, not learned from strong visual references.
- Low polygon count was enforced before the shape was good. This destroyed form before there was form worth preserving.
- Pixel noise and material colors were added before anatomy, proportion, and surface transitions worked.
- The same agent that created the object declared it good, and the scores were constants written into manifests rather than measurements from an independent evaluator.
- Khronos validation and Three.js loading proved file correctness, not artistic quality.
- Only one candidate was generated per attempt, so there was no tournament or meaningful selection pressure.
- There was no concept-art approval gate before expensive 3D work.

## Core architectural correction

> **Generate rich form first; simplify only after the form passes visual review.**

The shape source should come from a high-quality image-to-3D system, photogrammetric/reconstruction workflow, or licensed base/reference—not arbitrary primitive assembly. Blender automation should then make that source game-ready.

---

## Recommended tool stack

### 1. Concept and multi-view generation

Use **ComfyUI** as the orchestration layer for concept art, reference cleanup, segmentation, img2img styling, ControlNet, inpainting, and batch generation.

- Official project/docs: https://github.com/Comfy-Org/ComfyUI and https://docs.comfy.org/
- Local Linux AMD/ROCm is viable for many 2D workflows on this workstation.
- Use a strong image model with img2img/control conditioning—not unconstrained text-only generation.
- Use real reference photos/diagrams from sources whose rights are recorded.
- Generate front, rear, left, right, top and 3/4 views with locked design features.
- Prefer styling multiple real views of the same object over asking an image model to hallucinate independent orthographic views.

### 2. High-quality 3D generation

| System | Strength | Requirements / license | Role |
|---|---|---|---|
| **Pixal3D** | SIGGRAPH 2026 TRELLIS.2-based image-to-3D with pixel-aligned conditioning and near-reconstruction-level fidelity; full PBR and GLB export | Linux/NVIDIA; inherits TRELLIS.2's 24 GB minimum; MIT project and weights; compiled CUDA/NATTEN dependencies | **Primary open high-fidelity candidate** when a strong reference image exists |
| **TRELLIS.2-4B** | High-fidelity image-to-3D, sharp/complex/open topology, full PBR including base color, roughness, metallic and opacity | Linux; NVIDIA GPU with at least 24 GB; code and HF model card report MIT; inspect named dependency licenses | General-purpose open high-detail generator and texture backend |
| **Meshy 6 Multi-Image API** | Accepts 1–4 consistent images; PBR maps; 4K base color; smart topology, polygon targets, remesh, UV, retexture, rigging and animation APIs | Hosted paid API; current paid-plan terms assign outputs to customers, while free outputs are CC BY 4.0; archive exact plan terms | **Primary production service / easiest reliable integration** |
| **Hyper3D Rodin** | High-quality dense image-to-3D; specifically recommended by MeshAnything V2 as its dense-shape source | Hosted service/API; local Blender integration exists but is currently disabled | Independent candidate generator and quality cross-check |
| **PartCrafter** | Generates semantic multi-part objects from one RGB image; VLM can suggest part count | CUDA, at least 8 GB; MIT model card | Part-aware candidate for weapons, machinery and props |
| **TripoSG + PartCrafter** | Strong MIT geometry stack with explicit face limits and semantic part separation | CUDA, at least 8 GB; geometry-only, requiring a separate texture stage | Lightweight structured-geometry candidate for weapons and machinery |
| **Sloyd** | Parametric, artist-authored parts with predictable low-poly topology, quads, manifold output and part splitting | Hosted proprietary service; marketplace redistribution requires the applicable paid plan | Strong specialist for crates, furniture, tools, vehicles and template-compatible hard-surface props |
| **Stable Fast 3D / SPAR3D** | Fast single-image reconstruction with UVs, GLB textures and material parameters | Approximately 6 GB for SF3D; approximately 7–10.5 GB for SPAR3D; Stability Community License below $1M revenue with registration | Best lower-VRAM fallback/prototyping backend |
| **MeshAnything V2** | Converts a good dense mesh into an artist-like mesh capped near 1,600 faces | About 8 GB VRAM; **commercial license unresolved**: source repository is S-Lab non-commercial while HF card says MIT | Experimental retopology candidate only; do not ship commercially until clarified |
| **Hunyuan3D 2.1** | Strong image-to-shape and PBR generation; published 10 GB shape / 21 GB texture / 29 GB combined VRAM figures | Custom license excludes EU, UK and South Korea and prohibits “military purposes” | **Do not use for this worldwide commercial WW2 weapon pack** without legal clearance |

Verified primary sources:

- Pixal3D: https://github.com/TencentARC/Pixal3D
- TRELLIS.2: https://github.com/microsoft/TRELLIS.2
- TRELLIS.2 model: https://huggingface.co/microsoft/TRELLIS.2-4B
- Hunyuan3D 2.1: https://github.com/Tencent-Hunyuan/Hunyuan3D-2.1
- Meshy Multi-Image API: https://docs.meshy.ai/en/api/multi-image-to-3d
- Stable Fast 3D: https://github.com/Stability-AI/stable-fast-3d
- InstantMesh: https://github.com/TencentARC/InstantMesh
- TripoSG: https://github.com/VAST-AI-Research/TripoSG
- PartCrafter: https://github.com/wgsxm/PartCrafter
- MeshAnything V2: https://github.com/buaacyw/MeshAnythingV2
- Sloyd: https://sloyd.gitbook.io/documentation

### 3. Geometry cleanup and retopology

Classify the asset before choosing a cleanup policy: rigid hard-surface, organic static, deforming, architectural, hero or background. Preserve the raw generator output immutably. Use an ensemble rather than trusting one universal retopology path:

1. **Part-aware cleanup in Blender**
   - split stock/receiver/barrels/controls into semantic objects;
   - remove tiny floating components and hidden internal geometry;
   - repair normals and non-manifold regions;
   - preserve hard edges and mechanical interfaces.
2. **Blender Decimate or meshoptimizer simplification** as the default for static rigid props. Runtime assets need good indexed triangles, not compulsory quads.
3. **Blender QuadriFlow** for organic/editable candidates where field-aligned quads offer a real benefit.
4. **Blender Voxel Remesh** only as severe non-manifold recovery; it rounds corners, closes holes and destroys attributes.
5. **MeshAnything V2** only as an experimental learned low-poly proposal until its repository/model-card license conflict is resolved.
6. Compare all low-poly candidates against the approved high-poly silhouette and choose the best one.
7. Generate collision separately: primitives/convex hulls for simple props and **CoACD** for complex concave objects.

Sources:

- Instant Meshes: https://github.com/wjakob/instant-meshes
- Blender Python API: https://docs.blender.org/api/current/
- Trimesh: https://github.com/mikedh/trimesh
- Open3D: https://github.com/isl-org/Open3D
- CoACD: https://github.com/SarahWeiii/CoACD

### 4. UV, baking and materials

- Unwrap automatically with **xatlas** or Blender Smart UV/Lightmap Pack, with seam and texel-density checks.
- Bake high-poly data to the accepted low-poly mesh in headless Blender/Cycles:
  - base color;
  - tangent-space normal;
  - ambient occlusion;
  - roughness;
  - metallic;
  - optional curvature/cavity masks.
- Keep a 1K–4K master bake for provenance and later variants.
- Only after fidelity is proven, derive browser editions:
  - 512/256 px stylized textures;
  - controlled palette reduction;
  - intentional nearest-neighbor sampling for PS1 editions;
  - no arbitrary pixel noise.

Source: https://github.com/jpcy/xatlas

### 5. GLB and Three.js optimization

- Authoritative source: `.blend` plus unoptimized `.glb`.
- Derivative optimization:
  - glTF Transform for pruning, deduplication, texture resizing and KTX2/BasisU;
  - meshoptimizer/gltfpack for vertex/index optimization, simplification and meshopt compression;
  - preserve an uncompressed fallback when browser compatibility requires it.
- Do not run broad glTF Transform `optimize` and gltfpack blindly in series. Assign ownership of simplification, compression and texture conversion explicitly.
- Generate LOD1/LOD2 independently from accepted LOD0, not recursively from the preceding degraded LOD.
- Three.js runtime should explicitly configure `MeshoptDecoder` and `KTX2Loader` for compressed derivatives.
- Validate with Khronos glTF Validator and a real browser render.

Sources:

- glTF Transform: https://github.com/donmccurdy/glTF-Transform
- meshoptimizer/gltfpack: https://github.com/zeux/meshoptimizer
- Khronos glTF Validator: https://github.com/KhronosGroup/glTF-Validator
- KTX tools: https://github.com/KhronosGroup/KTX-Software

---

## The ideal stage-gated workflow

### Gate 0 — Asset brief and legal provenance

Each asset starts with a machine-readable contract containing:

- intended gameplay role and camera distance;
- target visual style;
- real-world dimensions/proportions;
- mandatory recognizable parts;
- forbidden markings/logos/symbols;
- triangle, material, texture and file-size targets;
- required movable parts and pivots;
- reference URLs, creators, rights, retrieval dates and local hashes.

No generation starts until the reference set is sufficient.

### Gate 1 — 2D concept tournament

1. Build a reference board from multiple real views and detail crops.
2. Generate 12–24 controlled concept candidates with consistent proportions and a neutral background.
3. Use independent VLM critics to reject impossible anatomy and identify required parts.
4. Rank candidates blind; do not show generation metadata to the judge.
5. Produce a clean multi-view sheet from the winner.
6. **User approves the concept before any 3D pack expansion.**

For weapons, the untextured side silhouette must already be unmistakable here.

### Gate 2 — Multi-view consistency

- Segment each view and align scale, orientation and principal axes.
- Verify stock/receiver/barrel/fore-end lengths and connection points across views.
- Compare masks and detected landmarks.
- Reject inconsistent view sets rather than asking the 3D model to reconcile impossible images.

### Gate 3 — 3D candidate ensemble

Generate several candidates from at least two independent backends, for example:

- TRELLIS.2 on a rented 24–80 GB NVIDIA worker;
- Meshy 6 multi-image API;
- Rodin or PartCrafter as an alternate.

Store every model version, seed, prompt, input hash, API task ID, license snapshot and cost in the candidate manifest.

### Gate 4 — Independent visual tournament

For every candidate, render standardized:

- left/right orthographic;
- front/rear;
- top/bottom;
- four 3/4 views;
- clay, silhouette, normal, depth and PBR beauty passes.

Score with systems that did not create the asset:

- DINOv2/CLIP similarity against the approved concept;
- silhouette intersection-over-union for aligned views;
- landmark/part presence and ordering;
- LPIPS/perceptual texture consistency;
- VLM rubric for anatomy, proportion, coherence and appeal;
- mesh metrics for disconnected components, non-manifold geometry, thin surfaces and self-intersections.

Use blind pairwise A/B ranking. A candidate may not pass because its manifest contains a declared score. Scores must be computed from artifacts.

#### Anti-reward-hacking controls

- Producer, critic and adjudicator are separate processes; prefer different model/vendor families.
- Freeze and hash the brief, reference set, camera rig, metrics, thresholds and retry budget before generation.
- Keep a score vector—semantic parts, silhouette, cross-view consistency, geometry, materials, aesthetics, runtime and provenance—rather than one scalar reward.
- Give critics anonymized A/B contact sheets, not model names, prompts, seeds or previous scores.
- Require evidence-bearing JSON critiques that identify the failing view/region and a concrete repair.
- Keep hidden holdout references and rubric clauses for sampled auditing.
- Inject known-bad canary assets; disable a judge that accepts missing parts, floating geometry or broken UVs.
- Bound retries and stop on plateaus rather than allowing endless reward hacking.

### Gate 5 — High-poly approval

The winning dense/high-poly candidate must pass an untextured clay review. If the form only looks good because the texture paints fake geometry, reject it.

This is where the user should see the asset for the second time.

### Gate 6 — Low-poly conversion

- Retopologize semantic parts separately where needed.
- Produce multiple low-poly proposals using MeshAnything V2, field-aligned remesh and controlled decimation.
- Preserve silhouette first; topology aesthetics are secondary for static browser assets.
- Project the accepted low-poly mesh back to the high-poly source.
- Generate LOD0/LOD1/LOD2 and collision meshes.

### Gate 7 — Bake and stylize

Bake the approved high-poly appearance to the game mesh. Generate the PS1/pixel edition from the clean bake, not from procedural noise. Inspect seams and material channels at full resolution and thumbnail scale.

### Gate 8 — Runtime proof

- Khronos validation: zero errors.
- Three.js load and screenshot from a loopback server.
- Compare optimized vs authoritative renders for visible drift.
- Record draw calls, triangles, material count, texture memory and GLB bytes.
- Test Chrome/Chromium and at least one alternate engine/import path.

### Gate 9 — Human release approval

A fully autonomous pipeline can narrow hundreds of candidates to a few strong options, but commercial art still needs a final visual owner. The user should approve:

1. the concept sheet;
2. the benchmark 3D asset;
3. the final pack contact sheet.

No other manual modeling or UV work is required.

---

## Recommended architecture for this repository

Keep:

- Linux-native Blender execution;
- factory doctor and path safety;
- Khronos validation;
- gltfpack/meshoptimizer;
- Three.js preview;
- manifests, reports and release packaging.

Replace or demote:

- primitive-based weapon generation;
- hardcoded “visual scores”;
- single-candidate generation;
- texture-first PS1 noise;
- automatic promotion based only on GLB validity.

Add:

```text
factory/
  concepts/              # ComfyUI/API concept generation and multiview sheets
  references/            # provenance, rights and hashes
  providers/
    trellis2.py
    meshy.py
    rodin.py
    partcrafter.py
  candidate_tournament.py
  multiview_render.py
  visual_metrics.py
  vlm_art_director.py
  retopo.py
  bake.py
  lod.py
  release_gates.py
runs/<run-id>/
  brief.json
  references/
  concepts/
  candidates/high/
  candidates/low/
  renders/
  metrics.json
  critique.json
  provenance.json
  decision.json
```

Every stage writes immutable artifacts. Failed candidates remain in the run directory but can never appear under `products/.../release`.

---

## Best practical deployment for this workstation

Live hardware inspection found an **AMD Navi 31 Radeon RX 7900-class GPU** and no NVIDIA CUDA runtime. Most leading open 3D generators are still explicitly CUDA/NVIDIA-oriented.

Therefore:

- **Local AMD workstation:** ComfyUI concept work via ROCm, Blender cleanup/baking/export, xatlas, glTF Transform, meshoptimizer, Three.js validation.
- **Cloud NVIDIA worker:** Pixal3D/TRELLIS.2 and PartCrafter. MeshAnything V2 remains research-only until its license conflict is resolved.
- **Hosted API option:** Meshy 6 and/or Rodin for strongest low-friction candidate generation.
- Do not force CUDA research projects onto this AMD host and then lower quality to fit local hardware.

## Recommended first benchmark

Do not build fifteen assets. Build one benchmark asset through the entire new pipeline:

1. a legally documented shotgun reference board;
2. a coherent approved multi-view concept sheet;
3. candidates from Pixal3D/TRELLIS.2, Meshy and Rodin/PartCrafter;
4. blind visual tournament;
5. retopology and PBR bake;
6. optimized Three.js GLB;
7. user approval.

Only after that benchmark is accepted should its style and technical profile become the pack standard.

## Pipeline choices compared

| Pipeline | Visual ceiling | Autonomy | This Linux/AMD host | Operating cost | Licensing risk | Recommendation |
|---|---:|---:|---:|---:|---:|---|
| Primitive Blender Python | Low for organic or designed forms | High | Excellent | Low | Low | Keep only for fixtures, collision, pivots and technical assembly |
| Fully local open-source 3D | Potentially high | Medium | Poor: leading models are CUDA-first | Low after NVIDIA hardware is available | Medium | Not practical on the current AMD machine |
| Cloud Pixal3D/TRELLIS.2 + local Blender | Very high | High after deployment | Excellent split architecture | Medium GPU rental | Low/medium; archive dependency and model licenses | Preferred open-source route |
| Meshy 6 API + local Blender | High and easiest to automate | High | Excellent | Per-task/API subscription | Terms must be archived and checked | Preferred production route |
| Meshy + Pixal3D/TRELLIS.2 + Rodin ensemble | Highest robustness because candidates compete | High | Excellent | Highest | Provider-by-provider review | **Ideal quality-first route for the benchmark** |
| Hunyuan3D 2.1 | High | High | Cloud NVIDIA required | Medium | High for this project | Exclude from WW2 pack unless legal constraints are resolved |

## Implementation roadmap

### Phase A — Freeze the failed path

- Mark all primitive-generated weapons as rejected prototypes.
- Remove hardcoded visual scores from release decisions.
- Make visual acceptance a required gate, not advisory metadata.

### Phase B — Reference and concept subsystem

- Implement asset briefs and reference-provenance manifests.
- Add ComfyUI/API adapters for controlled img2img, background removal, segmentation and concept batches.
- Add concept contact sheets and a user approval state.

**Exit condition:** one coherent shotgun concept/multi-view sheet is approved before any mesh is generated.

### Phase C — 3D provider adapters

- Implement Meshy Multi-Image task submission/polling/download.
- Deploy Pixal3D and TRELLIS.2 on an NVIDIA cloud worker behind a reproducible job API.
- Add Rodin as the independent third backend if its commercial terms and API access are acceptable.
- Capture model versions, inputs, task IDs, costs and license snapshots.

**Exit condition:** the same approved concept produces multiple durable, reproducible candidate meshes.

### Phase D — Candidate tournament and art critic

- Build standardized 12-view clay/PBR/silhouette/normal/depth rendering.
- Add DINOv2/CLIP, silhouette and geometry measurements.
- Add an independent VLM rubric and blind pairwise comparisons.
- Refuse promotion when views are missing or critic evidence is absent.

**Exit condition:** a winner is selected from real rendered evidence, never a manifest constant.

### Phase E — Game-production conversion

- Add semantic-part cleanup, class-specific remesh/decimation candidates, UVs and high-to-low baking; keep MeshAnything V2 disabled for commercial output until licensing is clarified.
- Generate LODs, collisions, pivots and intentional PS1 texture derivatives.
- Run glTF Transform, meshoptimizer, Khronos validation and Three.js browser proof.

**Exit condition:** optimized runtime output is visually equivalent to the approved high-poly source within the declared tolerances.

### Phase F — Benchmark approval and scale-out

- Present the concept, high-poly winner and final runtime asset to the user.
- Record approval/rejection evidence.
- Only after acceptance, freeze the style profile and produce the remaining pack assets through the same gates.

**Exit condition:** one benchmark asset is genuinely accepted on visual quality—not merely technically valid.

## Bottom line

The ideal system is not “better Blender Python primitives.” It is a **generative art pipeline feeding a deterministic game-production pipeline**:

```text
References + brief
  → controlled concept candidates
  → approved coherent multi-view sheet
  → high-quality 3D model ensemble
  → independent visual tournament
  → high-poly approval
  → learned/deterministic retopology ensemble
  → PBR bake and intentional stylization
  → LOD/collision/pivots
  → GLB optimization and Three.js proof
  → user release approval
```

That architecture gives AI the role it is strong at—visual synthesis and candidate exploration—and gives deterministic tooling the role it is strong at—cleanup, optimization, validation and repeatability.

## Deep research appendices

- [Current AI 3D model and service shortlist](research/AI_3D_MODEL_SHORTLIST_2026-07-22.md)
- [Production cleanup, retopology, UV, baking, collision and runtime toolchain](research/PRODUCTION_CLEANUP_TOOLCHAIN_2026-07-22.md)
- [Autonomous art direction, independent QA and anti-self-scoring architecture](research/AUTONOMOUS_ART_DIRECTION_QA_2026-07-22.md)
