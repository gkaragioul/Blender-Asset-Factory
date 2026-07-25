"""Independent original PS1-era over-under shotgun. Uses no supplied mesh or texture data."""
from pathlib import Path
import math, sys, json
import bpy
from mathutils import Vector

OUT_REL='products/ww2_lowpoly_frontline_pack/original-ps1-over-under-shotgun-v1'
ASSET='original_ps1_over_under_shotgun_v1'

def clear():
 bpy.ops.object.select_all(action='SELECT'); bpy.ops.object.delete(use_global=False)

def mat(name,color):
 m=bpy.data.materials.new(name); m.diffuse_color=(*color,1); m.use_nodes=True
 b=m.node_tree.nodes.get('Principled BSDF'); b.inputs['Base Color'].default_value=(*color,1); b.inputs['Roughness'].default_value=1
 if 'Specular IOR Level' in b.inputs: b.inputs['Specular IOR Level'].default_value=0
 m['ps1_unlit']=True; return m

def box(name,loc,dim,material,bevel=.0):
 bpy.ops.mesh.primitive_cube_add(size=1,location=loc); o=bpy.context.object; o.name=name; o.dimensions=dim; bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
 o.data.materials.append(material)
 if bevel:
  md=o.modifiers.new('Chamfer','BEVEL'); md.width=bevel; md.segments=1; bpy.context.view_layer.objects.active=o; bpy.ops.object.modifier_apply(modifier=md.name)
 for p in o.data.polygons:p.use_smooth=False
 return o

def cyl(name,loc,rad,depth,material,verts=8):
 bpy.ops.mesh.primitive_cylinder_add(vertices=verts,radius=rad,depth=depth,location=loc,rotation=(0,math.pi/2,0));o=bpy.context.object;o.name=name;o.data.materials.append(material)
 for p in o.data.polygons:p.use_smooth=False
 return o

def profile(name,pts,width,material):
 h=width/2; vs=[(x,-h,z) for x,z in pts]+[(x,h,z) for x,z in pts]; n=len(pts); fs=[tuple(range(n-1,-1,-1)),tuple(range(n,2*n))]
 fs += [(i,(i+1)%n,n+(i+1)%n,n+i) for i in range(n)]
 me=bpy.data.meshes.new(name+'Mesh');me.from_pydata(vs,[],fs);o=bpy.data.objects.new(name,me);bpy.context.collection.objects.link(o);me.materials.append(material)
 for p in me.polygons:p.use_smooth=False
 return o

def bounds(objs):
 pts=[o.matrix_world@Vector(c) for o in objs for c in o.bound_box]; lo=Vector((min(p.x for p in pts),min(p.y for p in pts),min(p.z for p in pts)));hi=Vector((max(p.x for p in pts),max(p.y for p in pts),max(p.z for p in pts)));return lo,hi,(lo+hi)/2

