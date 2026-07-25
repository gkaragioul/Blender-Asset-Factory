## Outcome

Primary repositories, model cards, licenses, and service documentation were checked directly on **2026-07-22**. All URLs listed below resolved successfully at research time.

### Ranked shortlist for lightweight WW2 / PS1-style Three.js assets

| Rank | Model / service | Why it ranks here | Inputs | Materials / texture | Geometry / topology | Linux hardware | Commercial implications |
|---|---|---|---|---|---|---|---|
| **1** | **Pixal3D** | Best current open local choice when a strong reference image is available. SIGGRAPH 2026 system built on TRELLIS.2, with pixel-aligned conditioning and near-reconstruction-level fidelity. | Single image. No native text or user multiview interface documented. | Full PBR; 1024–1536 resolution pipeline; GLB export. | Inherits TRELLIS.2 O-Voxel strengths, including sharp details and complex/open topology. Outputs remain dense generative meshes requiring game retopology/decimation. | Linux/NVIDIA; inherits TRELLIS.2's **24 GB minimum**. Low-VRAM mode exists, but its actual minimum is not documented. CUDA extension compilation including NATTEN is required. | **MIT** for project and weights; check third-party NOTICE/dependency licenses. |
| **2** | **TRELLIS.2-4B** | Strongest general-purpose permissively licensed foundation: excellent PBR, arbitrary topology, direct GLB, texture-only mode, and training code. | Single image; shape-conditioned PBR texturing. No released native text model. | Base color, roughness, metallic, opacity; supports transparency/translucency. 4K export example. | Explicit support for open surfaces, non-manifold geometry, and internal structures. Built-in remesh/decimate/UV path, but example defaults to up to **1M faces**, not game-ready topology. | Linux only, NVIDIA **≥24 GB**, verified A100/H100; CUDA 12.4, PyTorch 2.6, several compiled CUDA components. | Code and model **MIT**. Separate licenses apply to nvdiffrast/nvdiffrec and other subcomponents. |
| **3** | **Hunyuan3D 2.1** | Very strong geometry plus one of the better dedicated local PBR painters. Easier to fit than TRELLIS.2 if shape and paint stages are run separately. | Native documented path is single-image shape generation. Hunyuan 2.0 also provides multiview shape and text/image API routes. | Dedicated 2B PBR painter; metallic and richer material response; can texture generated or existing meshes. | High-detail but generally dense/watertight generative geometry. No claim of animation-quality loops or clean hard-surface topology. | Linux/Windows/macOS; PyTorch 2.5.1/CUDA 12.4. **10 GB shape, 21 GB paint, 29 GB combined**. Hunyuan 2.0 needs about **6 GB shape / 16 GB full**. | **Not open-source in the OSI/permissive sense.** Tencent Community License excludes the **EU, UK, and South Korea**, requires notices/disclosures, and requires a separate license above the stated 1M-MAU threshold. HF marks it EU-disallowed. |
| **4** | **Meshy API / Meshy 6** | Best turnkey service for autonomous asset production: text, image, multi-image, smart topology, explicit polygon targets, quad-dominant remesh, PBR, retexture, UV, rigging, and animation APIs. Particularly useful when local GPU setup is undesirable. | Text, image, and multi-image APIs. | Base color plus normal, metallic, roughness; Meshy 6 also supports emission; optional 4K texture. | `smart-topology`, low-poly generation, quad-dominant or decimated triangle output, and target polygon count. More production-oriented than raw research repositories, though still inspect results manually. | Hosted; no local GPU requirement. | Proprietary paid API. Current terms say paid-plan customers own outputs with commercial rights; free-plan outputs are CC BY 4.0. Preserve a dated copy of the applicable plan terms. |
| **5** | **Stable Fast 3D / SPAR3D** | Best local low-VRAM path. SF3D is extremely practical for static props; SPAR3D improves reconstruction and adds point conditioning. | Single image; SPAR3D supports point-aware editing/conditioning. | SF3D predicts UV textures and material parameters and performs de-lighting; GLB output. SPAR3D similarly produces textured GLB. Not as rich as TRELLIS.2 PBR. | Explicit mesh-artifact reduction plus optional triangle or quad remeshing. Still not equivalent to hand-built game topology. | SF3D approximately **6 GB**. SPAR3D defaults around **10.5 GB**, low-VRAM around **7 GB**. Linux is the primary supported CUDA platform; CPU/MPS paths exist but are slower/experimental. | Stability Community License: free limited commercial use below **US$1M annual revenue**, commercial registration required, enterprise license above threshold, and attribution/notice obligations. |
| **6** | **Sloyd** | Strong alternative for PS1/low-poly hard-surface props where topology matters more than free-form fidelity. Parametric, artist-authored parts can produce more predictable topology than diffusion meshes. | Text, images, and editable templates. | AI texturing; feature set is more game-production-oriented than research-model PBR benchmarking. | Polygon-count control, quads, manifold output, part splitting, rigging/animation. Constrained by its parametric/template vocabulary, but that can be an advantage for crates, furniture, tools, and vehicles. | Hosted service with Blender/Unity/Unreal integrations. | Proprietary subscription. Terms grant perpetual worldwide personal and commercial use; marketplace redistribution requires Pro, and commercial 3D printing requires a separate license. |
| **7** | **Step1X-3D** | Good permissive full geometry-and-texture pipeline, but slower and more memory-heavy than newer options. Useful if Apache licensing is a priority. | Single image. Texture system internally generates synchronized multiviews; direct user multiview conditioning remained roadmap work. | SDXL-based synchronized texture synthesis; multiple visual styles, but no explicit full metallic/roughness PBR claim comparable to TRELLIS.2/Hunyuan 2.1. | Watertight TSDF geometry with sharp-edge sampling. Dense generative topology; reduction helper is included. | CUDA 12.4; **27 GB** standard geometry+texture or **29 GB** label-conditioned; about **152 s / 50 steps** in the published table. | **Apache-2.0** for repository and HF model card. |
| **8** | **TripoSG + PartCrafter** | Excellent lightweight geometry stack. TripoSG is a major quality upgrade over TripoSR; PartCrafter adds semantically separable pieces useful for tanks, guns, turrets, wheels, doors, and other articulated props. | Both are single-image. PartCrafter optionally uses a hosted VLM to choose the number of parts. | Geometry only; requires a separate painter such as TRELLIS.2 texture mode, Hunyuan Paint, Meshy, or Blender baking. | TripoSG supports complex topology and explicit face limits. PartCrafter creates multiple independent meshes, but this is **part decomposition**, not clean retopology or guaranteed assembly tolerances. | Both document **≥8 GB VRAM**. PartCrafter tested on Debian 12/H20; TripoSG has straightforward PyTorch/CUDA installation. | Both repositories and HF weights are **MIT**. Check optional VLM provider terms if using its Gemini helpers. |
| **9** | **TRELLIS 1.x** | Still useful when native text conditioning or a 16 GB GPU is important. Image mode is materially preferable to its text models. | Native text and image models; authors recommend text-to-image followed by image-to-3D for quality. | Textured GLB, radiance fields, and Gaussians; not full modern PBR. | FlexiCubes-derived dense meshes with configurable simplification. | Linux, NVIDIA **≥16 GB**, tested A100/A6000; CUDA 11.8/12.2. | Main model/code **MIT**, but its renderer and modified FlexiCubes dependencies have separate NVIDIA-related licenses. Review those before commercial redistribution. |
| **10** | **InstantMesh** | Mature older single-image reconstruction baseline, but surpassed by TRELLIS.2, Pixal3D, Hunyuan 2.1, and TripoSG. | Single image; internally generates multiview images. No direct text. | Vertex colors by default; optional UV texture-map export. No PBR material prediction. | Dense reconstruction mesh; UV unwrapping may be slow at 256 extraction resolution. | Ubuntu-style CUDA installation; README recommends CUDA ≥12.1 and can split the demo over two GPUs. A precise minimum VRAM is not documented. | **Apache-2.0**. |

