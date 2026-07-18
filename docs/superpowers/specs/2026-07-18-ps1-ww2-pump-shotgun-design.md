# PS1 WWII Pump Shotgun Asset Design

Date: 2026-07-18
Status: Approved design awaiting written-spec review

## Objective

Create a fictional WWII trench-gun-style pump shotgun as an extremely lightweight PS1-era game asset. The asset must retain a recognizable, dramatic first-person silhouette while remaining suitable for browser games built with Three.js or React Three Fiber.

## Visual Direction

The shotgun uses late-war military styling without reproducing one manufacturer's weapon exactly. Its defining forms are a dark walnut buttstock, compact blued-steel receiver, single barrel, ribbed wooden pump, perforated heat shield, exposed hammer, simplified trigger guard, front bead, and a restrained bayonet-lug silhouette.

Proportions are deliberately chunky and slightly exaggerated to survive low-resolution rendering. Fine manufacturing details, internal mechanisms, readable markings, screws, and realistic disassembly features are outside scope.

## Geometry and Performance

- Target length: approximately 1.02 metres.
- Triangle budget: 450 triangles maximum for the visual mesh.
- Construction: modular hard-surface primitives consolidated into one visual mesh.
- Shading: flat or deliberately faceted where it strengthens the PS1 appearance.
- Collision: one separate simplified box-based collision proxy.
- Pivot: positioned around the firing-hand grip for first-person animation.
- Orientation: barrel along Blender positive X, Z up, exported Y-up through glTF.
- Scale: one Blender unit equals one metre.

## Materials

Use three lightweight materials:

1. Dark walnut for the stock and pump.
2. Blued steel for the receiver, barrel, heat shield, and hardware.
3. Near-black accent for cavities and high-contrast mechanical separation.

The initial release uses material colours without image textures. A later texture pass may introduce a tiny pixel-art atlas, but it is not part of this build.

## Live Construction Experience

The open Blender viewport must show the asset being built in recognizable stages rather than receiving a completed mesh instantly. A timer-driven Blender script will add and refine components approximately every 0.7–1.0 seconds while leaving the interface responsive.

The visible sequence is:

1. Clear the default scene and establish the asset collection.
2. Block out the receiver.
3. Add the barrel and muzzle.
4. Add the magazine tube.
5. Shape the buttstock and grip transition.
6. Add the ribbed wooden pump.
7. Add heat-shield geometry.
8. Add hammer, trigger, trigger guard, bead, and lug silhouettes.
9. Apply materials and faceted shading.
10. Consolidate and validate the visual mesh.
11. Create the collision proxy.
12. Frame the finished asset for inspection and save/export.

## Deliverables

Canonical output directory:

`G:\DevWork\GameDev\BlenderAssetFactory\assets\ps1_ww2_pump_shotgun_01`

Required files:

- `ps1_ww2_pump_shotgun_01.blend`
- `ps1_ww2_pump_shotgun_01.glb`
- `ps1_ww2_pump_shotgun_01_preview.png`
- `manifest.json`

The manifest records dimensions, triangle count, triangle budget, file sizes, material count, pivot convention, and validation status.

## Validation

Completion requires all of the following:

- The complete construction is visibly observable in the open Blender viewport.
- Visual mesh contains no more than 450 triangles.
- Exported GLB imports into a factory-clean Blender session.
- Imported GLB contains the expected visual mesh and materials.
- Dimensions and orientation match the specification.
- All deliverables exist beneath the canonical `G:` asset directory.
- The Blender MCP bridge remains connected and responsive after generation.

## Failure Handling

If a construction step fails, the timed sequence stops, leaves completed components visible, and records the failing stage in Blender's scene properties. Export occurs only after geometry and budget validation succeed. Existing unrelated files are never deleted or overwritten outside the asset's dedicated output directory.
