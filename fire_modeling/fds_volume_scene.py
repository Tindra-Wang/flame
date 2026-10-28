"""Blender-side FDS/OpenVDB renderer; no second CFD or procedural fallback.

Adapts the volume/blackbody/camera separation used by the provided FirePhantom
physics/blender_scene.py. Independent main-platform file contract, no upstream DB.
"""
import json
import hashlib
import math
from pathlib import Path
import sys


def main(job_path):
    import bpy
    import numpy as np
    import openvdb as vdb
    from mathutils import Vector
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

    job=json.loads(Path(job_path).read_text(encoding='utf-8'))
    from fire_modeling.synthesis_contracts import RenderProfile,BASELINE
    profile=RenderProfile.parse(job.get('profile') or BASELINE).to_dict()
    c=job['config']; out=Path(job['output']); out.mkdir(parents=True,exist_ok=True)
    with np.load(job['volume'],allow_pickle=False) as data:
        axes=[np.array(data[k+'_m']) for k in ('x','y','z')]
        temperature=np.array(data['temperature_c'],dtype=np.float32)
        soot=np.array(data['soot_kg_m3'],dtype=np.float32)
        hrr=np.array(data['hrrpuv_kw_m3'],dtype=np.float32)
    shape=tuple(len(a) for a in axes)
    if temperature.shape!=shape or soot.shape!=shape or hrr.shape!=shape or np.prod(shape)>160000:
        raise ValueError('Invalid FDS volume dimensions')
    if not all(np.isfinite(a).all() for a in (temperature,soot,hrr,*axes)):
        raise ValueError('Nonfinite FDS volume')
    # FDS slices fill obstruction cells with ambient bulk density (~1.16 kg/m3) as a
    # placeholder, not soot. Rendering it as smoke turns every structure into an
    # opaque black block (the whole-frame black root cause when the camera is close).
    obstruction_fill=soot>0.05
    filled_cells=int(obstruction_fill.sum())
    soot=np.where(obstruction_fill,np.float32(0),soot)
    hrr_peak=float(np.max(hrr))
    soot_peak=float(np.max(soot))
    hrr_norm=np.clip(hrr/hrr_peak,0,1) if hrr_peak>1e-9 else np.zeros_like(hrr)
    soot_norm=np.clip(soot/soot_peak,0,1) if soot_peak>1e-9 else np.zeros_like(soot)
    # Blender multiplies volume emission by density, and this propane fire carries almost
    # no soot (~1e-6 kg/m3), so a soot-only medium renders the flame invisible.
    # Bake a display medium (flame + smoke) for the emission to ride on; the NPZ keeps
    # the lossless physical fields.
    display_density=np.clip(soot_norm*.12+hrr_norm*.6,0,1).astype(np.float32)
    step=float(axes[0][1]-axes[0][0])
    if step<=0 or any(not np.allclose(np.diff(a),step,rtol=1e-4,atol=1e-6) for a in axes):
        raise ValueError('Nonuniform FDS volume transform')
    # Cache independent of camera/weather; only the optical transfer is scaled.
    cache=Path(job['volume']).with_suffix('.vdb')
    cache_record=cache.with_suffix('.vdb.json')
    cache_version='display-medium-v2'
    digest=hashlib.sha256(Path(job['volume']).read_bytes()).hexdigest()
    reuse=False
    if cache.exists() and cache_record.exists():
        record=json.loads(cache_record.read_text(encoding='utf-8'))
        reuse=record.get('cache_version')==cache_version and record.get('source_sha256')==digest and record.get('vdb_sha256')==hashlib.sha256(cache.read_bytes()).hexdigest()
    if not reuse:
        grids=[]
        for name,array in [('density',display_density),('temperature',np.maximum(temperature+273.15,0)),('hrrpuv',np.maximum(hrr,0))]:
            grid=vdb.FloatGrid(); grid.name=name
            grid.transform=vdb.createLinearTransform(voxelSize=step)
            grid.transform.preTranslate(tuple(float(a[0]) for a in axes))
            if not np.allclose(grid.transform.indexToWorld((0,0,0)),[a[0] for a in axes]):
                raise ValueError('OpenVDB world origin mismatch')
            grid.copyFromArray(np.ascontiguousarray(array))
            grids.append(grid)
        temporary=cache.with_suffix('.tmp.vdb'); vdb.write(str(temporary),grids=grids); temporary.replace(cache)
        cache_record.write_text(json.dumps({'cache_version':cache_version,'source_sha256':digest,'vdb_sha256':hashlib.sha256(cache.read_bytes()).hexdigest()}),encoding='utf-8')
    bpy.ops.object.select_all(action='SELECT'); bpy.ops.object.delete(use_global=False)
    scene=bpy.context.scene; scene.render.engine='CYCLES'; scene.cycles.device='CPU'
    scene.cycles.samples=c.get('render_samples',48); scene.cycles.seed=job['seed']
    scene.cycles.use_denoising=True; scene.cycles.volume_bounces=2
    scene.render.resolution_x=c['width']; scene.render.resolution_y=c['height']; scene.render.resolution_percentage=100
    scene.render.image_settings.file_format='PNG'
    scene.view_settings.view_transform='AgX'
    scene.view_settings.exposure=profile['exposure']
    scene.world.use_nodes=True; background=scene.world.node_tree.nodes.get('Background')
    background.inputs['Color'].default_value=(.16,.2,.25,1); background.inputs['Strength'].default_value=.35
    surface=bpy.data.materials.new('neutral_surfaces'); surface.use_nodes=True
    bsdf=surface.node_tree.nodes.get('Principled BSDF'); bsdf.inputs['Base Color'].default_value=(.16,.18,.18,1)
    bsdf.inputs['Roughness'].default_value=.82

    def cube(name,location,dimensions):
        bpy.ops.mesh.primitive_cube_add(size=1,location=location)
        obj=bpy.context.object; obj.name=name; obj.dimensions=dimensions
        obj.data.materials.append(surface)
        return obj

    lx,ly,lz=c['room_size_m']; x,y=c['fire_center_m']; fw,fd=c['fire_size_m']
    cube('floor',(lx/2,ly/2,-.06),(lx,ly,.1))
    editor=c.get('editor_scene')
    resolved=None;custom_lights=[];solids=[]
    if editor:
        from fire_modeling.editor_contract import resolved_scene,upstream
        editor,spec=resolved_scene(editor);p=upstream()
        resolved=p.layout_preview(editor['scenario'],editor['placements'],editor['origin_fuel'],origin=editor['origin'],
            cameras=editor['cameras'],gas_domain_override=editor['gas_domain'],viewpoints=editor['viewpoints'],
            lights=editor['lights'],simulation=editor['simulation'],structures=editor['structures'],domain=editor['domain'],frame_count=1)
        for box in spec.obstacles:
            a=box.xb
            solids.append((box.name,[a[0],a[2],a[4]],[a[1],a[3],a[5]]))
            cube(box.name,((a[0]+a[1])/2,(a[2]+a[3])/2,(a[4]+a[5])/2),(a[1]-a[0],a[3]-a[2],a[5]-a[4]))
        packages=p.normalize_placements(spec,editor['placements'],editor['origin_fuel'])
        for index,item in enumerate(packages):
            solids.append((f'object_{index}',[item['center'][k]-item['size'][k]/2 for k in range(3)],[item['center'][k]+item['size'][k]/2 for k in range(3)]))
            path=Path(item['asset_path']) if item['asset_path'] else None
            if path and path.is_file():
                before=set(bpy.data.objects);bpy.ops.import_scene.gltf(filepath=str(path));objects=set(bpy.data.objects)-before
                meshes=[o for o in objects if o.type=='MESH']
                if not meshes:raise ValueError('模型没有可渲染网格')
                points=[o.matrix_world@Vector(corner) for o in meshes for corner in o.bound_box]
                lo=Vector(tuple(min(v[k] for v in points) for k in range(3)));hi=Vector(tuple(max(v[k] for v in points) for k in range(3)))
                group=bpy.data.objects.new(f'model_{index}',None);scene.collection.objects.link(group)
                for obj in objects:
                    if obj.parent not in objects:obj.parent=group
                group.scale=tuple(item['size'][k]/max(hi[k]-lo[k],1e-6) for k in range(3))
                # Translate the fitted model to the same saved centre used by FDS.
                for obj in objects:
                    if obj.parent==group:obj.location-=((lo+hi)/2)
                group.location=item['center'];group.rotation_euler[2]=item['yaw']
            else:
                obj=cube(f'fuel_box_{index}',item['center'],item['size']);obj.rotation_euler[2]=item['yaw']
        custom_lights=resolved['lights']
    elif c['scene_type']=='indoor':
        cube('left_wall',(-.06,ly/2,lz/2),(.1,ly,lz))
        cube('back_wall',(lx/2,ly+.06,lz/2),(lx,.1,lz))
        # Front and right cutaway are intentionally hidden from the observation camera.
    cube('burner',(x,y,-.01),(fw,fd,.03))
    bpy.ops.object.volume_import(filepath=str(cache))
    volume=bpy.context.object; volume.name='FDS_physical_volume'; volume.hide_render=not job['positive']
    mat=bpy.data.materials.new('FDS_optical_transfer'); mat.use_nodes=True
    nodes=mat.node_tree.nodes; nodes.clear(); links=mat.node_tree.links
    output=nodes.new('ShaderNodeOutputMaterial'); shader=nodes.new('ShaderNodeVolumePrincipled')
    shader.inputs['Color'].default_value=(.12,.12,.13,1)
    def attribute(name):
        n=nodes.new('ShaderNodeAttribute'); n.attribute_name=name; return n.outputs['Fac']
    def multiply(source,value):
        n=nodes.new('ShaderNodeMath'); n.operation='MULTIPLY'; n.inputs[1].default_value=value
        links.new(source,n.inputs[0]); return n.outputs[0]
    # Visibility transfer normalized per frame: a 100 kW fire spread over structure
    # surfaces peaks at a few kW/m3 and would be invisible under a fixed absolute gain.
    # This is a display mapping, not a radiometric calibration (disclosed in the report).
    density_gain=1.0
    emission_gain=1.5/hrr_peak if hrr_peak>1e-9 else 0.0
    emission_cutoff=.02*hrr_peak
    ramp_gain=1.0/max(hrr_peak-emission_cutoff,1e-9)
    links.new(multiply(attribute('density'),density_gain),shader.inputs['Density'])
    cutoff=nodes.new('ShaderNodeMath'); cutoff.operation='SUBTRACT'; cutoff.inputs[1].default_value=emission_cutoff
    links.new(attribute('hrrpuv'),cutoff.inputs[0])
    positive=nodes.new('ShaderNodeMath'); positive.operation='MAXIMUM'; positive.inputs[1].default_value=0
    links.new(cutoff.outputs[0],positive.inputs[0])
    links.new(multiply(positive.outputs[0],emission_gain),shader.inputs['Emission Strength'])
    if profile['color_mode']=='blackbody':
        blackbody=nodes.new('ShaderNodeBlackbody'); links.new(attribute('temperature'),blackbody.inputs['Temperature'])
        links.new(blackbody.outputs['Color'],shader.inputs['Emission Color'])
    else:
        ramp=nodes.new('ShaderNodeValToRGB');ramp.color_ramp.elements[0].color=(1,.03,.001,1);ramp.color_ramp.elements[1].color=(1,.5,.05,1)
        links.new(multiply(positive.outputs[0],ramp_gain),ramp.inputs['Fac']);links.new(ramp.outputs['Color'],shader.inputs['Emission Color'])
    links.new(shader.outputs['Volume'],output.inputs['Volume']); volume.data.materials.append(mat)
    target=Vector((x,y,.9)); a=math.radians(job['angle']); radius=.52*min(lx,ly)
    pose=resolved['cameras'].get(job.get('viewpoint')) if resolved else None
    if pose:target=Vector(pose['target'])
    camera_pushed=False
    if pose and solids:
        # 相机落在结构/物件实体内时（原样渲染只能看到内壁或贴脸黑块），
        # 退到该实体外侧一个完整取景距离，而不是贴在外壁上。
        loc=Vector(tuple(pose['location']))
        def _contains(p,box):
            _n,lo,hi=box
            return all(lo[k]-.05<=p[k]<=hi[k]+.05 for k in range(3))
        def _inside(p):
            return any(_contains(p,b) for b in solids)
        if _inside(loc):
            containing=[b for b in solids if _contains(loc,b)]
            lo=Vector(tuple(min(b[1][k] for b in containing) for k in range(3)))
            hi=Vector(tuple(max(b[2][k] for b in containing) for k in range(3)))
            center=(lo+hi)/2;span=max(hi-lo)
            direction=loc-center
            if direction.length<1e-6:direction=Vector((1.,-1.,.35))
            direction.normalize()
            standoff=max(5.0,2.6*span)
            angle=math.atan2(direction.y,direction.x);placed=center+direction*standoff;turned=0
            while _inside(placed) and turned<12:
                turned+=1;theta=angle+math.radians(30*turned)
                q=Vector((math.cos(theta),math.sin(theta),direction.z))
                if q.length<1e-6:q=Vector((1.,-1.,.35))
                q.normalize();placed=center+q*standoff
            placed.x=max(.3,min(lx-.3,placed.x));placed.y=max(.3,min(ly-.3,placed.y));placed.z=max(.3,min(lz-.3,placed.z))
            pose={**pose,'saved_target':pose.get('target'),
                  'target':[round(center.x,4),round(center.y,4),round(center.z,4)],
                  'location':[round(placed.x,4),round(placed.y,4),round(placed.z,4)],
                  'inside_solid':True,'camera_pushed_out':True,
                  'camera_standoff_m':round(standoff,3),'camera_turn_steps':turned}
            camera_pushed=True
    bpy.ops.object.camera_add(location=pose['location'] if pose else target+Vector((radius*math.cos(a),-radius*math.sin(a),.65)))
    camera=bpy.context.object; camera.rotation_euler=(target-camera.location).to_track_quat('-Z','Y').to_euler()
    camera.data.lens=pose['focal_mm'] if pose else 34; scene.camera=camera
    bpy.ops.object.light_add(type='AREA',location=(lx/2,ly/2,lz-.1))
    light=bpy.context.object; light.data.energy=450; light.data.size=3
    presentation_fill=not resolved or not any(item['enabled'] for item in custom_lights)
    light.hide_render=not presentation_fill
    if resolved:
        for item in custom_lights:
            bpy.ops.object.light_add(type=item['type'],location=item['location'],rotation=item['rotation'])
            obj=bpy.context.object;obj.data.color=item['color'];obj.data.energy=item['energy'];obj.hide_render=not item['enabled']
            if item['type']=='AREA':obj.data.size=item['size']
    if job['weather']=='fog':
        # Presentation condition only: recorded separately from FDS boundary/weather.
        fog=cube('visual_fog',(lx/2,ly/2,lz/2),(lx,ly,lz)); fog.data.materials.clear()
        fogmat=bpy.data.materials.new('visual_fog'); fogmat.use_nodes=True
        fn=fogmat.node_tree.nodes; fn.clear(); fs=fn.new('ShaderNodeVolumePrincipled'); fs.inputs['Density'].default_value=.055
        fo=fn.new('ShaderNodeOutputMaterial'); fogmat.node_tree.links.new(fs.outputs['Volume'],fo.inputs['Volume']); fog.data.materials.append(fogmat)
    else: fog=None
    if job['weather'] in {'rain','snow'}:
        rng=np.random.default_rng(job['seed']);particlemat=bpy.data.materials.new('visual_precipitation');particlemat.diffuse_color=(.75,.85,.95,1)
        for i in range(80):
            loc=(float(rng.uniform(0,lx)),float(rng.uniform(0,ly)),float(rng.uniform(.2,lz)))
            if job['weather']=='snow':bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=1,radius=.035,location=loc)
            else:bpy.ops.mesh.primitive_cylinder_add(vertices=4,radius=.004,depth=.22,location=loc)
            bpy.context.object.name='visual_precipitation';bpy.context.object.data.materials.append(particlemat)
    if job.get('controls'):
        scene.view_layers[0].use_pass_z=True;scene.use_nodes=True
        nt=scene.node_tree;nt.nodes.clear();rl=nt.nodes.new('CompositorNodeRLayers');comp=nt.nodes.new('CompositorNodeComposite');nt.links.new(rl.outputs['Image'],comp.inputs[0])
        normal=nt.nodes.new('CompositorNodeMapRange');normal.inputs['From Max'].default_value=math.sqrt(lx*lx+ly*ly+lz*lz);normal.inputs['To Min'].default_value=1;normal.inputs['To Max'].default_value=0;normal.use_clamp=True;nt.links.new(rl.outputs['Depth'],normal.inputs['Value'])
        depthout=nt.nodes.new('CompositorNodeOutputFile');depthout.base_path=str(out);depthout.file_slots[0].path='depth';depthout.format.file_format='PNG';depthout.format.color_mode='BW';depthout.format.color_depth='8';nt.links.new(normal.outputs['Value'],depthout.inputs[0])
        rawdepth=nt.nodes.new('CompositorNodeOutputFile');rawdepth.base_path=str(out);rawdepth.file_slots[0].path='depth_m';rawdepth.format.file_format='OPEN_EXR';rawdepth.format.color_depth='32';nt.links.new(rl.outputs['Depth'],rawdepth.inputs[0])
    bpy.ops.wm.save_as_mainfile(filepath=str(out/'scene.blend'))
    scene.render.filepath=str(out/'rgb.png'); bpy.ops.render.render(write_still=True)
    if job.get('controls'):
        (out/'depth0001.png').replace(out/'depth.png');(out/'depth_m0001.exr').replace(out/'depth_m.exr');scene.use_nodes=False
    # Emission-only pass gives a candidate silhouette; not an independently validated label.
    light.hide_render=True; background.inputs['Strength'].default_value=0
    for obj in scene.objects:
        if obj.type=='LIGHT':obj.hide_render=True
    bsdf.inputs['Base Color'].default_value=(0,0,0,1)
    if fog: fog.hide_render=True
    for link in list(shader.inputs['Emission Color'].links): links.remove(link)
    shader.inputs['Emission Color'].default_value=(1,1,1,1)
    scene.view_settings.view_transform='Standard'; scene.render.filepath=str(out/'mask.png'); bpy.ops.render.render(write_still=True)
    report={'blender_version':bpy.app.version_string,'route':'fds_openvdb_volume','physical_backend':'FDS',
            'volume_file':str(Path(job['volume']).name),'vdb_file':cache.name,'shape':shape,
            'output_size':[c['width'],c['height']],'samples':scene.cycles.samples,
            'editor_scene_revision':editor['revision'] if editor else None,'saved_camera':pose,
            'saved_models':len(editor['placements']) if editor else 0,'saved_lights':len(custom_lights),
            'optical_transfer':profile,
            'display_transfer':{'mode':'frame_peak_v2','hrrpuv_peak_kw_m3':round(hrr_peak,6),
                                'hrrpuv_display_gain':round(emission_gain,6),'hrrpuv_relative_cutoff':.02,
                                'soot_peak_kg_m3':round(soot_peak,9),'soot_display_density_peak':.12,
                                'flame_display_density_peak':.6,'obstruction_fill_cells':filled_cells},
            'presentation_fill_light':presentation_fill,
            'controls':{'depth':'depth.png','depth_m':'depth_m.exr'} if job.get('controls') else {},
            'mask':'emission_candidate_requires_review','scene_presentation':'indoor_cutaway' if c['scene_type']=='indoor' else 'outdoor',
            'limitation':'Display transfer is normalized per frame (visibility only, not radiometric calibration); obstruction-filled soot placeholders are masked; no added CFD detail or measured realism claim.'}
    (out/'render.json').write_text(json.dumps(report,ensure_ascii=False),encoding='utf-8')


if __name__=='__main__': main(sys.argv[sys.argv.index('--')+1])