## Specialist and lower-priority components

- **MeshAnything / MeshAnything V2** — a **mesh-to-mesh retopology-like postprocessor**, not a standalone image/text generator. V2 emits artist-like meshes capped at **1,600 faces**, uses about **8 GB / 45 s on A6000**, and accepts a dense mesh or normal-equipped point cloud. It can be useful for PS1 props, but shape fidelity suffers when compressing complex assets.
  - **Critical license issue:** repository source uses the **S-Lab non-commercial license**, while the HF weight card says MIT. Treat commercial use as **uncleared** until the authors clarify the mismatch.
- **CraftsMan3D** — text/image-to-mesh, approximately 5 seconds coarse generation plus 20 seconds normal-based refinement. Refinement was tested on GTX 3080, but full inference VRAM is not stated. It produces geometry, not a complete textured/PBR asset.
  - The README says MIT, but there is no root LICENSE file in the fetched repository, and related HF checkpoints show inconsistent licenses such as OpenRAIL/“other.” Avoid commercial deployment without written clarification.
- **TripoSR** — MIT, single image, approximately 6 GB, texture baking available. It is now a baseline; SF3D and TripoSG are better successors.
- **Direct3D-S2** — strong high-resolution geometry, MIT, Ubuntu 22.04/CUDA 12.1, roughly **10 GB at 512** or **24 GB at 1024**. No complete texture/PBR pipeline, and the authors discourage the lower-quality 512 model.
- **TripoSF** — MIT, ≥12 GB at 1024³, excellent arbitrary/open-surface representation, but currently a **mesh autoencoder/reconstruction component**, not a complete image-conditioned textured asset generator.
- **Stable3DGen** — MIT TRELLIS adaptation that removes several NVIDIA dependencies specifically to improve commercial deployability. Interesting if TRELLIS dependency licensing blocks a project, but it is less established than TRELLIS.2/Pixal3D.
- **NVIDIA Asset Harvester** — Apache-2.0 and about 16 GB, but optimized for sparse vehicle-camera observations and Gaussian/simulation assets rather than conventional lightweight game meshes.
- **Apple SHARP** — impressive single-image 3D Gaussian reconstruction on CPU/CUDA/MPS, but it outputs Gaussian representations rather than ordinary lightweight meshes; unsuitable as the main Three.js GLB asset generator.
- **Tripo API / Rodin (Hyper3D)** — both remain capable proprietary generation services. Tripo exposes a documented API and permits lawful commercial/non-commercial output use under current terms, with restrictions on competing-model use. Rodin remains referenced by MeshAnything’s authors as a good dense-mesh source, but public licensing/API terms were less transparent than Meshy’s during this review.

