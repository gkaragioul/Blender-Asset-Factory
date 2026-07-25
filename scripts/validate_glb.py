"""Import the generated GLB into a clean Blender process as a portability check."""

import bpy


GLB = r"G:\DevWork\GameDev\BlenderAssetFactory\assets\ps1_wood_crate_01\ps1_wood_crate_01.glb"

bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)
bpy.ops.import_scene.gltf(filepath=GLB)
meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
if len(meshes) != 1:
    raise RuntimeError(f"Expected one mesh, imported {len(meshes)}")
print(f"GLB_IMPORT_OK objects={len(bpy.context.scene.objects)} meshes={len(meshes)}")
