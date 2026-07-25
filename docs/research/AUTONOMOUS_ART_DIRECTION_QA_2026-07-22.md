# Autonomous Art Direction + QA for AI Game Assets

**Research date:** 2026-07-22  
**Target:** Linux-native, lightweight Three.js `.glb`, minimal/no human modeling  
**Bottom line:** Automation can reject technical and obvious visual failures, rank candidate pools, and focus regeneration. It cannot reliably certify that an asset has excellent taste, originality, or marketplace appeal. A human should still approve the benchmark/hero asset and the final release contact sheet; thereafter automation can safely propagate an approved visual grammar.

## Recommended architecture: independent producer, judges, and release gate

Do **not** let the generator grade itself or expose one scalar reward that it can game.

```text
immutable brief + rights-cleared reference board
       |
       v
PRODUCER (image model -> multiview/3D model -> Blender repair)
       |
       +--> deterministic technical QA (no AI judgment)
       +--> frozen metric panel (OpenCLIP + DINO + masks + depth/normals)
       +--> blind critics from different model/vendor families
                       |
                       v
              adjudicator / Pareto ranker
                       |
             reject + bounded repair brief
                       |
              hidden holdout judge (sampled)
                       |
         human benchmark/final contact-sheet approval
                       |
              transactional GLB release
```

### Anti-self-scoring controls

1. **Role and model separation:** producer, critic, and adjudicator are separate processes; no candidate is reviewed by the model instance that generated it. Prefer a different vendor/model family for the main visual critic.
2. **Frozen inputs:** version the brief, required-parts list, forbidden motifs, reference set, camera rig, score code, and thresholds before a run. Hash them.
3. **Blind pairwise review:** critics see randomized A/B candidates, reference board, and rubric—not seed, prompt, generator name, previous score, or preferred answer. Pairwise ranking is more stable than an invented absolute 0–10.
4. **Score vector, not one reward:** retain separate semantic, silhouette, cross-view, geometry, material, aesthetic, novelty, runtime, and provenance outcomes. Select from the Pareto frontier; hard failures cannot be averaged away.
5. **Hard gates are deterministic:** topology, file size, GLB validation, texture budgets, missing required parts, broken alpha, and license/provenance failures are not negotiable VLM opinions.
6. **Soft scores only shortlist:** CLIP, DINO, ImageReward/PickScore/aesthetic predictors are distribution-biased proxies. Never allow them alone to publish an asset.
7. **Hidden holdout judge:** keep some reference images, negative examples, and rubric clauses unavailable to the producer/repair agent. Re-evaluate a sample with a second independent VLM and periodically with humans. Large train-vs-holdout score divergence indicates reward hacking.
8. **Evidence-bearing critiques:** every critic must return JSON with pass/fail per rubric item, confidence, visible evidence (view + bounding box/region), and one concrete repair. Unsupported adjectives are discarded.
9. **Bounded retries and plateau detection:** e.g. 3 image retries, 2 reconstruction retries, 2 Blender repair retries. Stop when no Pareto improvement occurs twice; escalate rather than generating a procedural shotgun batch.
10. **Canary failures:** inject known bad candidates (missing trigger, disconnected limb, mirrored text, broken UV) into critic calibration. If a judge passes them, disable that judge.

## Stage-gated production pipeline

### Gate 0 — Asset contract and provenance (hard)

Create an immutable `asset_job.json` containing:

- intended use and audience; recognizable noun/asset class;
- required semantic parts and forbidden details;
- canonical scale, units, up/forward axes, pivot, origin;
- target triangle/material/draw-call/texture/file-size budgets;
- style tokens, palette, edge language, roughness/metalness ranges;
- camera rig (hero, strict side/front/back/top, 8–24 view turntable, close-ups);
- acceptance thresholds and retry budget;
- source manifest: URL, creator, license + version, acquisition timestamp, local SHA-256;
- generator/service/model identifiers, model-card/license URLs, commit or API version, prompts, seeds, workflow JSON, container digest.

Use only owned/licensed references. Prefer CC0 sources such as Poly Haven; do not treat Pinterest/search thumbnails as reusable source assets. Sign/hash the manifest. C2PA can carry provenance for supported image intermediates; because GLB support is not generally the core C2PA path, bind the final GLB by SHA-256 in a signed JSON/C2PA sidecar.

**Pass:** every source and every model/checkpoint has a recorded commercial-use basis.  
**Fail:** unknown source, ambiguous checkpoint license, or service terms not archived.