## Practical recommendation

For an autonomous Linux-native system:

1. **Generate a clean concept/reference image first**—ideally isolated on transparent or neutral background, orthographic-ish, and without cast shadows.
2. Use:
   - **Pixal3D** on a 24 GB+ GPU for maximum local quality and permissive licensing.
   - **TRELLIS.2** when arbitrary/open topology and comprehensive PBR are the priority.
   - **SF3D/SPAR3D** on 8–12 GB hardware.
   - **Meshy or Sloyd** when dependable low-poly/topology controls matter more than local execution.
3. Treat generated GLB as a **high-resolution source asset**, not final game art:
   - Split moving parts before reduction.
   - Decimate/remesh to roughly **300–5,000 triangles** depending on prop size.
   - Re-bake PBR to 256–1024 px.
   - For PS1 style, quantize/downsample albedo, use nearest filtering, reduce or discard roughness/normal maps, and consider vertex lighting.
   - Generate collision hulls and LODs separately.
4. Use **PartCrafter** selectively for tanks, artillery, weapons, vehicles, and interactive machinery where semantic part separation is valuable.
5. Do not expect any current open generator to reliably produce animation-ready edge loops, historically accurate mechanical construction, or flawless thin geometry without validation.

## Primary evidence URLs

### Open repositories and model cards

