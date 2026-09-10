import bpy,json
from pathlib import Path
from mathutils.bvhtree import BVHTree
ROOT=Path(__file__).resolve().parent
deps=bpy.context.evaluated_depsgraph_get();scene=bpy.context.scene;cache={}
def group(name):return [o for o in scene.objects if o.name==name or o.name.startswith(name+".")]
def geom(ob):
 if ob.name in cache:return cache[ob.name]
 ev=ob.evaluated_get(deps);me=ev.to_mesh();vs=[ev.matrix_world@v.co for v in me.vertices];fs=[tuple(p.vertices) for p in me.polygons];ev.to_mesh_clear()
 cache[ob.name]=(vs,BVHTree.FromPolygons(vs,fs));return cache[ob.name]
checks={}
def connected(child,parent):
 cs=group(child);ps=group(parent);assert cs and ps,(child,parent)
 for c in cs:
  cv,ct=geom(c);best=1e9;intersects=False
  for p in ps:
   pv,pt=geom(p)
   if ct.overlap(pt):intersects=True;best=0;break
   best=min(best,min(pt.find_nearest(v)[3] for v in cv),min(ct.find_nearest(v)[3] for v in pv))
  checks[c.name+" -> "+parent]=best*1000
  assert best<.0015,(c.name,parent,best)
for pair in [
 ("H4_Cab_Hatch_Gasket","Cockpit_Pressure_Hull"),("H4_Cab_Hatch","H4_Cab_Hatch_Gasket"),("H4_Cab_Hatch_Handle","H4_Cab_Hatch"),
 ("H4_Cab_Lamp","Cockpit_Pressure_Hull"),("H4_Cab_Lamp_Lens","H4_Cab_Lamp"),("H4_Cab_Vent_Recess","Cockpit_Pressure_Hull"),("H4_Cab_Vent_Fin","H4_Cab_Vent_Recess"),
 ("H4_Radiator_Base","Laboratory_Pressure_Hull"),("H4_Radiator_Core","H4_Radiator_Base"),("H4_Radiator_Fin","H4_Radiator_Core"),
 ("H4_Roof_Rail_Foot","Laboratory_Pressure_Hull"),("H4_Roof_Rail_Post","H4_Roof_Rail_Foot"),("H4_Roof_Rail","H4_Roof_Rail_Post"),
 ("H4_Mast_Foot","Laboratory_Pressure_Hull"),("H4_Mast_Stem","H4_Mast_Foot"),("H4_Mast_Collar","H4_Mast_Stem"),("H4_Sensor_Head","H4_Mast_Stem"),("H4_Sensor_Lens_Housing","H4_Sensor_Head"),("H4_Sensor_Lens","H4_Sensor_Lens_Housing"),
 ("H4_Antenna_Base","Laboratory_Pressure_Hull"),("H4_Antenna","H4_Antenna_Base"),
 ("H4_Lab_Panel_Gasket","Laboratory_Pressure_Hull"),("H4_Lab_Service_Panel","H4_Lab_Panel_Gasket"),("H4_Lab_Window_Gasket","H4_Lab_Service_Panel"),("H4_Lab_Window_Glass","H4_Lab_Window_Gasket"),
 ("H4_Airlock_Seal","Laboratory_Pressure_Hull"),("H4_Airlock_Door","H4_Airlock_Seal"),("H4_Airlock_Hinge","H4_Airlock_Door"),("H4_Airlock_Handle_Foot","H4_Airlock_Door"),("H4_Airlock_Handle","H4_Airlock_Handle_Foot"),
 ("H4_Step_Hull_Mount","Laboratory_Pressure_Hull"),("H4_Step_Support","H4_Step_Hull_Mount"),("H4_Rear_Step","H4_Step_Support"),("H4_Rear_Step_Tread","H4_Rear_Step")
]:connected(*pair)
for label in ["F_L","F_R"]:
 connected("H4_Front_Guard_Bracket_"+label,"Cockpit_Pressure_Hull")
 connected("H4_Front_Guard_"+label,"H4_Front_Guard_Bracket_"+label)
 guard=group("H4_Front_Guard_"+label)+group("H4_Front_Guard_Bracket_"+label)+group("H4_Front_Guard_Edge_"+label)
 tracks=[o for o in scene.objects if o.name.startswith("Track_"+label+"_")]
 for g in guard:
  for t in tracks:assert not geom(g)[1].overlap(geom(t)[1]),(g.name,t.name)
(ROOT/"qa"/"hull-attachment-check.json").write_text(json.dumps({"result":"PASS","connected_parts_checked":len(checks),"distance_mm":checks,"front_track_guards_clear":True},indent=2))
print("HULL_ATTACHMENT_CHECK_PASS",len(checks),flush=True)
