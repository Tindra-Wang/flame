"""Execute with Blender --background --python ... -- job.json (not host Python).

Mantaflow supplies visual flames; HRR controls fuel rate through a documented
heuristic. FDS temperature/velocity grids are NOT reconstructed by this script.
"""
import json
import math
from pathlib import Path
import sys


def main(job_path):
    import bpy
    from mathutils import Vector
    job=json.loads(Path(job_path).read_text(encoding="utf-8"))
    c=job["config"]; out=Path(job["output"]); out.mkdir(parents=True,exist_ok=True)
    if bpy.app.version < (3,6,0):
        raise RuntimeError("Use Blender 3.6 or newer; record and freeze the version after validation")
    bpy.ops.object.select_all(action="SELECT"); bpy.ops.object.delete(use_global=False)
    scene=bpy.context.scene
    scene.render.engine="CYCLES"; scene.cycles.device="CPU"; scene.cycles.samples=16
    scene.cycles.seed=job["seed"]
    scene.render.resolution_x=c["width"]; scene.render.resolution_y=c["height"]; scene.render.resolution_percentage=100
    scene.render.image_settings.file_format="PNG"
    scene.world.use_nodes=True
    world=scene.world.node_tree.nodes.get("Background")
    world.inputs["Color"].default_value=(.25,.3,.4,1); world.inputs["Strength"].default_value=.3
    material=bpy.data.materials.new("surface"); material.diffuse_color=(.25,.25,.25,1); material.use_nodes=True
    surface_shader=material.node_tree.nodes.get("Principled BSDF")
    surface_shader.inputs["Base Color"].default_value=(.25,.23,.2,1)

    def cube(name,location,dimensions,effector=False):
        bpy.ops.mesh.primitive_cube_add(size=1,location=location)
        obj=bpy.context.object; obj.name=name; obj.dimensions=dimensions
        bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
        obj.data.materials.append(material)
        if effector:
            mod=obj.modifiers.new("collision","FLUID"); mod.fluid_type="EFFECTOR"
        return obj

    lx,ly,lz=c["room_size_m"]; x,y=c["fire_center_m"]; fw,fd=c["fire_size_m"]
    cube("floor",(lx/2,ly/2,-.06),(lx,ly,.1),True)
    if c["scene_type"]=="indoor":
        cube("left",(-.06,ly/2,lz/2),(.1,ly,lz),True)
        cube("right",(lx+.06,ly/2,lz/2),(.1,ly,lz),True)
        cube("back",(lx/2,ly+.06,lz/2),(lx,.1,lz),True)
        cube("ceiling",(lx/2,ly/2,lz+.06),(lx,ly,.1),True)
        half=max(1,round(.4/c["cell_size_m"]))*c["cell_size_m"]
        center=round(lx/2/c["cell_size_m"])*c["cell_size_m"]
        door_h=round(2/c["cell_size_m"])*c["cell_size_m"]
        for a,b in [(0,center-half),(center+half,lx)]:
            cube("front",((a+b)/2,-.06,lz/2),(b-a,.1,lz),True)
        cube("door_lintel",(center,-.06,(door_h+lz)/2),(2*half,.1,lz-door_h),True)
    else:
        for ox,oy in [(.5,3.2),(3.4,3.3),(.7,1.2)]:
            cube("outdoor_obstacle",(ox,oy,.35),(.35,.35,.7),True)

    flame=cube("fire_emitter",(x,y,.12),(fw,fd,.2))
    flow=flame.modifiers.new("fire_flow","FLUID"); flow.fluid_type="FLOW"
    bpy.context.view_layer.update()
    flow.flow_settings.flow_type="BOTH"; flow.flow_settings.flow_behavior="INFLOW"
    flow.flow_settings.fuel_amount=min(3,max(.1,job["strength"])) if job["positive"] else 0
    flame.hide_render=True
    domain=cube("gas_domain",(lx/2,ly/2,lz/2),(lx,ly,lz))
    dm=domain.modifiers.new("gas","FLUID"); dm.fluid_type="DOMAIN"
    bpy.context.view_layer.update()
    settings=dm.domain_settings; settings.domain_type="GAS"; settings.resolution_max=32
    settings.cache_type="ALL"; settings.cache_frame_start=1; settings.cache_frame_end=24
    settings.cache_directory=str(out/"fluid_cache"); settings.use_noise=False
    domain.data.materials.clear()
    volume=bpy.data.materials.new("flame_volume"); volume.use_nodes=True
    nodes=volume.node_tree.nodes; nodes.clear(); links=volume.node_tree.links
    output=nodes.new("ShaderNodeOutputMaterial"); shader=nodes.new("ShaderNodeVolumePrincipled")
    density=nodes.new("ShaderNodeAttribute"); density.attribute_name="density"
    fire=nodes.new("ShaderNodeAttribute"); fire.attribute_name="flame"
    gain=nodes.new("ShaderNodeMath"); gain.operation="MULTIPLY"; gain.inputs[1].default_value=5
    links.new(density.outputs["Fac"],shader.inputs["Density"])
    links.new(fire.outputs["Fac"],gain.inputs[0]); links.new(gain.outputs[0],shader.inputs["Emission Strength"])
    shader.inputs["Emission Color"].default_value=(1,.22,.01,1)
    shader.inputs["Color"].default_value=(.15,.15,.15,1)
    links.new(shader.outputs["Volume"],output.inputs["Volume"]); domain.data.materials.append(volume)
    if c["scene_type"]=="outdoor" and c["wind_m_s"]:
        bpy.ops.object.effector_add(type="WIND",location=(0,ly/2,1),rotation=(0,math.copysign(math.pi/2,c["wind_m_s"]),0))
        bpy.context.object.field.strength=abs(c["wind_m_s"])

    target=Vector((x,y,.75)); a=math.radians(job["angle"])
    radius=.4*min(lx,ly)
    bpy.ops.object.camera_add(location=target+Vector((radius*math.cos(a),-radius*math.sin(a),.8)))
    cam=bpy.context.object; cam.rotation_euler=(target-cam.location).to_track_quat("-Z","Y").to_euler(); cam.data.lens=32; scene.camera=cam
    bpy.ops.object.light_add(type="AREA",location=(lx/2,ly/2,lz-.2))
    light=bpy.context.object; light.data.energy=350; light.data.shape="DISK"; light.data.size=3
    scene.frame_start=1; scene.frame_end=24
    if job["positive"]:
        bpy.ops.object.select_all(action="DESELECT"); domain.select_set(True); bpy.context.view_layer.objects.active=domain
        result=bpy.ops.fluid.bake_all()
        if "FINISHED" not in result: raise RuntimeError("Fluid baking did not finish")
    else:
        domain.hide_render=True
    scene.frame_set(24)
    bpy.ops.wm.save_as_mainfile(filepath=str(out/"scene.blend"))
    scene.render.filepath=str(out/"rgb.png"); bpy.ops.render.render(write_still=True)
    # A flame-emission pass is only a candidate mask, never approved ground truth.
    light.hide_render=True; world.inputs["Strength"].default_value=0
    surface_shader.inputs["Base Color"].default_value=(0,0,0,1)
    shader.inputs["Emission Color"].default_value=(1,1,1,1)
    scene.view_settings.view_transform="Standard"
    scene.render.filepath=str(out/"mask.png"); bpy.ops.render.render(write_still=True)
    if job["weather"]=="fog":
        # Visual fog is applied in a compositor, not passed off as FDS humidity.
        scene.use_nodes=True; nt=scene.node_tree; nt.nodes.clear()
        layers=nt.nodes.new("CompositorNodeRLayers"); mix=nt.nodes.new("CompositorNodeMixRGB"); mix.blend_type="MIX"
        mix.inputs[0].default_value=.2; mix.inputs[2].default_value=(.65,.68,.7,1)
        comp=nt.nodes.new("CompositorNodeComposite"); nt.links.new(layers.outputs["Image"],mix.inputs[1]); nt.links.new(mix.outputs[0],comp.inputs[0])
        # Restore RGB materials before rendering the fogged RGB image.
        light.hide_render=False; world.inputs["Strength"].default_value=.3
        surface_shader.inputs["Base Color"].default_value=(.25,.23,.2,1); shader.inputs["Emission Color"].default_value=(1,.22,.01,1)
        scene.render.filepath=str(out/"rgb.png"); bpy.ops.render.render(write_still=True)
    (out/"render.json").write_text(json.dumps({"blender_version":bpy.app.version_string,"route":"mantaflow_visual_proxy","mask":"flame_emission_candidate_requires_review","frames":24,"resolution":32}),encoding="utf-8")


if __name__=="__main__":
    main(sys.argv[sys.argv.index("--")+1])
