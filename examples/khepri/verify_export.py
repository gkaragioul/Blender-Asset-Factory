import bpy,json,math
from pathlib import Path
from mathutils import Vector
ROOT=Path(__file__).resolve().parent
source=bpy.data.scenes["KHEPRI_Explorer"]
bpy.context.window.scene=source
bpy.context.view_layer.update()
deps=bpy.context.evaluated_depsgraph_get()
def bounds(objects,evaluate=False):
    lo=[float("inf")]*3;hi=[float("-inf")]*3
    count=0;triangles=0
    for ob in objects:
        if ob.type not in {"MESH","CURVE","FONT"}:continue
        if any(c.name.endswith("90_Studio") for c in ob.users_collection):continue
        ev=ob.evaluated_get(deps) if evaluate else ob
        me=ev.to_mesh() if evaluate else ob.data
        if not me or not me.polygons:
            if evaluate:ev.to_mesh_clear()
            continue
        count+=1
        triangles+=sum(len(p.vertices)-2 for p in me.polygons)
        for v in me.vertices:
            p=ob.matrix_world@v.co
            assert all(math.isfinite(x) for x in p),ob.name
            for i in range(3):
                lo[i]=min(lo[i],p[i]);hi[i]=max(hi[i],p[i])
        if evaluate:ev.to_mesh_clear()
    return {"min":lo,"max":hi,"dimensions":[hi[i]-lo[i] for i in range(3)],"meshes":count,"triangles":triangles}
source_info=bounds(source.objects,True)
pods=[o for o in source.objects if o.name.startswith("CTRL_Track_")]
assert len(pods)==4
assemblies=[[o for o in pod.children if o.name.startswith("CleanTrack_")] for pod in pods]
assert all(len(a)==9 for a in assemblies)
mesh_users={}
for assembly in assemblies:
    for ob in assembly:
        mesh_users.setdefault(ob.data.name,0)
        mesh_users[ob.data.name]+=1
        assert ob.data.polygons and ob.data.materials
assert len(mesh_users)==9 and set(mesh_users.values())=={4}
packed=[i.name for i in bpy.data.images if i.packed_file and "blueprint" in i.name.lower()]
assert packed,"Blueprint missing from saved source"
scene=bpy.data.scenes.new("GLB_Verification")
bpy.context.window.scene=scene
bpy.ops.import_scene.gltf(filepath=str(ROOT/"exports"/"khepri-explorer.glb"))
bpy.context.view_layer.update()
imported_info=bounds(scene.objects)
imported_pods=[o.name for o in scene.objects if o.name.startswith("CTRL_Track_")]
assert len(imported_pods)==4
assert len([o for o in scene.objects if o.name.startswith("CleanTrack_") and o.type=="MESH"])==36
assert all(ob.data.materials for ob in scene.objects if ob.type=="MESH")
assert source_info["meshes"]==imported_info["meshes"],(source_info,imported_info)
assert source_info["triangles"]==imported_info["triangles"],(source_info,imported_info)
for edge in ["min","max"]:
    assert max(abs(a-b) for a,b in zip(source_info[edge],imported_info[edge]))<.0001,(source_info,imported_info)
result={"source":source_info,"reimported_glb":imported_info,"all_four_pods_share_same_nine_mesh_templates":True,"packed_blueprints":packed,"export_bytes":(ROOT/"exports"/"khepri-explorer.glb").stat().st_size,"result":"PASS"}
(ROOT/"qa"/"export-check.json").write_text(json.dumps(result,indent=2))
print("VERIFIED_V4",json.dumps(result),flush=True)