### Gate 1 — Rights-cleared reference board (human once, then frozen)

Build a machine-readable board rather than a loose mood board:

- `identity/shape`: 6–12 references defining proportions and required parts;
- `style/material`: 6–12 references defining palette, edge wear, surface response;
- `negative`: 6–12 examples of failure modes (toy-like, noisy, melted, over-detailed, wrong era);
- each crop tagged with what may be borrowed: silhouette, palette, material, construction logic—not wholesale design identity.

Generate a contact sheet and embeddings. Cluster with DINO/OpenCLIP to remove near-duplicates and keep visual diversity. A human should approve this board because copyright, taste, and brand fit are not reliable autonomous judgments.

### Gate 2 — Image-first concept tournament

Generate 16–32 low-cost thumbnails in a controlled studio setup before any 3D work. Use the same camera class, neutral background, and prompt contract. Good practical stacks:

- hosted: Adobe Firefly API (provenance-oriented) or Black Forest Labs FLUX API;
- local: ComfyUI + a commercially compatible checkpoint, with IP-Adapter/reference conditioning and ControlNet for silhouette/depth/edge control.

First eliminate malformed/missing-part candidates using masks and a VLM rubric. Then blind-pairwise rank survivors using:

- prompt/required-parts alignment: OpenCLIP text-image score;
- visual/style similarity to the frozen board: DINO cosine/patch similarity + OpenCLIP image-image;
- aesthetic preference: LAION aesthetic predictor and optionally a preference reward model, only as soft rankers;
- diversity/novelty: reject near-copies against source references and already-selected pack assets;
- independent VLM critics: one art-direction critic and one construction/anatomy critic from different providers.

Select 3–5 Pareto-front candidates, not the top result of a weighted sum. Require a clean silhouette at 64–128 px. For a new pack, get human approval of **one** benchmark concept before continuing.

### Gate 3 — Multi-view consistency before reconstruction

Generate a canonical six-view or eight-view sheet from the chosen hero image with locked identity/reference conditioning. Keep exact azimuth/elevation metadata. Do not independently prompt every view.

Check the *source views themselves* before 3D:

- SAM 2 masks: stable projected area, connected-component count, appendage count;
- DINO patch/global embeddings: identity/style stability across views;
- LightGlue correspondences (use DISK/ALIKED, not restrictively licensed SuperPoint if commercial): adjacent-view feature track survival;
- VLM required-parts inventory per view;
- inferred depth order and normals: Depth Anything V2 Small and/or Marigold as soft geometric priors;
- explicit contradiction checks: parts appearing/disappearing, handedness flip, topology change, logo/text mutation, material swap.

Reject contradictory view sets. A 3D model cannot faithfully reconcile impossible source views.

### Gate 4 — Image-to-3D candidate tournament

Run 2–4 reconstruction backends/seeds where compute permits. Recommended order:

1. **TRELLIS image-to-3D** — strong open baseline; models and most code MIT, but inspect named submodule licenses.
2. **TripoSR** — simple MIT baseline; repo states code and pretrained models are MIT; fast and Linux-friendly.
3. **Wonder3D / InstantMesh** — useful multiview-to-mesh alternatives; audit all weights/dependencies.
4. **Stable Fast 3D** — outputs GLB and is Linux-oriented, but gated/custom Stability license; review current terms before commercial use.
5. **Hosted Meshy or Tripo API** — practical when quality/throughput beats local models; archive the exact plan terms and privacy settings.

Avoid making Hunyuan3D-2.1 the default commercial backend: its community license explicitly excludes use in the EU, UK, and South Korea and adds a >1M-MAU commercial-license trigger. Zero123++ weights are CC-BY-NC-4.0 and its README says they cannot be used in a commercial product pipeline; Era3D is AGPL-3.0 unless separately licensed.

Keep every raw candidate; do not destructively overwrite it with decimation/repair.

### Gate 5 — Geometry/silhouette/depth/normal QA (hard + soft)

In Blender, render fixed camera views with beauty, alpha/mask, Z-depth, world/view normal, AO, base color, roughness, and metallic passes.

**Hard mesh checks**

- manifold/watertight where required; no degenerate/zero-area faces;
- no unintended disconnected components, duplicate vertices, inverted normals, or severe self-intersections;
- required named/visible parts present; valid UVs; no NaN/Inf;
- correct scale, pivot, orientation, bounding box, triangle/material/texture budgets.

