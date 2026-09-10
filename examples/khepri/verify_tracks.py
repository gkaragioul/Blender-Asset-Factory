import bpy,json
from pathlib import Path
from mathutils.bvhtree import BVHTree
ROOT=Path(__file__).resolve().parent
scene=bpy.context.scene;deps=bpy.context.evaluated_depsgraph_get()
def geometry(obs):
 vs=[];fs=[]
 for ob in obs:
  if ob.type not in {"MESH","CURVE","FONT"}:continue
  ev=ob.evaluated_get(deps);me=ev.to_mesh();offset=len(vs)
  vs.extend([ev.matrix_world@v.co for v in me.vertices])
  fs.extend([tuple(offset+i for i in p.vertices) for p in me.polygons])
  ev.to_mesh_clear()
 return vs,BVHTree.FromPolygons(vs,fs)
def one(name):return geometry([bpy.data.objects[name]])
bodyv,body=geometry(bpy.data.collections["KHEPRI_02_Laboratory"].objects)
frontv,front=geometry([o for o in scene.objects if o.name.startswith(("Cockpit_Pressure_Hull","Nose_Impact_Fascia"))])
report={}
for s in ["L","R"]:
 v,t=one("Tow_"+s+"_Seated_Base")
 report["tow_base_"+s+"_body_intersections"]=len(t.overlap(front))
 assert report["tow_base_"+s+"_body_intersections"]>0
 v,t=one("Tow_"+s+"_Loop");_,pin=one("Tow_"+s+"_Cross_Pin")
 assert t.overlap(pin),"Loop not connected to pin"
 report["tow_loop_"+s+"_pin_connected"]=True
 v,t=geometry([o for o in scene.objects if o.name.startswith("Track_R_"+s+"_")])
 intersections=len(t.overlap(body))
 report["rear_track_"+s+"_body_intersections"]=intersections
 assert intersections==0,("Track/body collision",s,intersections)
 report["rear_track_"+s+"_nearest_sample_clearance_mm"]=min(body.find_nearest(p)[3] for p in v)*1000
 _,guard=geometry([o for o in scene.objects if o.name.startswith("Rear_"+s+"_") and "Guard" in o.name])
 assert not t.overlap(guard),"Track/guard collision"
 _,axle=one("Rear_"+s+"_Pivot_Axle")
 _,recess=one("CleanTrack_R_"+s+"_Recess")
 assert axle.overlap(recess),"Axle not seated in pod"
 _,saddle=one("Rear_"+s+"_Chassis_Saddle")
 assert saddle.overlap(body),"Saddle not seated in hull"
 report["rear_"+s+"_axle_and_saddle_connected"]=True
for label in ["F_L","F_R","R_L","R_R"]:
 _,belt=one("Track_"+label+"_Continuous_Belt")
 for i in range(1,5):
  vs,_=one("CleanTrack_"+label+"_Roller_%02d"%i)
  dist=min(belt.find_nearest(p)[3] for p in vs)
  assert dist<.0001,(label,i,dist)
  report[label+"_roller_%02d_contact_mm"%i]=dist*1000
report["result"]="PASS"
(ROOT/"qa"/"geometry-verification.json").write_text(json.dumps(report,indent=2))
__result__=report