def main(root):
 clear(); out=root/OUT_REL;out.mkdir(parents=True,exist_ok=True)
 steel=mat('PS1_Parkerized_Steel',(0.055,.075,.09)); dark=mat('PS1_Bore_Black',(.008,.01,.012)); wood=mat('PS1_Walnut',(0.20,.055,.016)); woodhi=mat('PS1_Walnut_Highlight',(.38,.12,.028)); brass=mat('PS1_Brass',(.38,.25,.05)); objs=[]
 # original stock, measured only against generic shotgun proportions
 stock=profile('Original_Walnut_Stock',[(-.67,.105),(-.55,.125),(-.36,.112),(-.20,.072),(-.12,.038),(-.12,-.030),(-.28,-.055),(-.52,-.075),(-.67,-.040)],.105,wood);objs.append(stock)
 cheek=profile('Stock_Cheek_Facet',[(-.57,.095),(-.37,.090),(-.22,.058),(-.34,.015),(-.54,.022)],.008,woodhi);cheek.location.y=-.057;objs.append(cheek)
 objs += [box('Buttplate',(-.677,0,.026),(.014,.112,.15),dark,.005),box('Receiver',(-.03,0,.025),(.19,.095,.12),steel,.012),box('Break_Action_Seam',(.065,0,.025),(.009,.10,.122),dark),box('Top_Lever',(-.045,0,.095),(.075,.035,.018),steel,.006)]
 # original vertical over-under pair and explicit dark bores
 for z,label in ((.053,'Upper'),(-.005,'Lower')):
  objs.append(cyl(label+'_Barrel',(.28,0,z),.025,.62,steel))
  objs.append(cyl(label+'_Muzzle_Bore',(.593,0,z),.017,.009,dark,8))
 objs += [box('Wood_Foreend',(.25,0,.022),(.20,.085,.075),wood,.018),box('Foreend_Band',(.16,0,.022),(.012,.092,.080),brass),box('Foreend_Band_Front',(.34,0,.022),(.012,.092,.080),brass)]
 # trigger guard: low-poly torus in vertical plane, plus two triggers
 bpy.ops.mesh.primitive_torus_add(major_segments=8,minor_segments=4,location=(-.09,0,-.055),major_radius=.045,minor_radius=.006,rotation=(math.pi/2,0,0));g=bpy.context.object;g.name='Trigger_Guard';g.data.materials.append(steel);objs.append(g)
 objs += [box('Front_Trigger',(-.075,-.008,-.052),(.012,.012,.045),brass,.003),box('Rear_Trigger',(-.105,.008,-.052),(.012,.012,.038),brass,.003),box('Front_Sight',(.59,0,.085),(.016,.016,.020),brass,.002)]
 # collision kept in blend only, excluded export
 lo,hi,c=bounds(objs); coll=box('COLLISION_SHOTGUN',c,hi-lo,dark);coll.hide_render=True;coll.hide_viewport=True;coll['collision_proxy']=True
 # previews
 bpy.ops.object.light_add(type='AREA',location=(-1,-1,1));bpy.context.object.data.energy=700;bpy.context.object.data.size=3
 bpy.ops.object.light_add(type='AREA',location=(1,-.5,.7));bpy.context.object.data.energy=350;bpy.context.object.data.size=2
 bpy.ops.object.camera_add();cam=bpy.context.object;cam.data.type='ORTHO';bpy.context.scene.camera=cam
 scene=bpy.context.scene;scene.render.engine='BLENDER_EEVEE';scene.render.resolution_x=1200;scene.render.resolution_y=700;scene.render.resolution_percentage=100;scene.render.image_settings.file_format='PNG';scene.world.color=(.015,.018,.022)
 loc=c+Vector((-.35,-2.0,.48));cam.location=loc;cam.rotation_euler=(c-loc).to_track_quat('-Z','Y').to_euler();cam.data.ortho_scale=(hi.x-lo.x)*1.16;scene.render.filepath=str(out/(ASSET+'_hero.png'));bpy.ops.render.render(write_still=True)
 loc=c+Vector((0,-2.2,.03));cam.location=loc;cam.rotation_euler=(c-loc).to_track_quat('-Z','Y').to_euler();scene.render.filepath=str(out/(ASSET+'_side.png'));bpy.ops.render.render(write_still=True)
 # save and export hero only
 bpy.ops.wm.save_as_mainfile(filepath=str(out/(ASSET+'.blend')));bpy.ops.object.select_all(action='DESELECT')
 for o in objs:o.select_set(True)
 bpy.ops.export_scene.gltf(filepath=str(out/(ASSET+'.glb')),export_format='GLB',use_selection=True,export_apply=True)
 tri=sum(len(o.data.polygons) for o in objs if o.type=='MESH')
 (out/'manifest.json').write_text(json.dumps({'asset_id':ASSET,'reference_only_sources':True,'original_geometry':True,'original_textures':True,'triangles':tri,'collision_proxy':'COLLISION_SHOTGUN'},indent=2))
 print('ORIGINAL_RESULT',tri)
if __name__=='__main__': main(Path(sys.argv[sys.argv.index('--')+1]).resolve())