- Pixal3D  
  https://github.com/TencentARC/Pixal3D  
  https://huggingface.co/TencentARC/Pixal3D  
  https://ldyang694.github.io/projects/pixal3d/  
  https://arxiv.org/abs/2605.10922

- TRELLIS.2  
  https://github.com/microsoft/TRELLIS.2  
  https://huggingface.co/microsoft/TRELLIS.2-4B  
  https://microsoft.github.io/TRELLIS.2  
  https://github.com/microsoft/TRELLIS.2/blob/main/LICENSE

- TRELLIS 1.x  
  https://github.com/microsoft/TRELLIS  
  https://huggingface.co/microsoft/TRELLIS-image-large  
  https://huggingface.co/microsoft/TRELLIS-text-xlarge

- Hunyuan3D  
  https://github.com/Tencent-Hunyuan/Hunyuan3D-2.1  
  https://huggingface.co/tencent/Hunyuan3D-2.1  
  https://github.com/Tencent-Hunyuan/Hunyuan3D-2.1/blob/main/LICENSE  
  https://github.com/Tencent-Hunyuan/Hunyuan3D-2  
  https://huggingface.co/tencent/Hunyuan3D-2mv

- Stability models  
  https://github.com/Stability-AI/stable-fast-3d  
  https://huggingface.co/stabilityai/stable-fast-3d  
  https://github.com/Stability-AI/stable-point-aware-3d  
  https://huggingface.co/stabilityai/stable-point-aware-3d  
  https://github.com/Stability-AI/stable-fast-3d/blob/main/LICENSE.md

- Tripo open models  
  https://github.com/VAST-AI-Research/TripoSG  
  https://huggingface.co/VAST-AI/TripoSG  
  https://github.com/VAST-AI-Research/TripoSR  
  https://huggingface.co/stabilityai/TripoSR  
  https://github.com/VAST-AI-Research/TripoSF

- PartCrafter  
  https://github.com/wgsxm/PartCrafter  
  https://huggingface.co/wgsxm/PartCrafter  
  https://wgsxm.github.io/projects/partcrafter/

- Step1X-3D  
  https://github.com/stepfun-ai/Step1X-3D  
  https://huggingface.co/stepfun-ai/Step1X-3D

- InstantMesh  
  https://github.com/TencentARC/InstantMesh  
  https://huggingface.co/TencentARC/InstantMesh

- MeshAnything  
  https://github.com/buaacyw/MeshAnythingV2  
  https://huggingface.co/Yiwen-ntu/MeshAnythingV2  
  https://github.com/buaacyw/MeshAnythingV2/blob/main/LICENSE.txt

- CraftsMan3D  
  https://github.com/HKUST-SAIL/CraftsMan3D

- Other relevant repositories  
  https://github.com/DreamTechAI/Direct3D-S2  
  https://github.com/Stable-X/Stable3DGen  
  https://github.com/NVIDIA/asset-harvester  
  https://github.com/apple/ml-sharp

### Hosted services

- Meshy API  
  https://docs.meshy.ai/en/api/text-to-3d  
  https://docs.meshy.ai/en/api/image-to-3d  
  https://docs.meshy.ai/en/api/multi-image-to-3d  
  https://docs.meshy.ai/en/api/rigging-and-animation  
  https://docs.meshy.ai/en/api/pricing  
  https://www.meshy.ai/terms-of-use

- Tripo API and terms  
  https://platform.tripo3d.ai/docs  
  https://www.tripo3d.ai/terms

- Sloyd  
  https://sloyd.gitbook.io/documentation  
  https://www.sloyd.ai/terms-of-use

- Rodin / Hyper3D  
  https://hyper3d.ai/

## Files and issues

- **Workspace files modified:** none.
- Temporary source copies were downloaded under `/tmp/3dresearch` for comparison only.
- Main uncertainties: undocumented VRAM floors for Pixal3D low-VRAM mode, InstantMesh, and full CraftsMan inference; contradictory MeshAnything/CraftsMan licensing metadata; proprietary Rodin terms were less explicit than Meshy/Sloyd terms.