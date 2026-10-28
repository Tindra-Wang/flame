"""Create small original GLB meshes for an offline, working scene shelf.

Run inside Blender. These are labelled built-in simplified meshes, not the
missing third-party models named by the provided FirePhantom asset manifest.
"""
from pathlib import Path
import bpy

ROOT=Path('/app/artifacts/scene-assets/library');ROOT.mkdir(parents=True,exist_ok=True)

def block(location,scale,color):
    bpy.ops.mesh.primitive_cube_add(size=1,location=location);o=bpy.context.object;o.scale=scale
    m=bpy.data.materials.new('surface');m.diffuse_color=(*color,1);o.data.materials.append(m)

def sphere(location,scale,color):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=12,ring_count=8,radius=1,location=location);o=bpy.context.object;o.scale=scale
    m=bpy.data.materials.new('surface');m.diffuse_color=(*color,1);o.data.materials.append(m)

for name in ['painted_wooden_sofa','WoodenTable_01','potted_plant_04','wooden_crate_01','boulder_01']:
    if (ROOT/f'{name}.glb').is_file():continue
    bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
    wood=(.34,.17,.065);green=(.13,.29,.09)
    if name=='painted_wooden_sofa':
        block((0,0,.3),(2.2,.9,.3),(.22,.31,.28));block((0,.35,.65),(2.2,.2,.5),(.22,.31,.28))
        for x in [-1,1]:block((x,0,.55),(.2,.9,.5),(.27,.37,.3))
        for x in [-.9,.9]:
            for y in [-.3,.3]:block((x,y,.08),(.1,.1,.16),wood)
    elif name=='WoodenTable_01':
        block((0,0,.7),(1.2,.7,.1),wood)
        for x in [-.5,.5]:
            for y in [-.25,.25]:block((x,y,.34),(.08,.08,.68),wood)
    elif name=='potted_plant_04':
        block((0,0,.13),(.3,.3,.26),(.35,.17,.1));block((0,0,.35),(.06,.06,.4),wood)
        for x,y,z in [(-.15,0,.48),(.15,0,.5),(0,.12,.56),(0,-.12,.5)]:sphere((x,y,z),(.18,.16,.15),green)
    elif name=='boulder_01':sphere((0,0,.3),(.4,.4,.3),(.32,.34,.32))
    else:
        block((0,0,.4),(.8,.8,.8),wood)
        for z in [.12,.4,.68]:block((0,-.41,z),(.8,.025,.04),(.58,.34,.16))
    bpy.ops.export_scene.gltf(filepath=str(ROOT/f'{name}.glb'),export_format='GLB',use_selection=False)
print('Created 5 original simplified GLB assets')