**2D/3D comparison checks**

- silhouette IoU and boundary Chamfer distance for known source cameras;
- required-part mask visibility and connectivity;
- depth: scale/shift-invariant rank correlation to independent monocular depth, not raw absolute depth;
- normals: foreground median/angular-error map against independent normal estimates, treated softly because pseudo normals are uncertain;
- DINO/OpenCLIP similarity between source views and matched renders;
- cross-view texture/material consistency and seam visibility;
- strict side/front/back silhouette readability at thumbnail size.

Use a hard veto for missing anatomy, floating geometry, broken topology, and non-readable silhouette. Depth/normal predictors must never override visibly correct geometry.

### Gate 6 — Independent multi-agent art critique

Send a labeled contact sheet (hero, orthographic views, wireframe, flat base-color, PBR, normal/depth, 64 px thumbnail) to at least two independent vision-model families. Suggested roles:

- **Art director:** silhouette, hierarchy, focal point, palette, style-board fit, thumbnail readability.
- **Construction critic:** believable attachment, thickness, anatomy/mechanics, floating/interpenetrating parts.
- **Material critic:** PBR plausibility, material separation, baked lighting, seams, texel density.
- **Game/runtime critic:** camera readability, collision/pivot/scale, transparency, performance.
- **Red-team critic:** argues for rejection and cites the single most damaging visible defect.

The adjudicator sees anonymized critiques and metric vectors, never the producer's chain-of-thought. A failed criterion yields a constrained repair brief (`increase stock depth 12–18%`, `join floating sight`, `repack UV island`) rather than a vague “make better” prompt.

### Gate 7 — Optimization and runtime proof (hard)

- Export authoritative GLB from Blender.
- Run Khronos glTF Validator: zero errors; warnings explicitly waived or fixed.
- Make an optimized derivative with glTF Transform/meshoptimizer/texture compression; never overwrite source GLB.
- Re-run validation and compare before/after renders (silhouette, DINO/LPIPS, material channels).
- Load the exact optimized GLB in a loopback-served Three.js harness using the target Three.js revision.
- Capture deterministic browser screenshots, console output, animation list, draw calls, triangles, materials, textures, GPU memory estimate, and load time.

### Gate 8 — Release and human approval

Publish transactionally only after all gates pass. Package:

- source `.blend`/raw generator output;
- authoritative and optimized `.glb`;
- previews/contact sheet;
- validation/runtime reports;
- rights/provenance manifest and hashes;
- model/service terms snapshot references;
- license/attribution notices.

**Human approval remains essential** for (a) the first benchmark asset/style grammar, (b) culturally/IP-sensitive imagery, and (c) final release contact sheet. Automation can handle batch propagation only after that benchmark is approved. A technically valid, high-scoring asset is not automatically beautiful or sellable.

## Practical tools and licensing notes

| Function | Tool | Practical note / commercial caveat | Source |
|---|---|---|---|
| Workflow/orchestration | ComfyUI | Linux-native node graph and reproducible workflow JSON. Core/node licenses must be checked when distributed. | https://github.com/comfyanonymous/ComfyUI |
| Reference conditioning | ComfyUI IP-Adapter Plus | Strong image/style reference control; repository GPL-3.0 and checkpoint licenses are separate. | https://github.com/cubiq/ComfyUI_IPAdapter_plus |
| Shape/depth/edge control | ControlNet | Apache-2.0 code; each base/control checkpoint must be audited separately. | https://github.com/lllyasviel/ControlNet |
| Commercial concept API | Adobe Firefly API | Provenance/commercial-safety positioning; Adobe may attach Content Credentials. Enterprise indemnification, where offered, is plan/contract-specific—not universal. | https://developer.adobe.com/firefly-services/docs/firefly-api/ |
| Firefly training/provenance approach | Adobe | States Firefly is trained on licensed/public-domain content and describes Content Credentials approach. | https://www.adobe.com/ai/overview/firefly/gen-ai-approach.html |
| Commercial concept API | BFL FLUX API | Current terms say BFL claims no ownership in outputs and permits personal/commercial output use, subject to restrictions; terms also contain broad input/output service-improvement licenses, so review privacy needs. | https://docs.bfl.ai/quick_start/introduction and https://bfl.ai/legal/terms-of-service |
| Local concept model | FLUX.1-schnell | Apache-2.0 model card; quality/control trade-off versus hosted models. Do not assume other FLUX checkpoints share this license. | https://huggingface.co/black-forest-labs/FLUX.1-schnell |
| Consistent multiview + normals | Zero123++ | Good research tool, but code Apache-2.0 and model weights CC-BY-NC-4.0; README explicitly bars the model from a commercial product pipeline. | https://github.com/SUDO-AI-3D/zero123plus |
| Multiview colors/normals | Wonder3D | Official repo states MIT; still audit downloaded weights/dependencies. | https://github.com/xxlong0/Wonder3D |
| High-res multiview | Era3D | AGPL-3.0; repo says downstream products containing code/model should open-source unless a commercial license is obtained. | https://github.com/pengHTYX/Era3D |
| Image-to-3D | TRELLIS | Models and majority of code MIT; README flags differently licensed submodules. HF image model card is MIT. | https://github.com/microsoft/TRELLIS and https://huggingface.co/microsoft/TRELLIS-image-large |
| Image-to-3D baseline | TripoSR | Repo states code and pretrained models MIT; about 6 GB VRAM default. | https://github.com/VAST-AI-Research/TripoSR |
| Image-to-3D | InstantMesh | Sparse-view LRM pipeline; useful alternative, but weight/dependency licenses need audit. | https://github.com/TencentARC/InstantMesh |
| Fast GLB reconstruction | Stable Fast 3D | Linux is the primary supported path; saves GLB; gated/custom Stability license—not plain MIT/Apache. | https://github.com/Stability-AI/stable-fast-3d and https://huggingface.co/stabilityai/stable-fast-3d |
| PBR 3D generation | Hunyuan3D-2.1 | Strong PBR system, but custom territorial/commercial license; excludes EU/UK/South Korea and has >1M-MAU trigger. | https://github.com/Tencent-Hunyuan/Hunyuan3D-2.1/blob/main/LICENSE |
| Hosted text/image-to-3D | Meshy API | Free-plan outputs are owned by provider and licensed CC BY 4.0 per current terms; paid-plan handling differs. Verify plan, privacy, and terms snapshot. | https://docs.meshy.ai/en and https://www.meshy.ai/terms-of-use |
| Hosted text/image-to-3D | Tripo API | Current terms permit lawful commercial/non-commercial output use but impose restrictions and disclaim warranties. Archive exact terms/API version. | https://docs.tripo3d.ai/ and https://www.tripo3d.ai/terms |
| Segmentation/masks | SAM 2 | Checkpoints and training/demo code Apache-2.0. | https://github.com/facebookresearch/sam2 |
| Semantic/style embedding | OpenCLIP | Use fixed model/version; checkpoint licenses vary. LAION ViT-H card is MIT. | https://github.com/mlfoundations/open_clip and https://huggingface.co/laion/CLIP-ViT-H-14-laion2B-s32B-b79K |
| Visual correspondence/style | DINOv2 | Standard DINOv2 Small card is Apache-2.0. Do not generalize to every repo checkpoint (e.g. specialized XRay weights have different terms). | https://github.com/facebookresearch/dinov2 and https://huggingface.co/facebook/dinov2-small |
| Perceptual similarity | DreamSim | MIT code; designed for mid-level perceptual similarity. Audit bundled/backbone weights separately. | https://github.com/ssundaram21/dreamsim |
| Preference score | PickScore | Useful soft ranker; code MIT, but HF checkpoint card currently lacks a clear license field—resolve before commercial deployment. | https://github.com/yuvalkirstain/PickScore and https://huggingface.co/yuvalkirstain/PickScore_v1 |
| Preference score | ImageReward | Trained on 137k expert comparison pairs and reports outperforming CLIP/aesthetic/BLIP on its benchmark. Use as a biased soft ranker; verify checkpoint terms. | https://github.com/zai-org/ImageReward |
| Aesthetic score | LAION aesthetic predictor | CLIP+MLP estimates average preference; useful for filtering, unsafe as a release gate. | https://github.com/christophschuhmann/improved-aesthetic-predictor |
| IQA toolbox | pyIQA | Broad metrics, but current repository license is PolyForm Noncommercial/NTU components. Do not embed in a commercial pipeline without permission. | https://github.com/chaofengc/IQA-PyTorch |
| Monocular depth | Depth Anything V2 Small | Small model Apache-2.0; Base/Large/Giant are CC-BY-NC-4.0 per repo. | https://github.com/DepthAnything/Depth-Anything-V2 and https://huggingface.co/depth-anything/Depth-Anything-V2-Small-hf |
| Depth/normals | Marigold | Useful independent pseudo-depth/normal priors; HF v1.1 cards list OpenRAIL++. Review restrictions. | https://github.com/prs-eth/Marigold and https://huggingface.co/prs-eth/marigold-normals-v1-1 |
| Cross-view feature tracks | LightGlue | Code/weights Apache-2.0; use DISK/ALIKED for compatible licensing; repo warns SuperPoint is restrictive. | https://github.com/cvg/LightGlue |
| Render QA passes | Blender | Official render passes include Z, Normal and other data passes. | https://docs.blender.org/manual/en/latest/render/layers/passes.html |
| GLB validation | Khronos glTF Validator | Canonical glTF validation tool/web UI. | https://github.com/KhronosGroup/glTF-Validator and https://github.khronos.org/glTF-Validator/ |
| GLB optimization | glTF Transform | MIT CLI/library; Draco/Meshopt/texture workflows. | https://github.com/donmccurdy/glTF-Transform |
| Mesh compression | meshoptimizer | glTF compression/optimization guidance. | https://meshoptimizer.org/gltf/ |
| Three.js runtime | Three.js GLTFLoader | Test the exact release artifact in the target renderer. | https://threejs.org/docs/#examples/en/loaders/GLTFLoader |
| Multi-model critics | OpenAI vision | Independent hosted VLM option. | https://developers.openai.com/api/docs/guides/images-vision |
| Multi-model critics | Anthropic vision | Independent hosted VLM option. | https://platform.claude.com/docs/en/build-with-claude/vision |
| Multi-model critics | Gemini image understanding | Independent hosted VLM option. | https://ai.google.dev/gemini-api/docs/image-understanding |
| Provenance standard | C2PA | Standard for signed provenance/history assertions. | https://spec.c2pa.org/specifications/specifications/2.2/index.html |
| Provenance tooling | c2pa-rs / c2patool | Open implementation and CLI; inspect supported formats. | https://github.com/contentauth/c2pa-rs and https://opensource.contentauthenticity.org/docs/c2patool/ |
| Rights-cleared references | Poly Haven | Assets are CC0; record per-file hashes and source URLs. | https://polyhaven.com/license |
| Software/model BOM | SPDX | Use an SPDX SBOM plus a custom model/data manifest; SPDX alone does not prove source-content rights. | https://spdx.github.io/spdx-spec/ |

## Suggested initial pass thresholds (calibrate, do not universalize)

These are starting points for one approved style profile, not claims of objective quality:

- zero glTF Validator errors;
- 100% required-part inventory in hero + orthographic views;
- silhouette IoU ≥ 0.85 on the source hero view and ≥ 0.75 on other conditioned views;
- no unintended disconnected foreground components larger than 0.5% of projected area;
- DINO source-render cosine above a threshold calibrated on approved assets (never borrow a universal threshold from another model/version);
- depth Spearman correlation ≥ 0.75 after foreground masking and scale/shift normalization;
- normal median angular error ≤ 25° only where predictor confidence/mask is valid;
- optimization before/after silhouette IoU ≥ 0.995 and no visible material regression;
- all hard gates pass, two independent critics pass each critical rubric item, no red-team catastrophic veto;
- human benchmark/final contact-sheet approval.

Calibrate all learned-metric thresholds from a small labeled set: clearly rejected assets, acceptable assets, and exemplar assets in the exact target style. Never interpret raw CLIP/DINO/aesthetic numbers across model revisions as stable quality units.

## Recommended minimum viable implementation

1. **ComfyUI/BFL/Firefly** creates 24 thumbnails and a frozen contact sheet.
2. **SAM 2 + OpenCLIP + DINOv2 Small + LAION aesthetic predictor** filter/rank; two external VLM families blind-review the final 6.
3. Human approves one benchmark image.
4. Generate locked multiview; reject contradictions with SAM/DINO/LightGlue + VLM inventory.
5. Run **TRELLIS and TripoSR**; Blender Python performs deterministic cleanup and fixed-pass renders.
6. Compare source/render silhouettes, depth ranks, normals, DINO embeddings; run independent role critics.
7. Export and optimize GLB; run Khronos Validator and a Playwright-driven Three.js preview.
8. Publish only after signed provenance manifest and human final contact-sheet approval.

This system is autonomous over routine iteration while reserving scarce human judgment for the two decisions machines remain weakest at: defining the visual bar and declaring the result genuinely good.