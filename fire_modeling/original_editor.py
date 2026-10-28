"""Run the supplied original Mantaflow script unchanged, publish native artifacts."""
import importlib,subprocess,time
from pathlib import Path
import numpy as np
from PIL import Image,ImageEnhance,ImageFilter
from .editor_contract import upstream,resolved_scene
from .io import write_json,read_json,sha256,new_directory
from .quality import inspect_run


def run_original(config,root,generation,blender='blender'):
    p=upstream();module=importlib.import_module('firephantom.physics.blender_scene')
    scene,spec=resolved_scene(config.editor_scene);out=new_directory(root/'render')
    (out/'images').mkdir();(out/'masks').mkdir();video=root/'video';video.mkdir()
    views=generation['viewpoints'];weathers=generation['weathers'];frames=generation['frame_count']
    manifest={'schema_version':1,'status':'running','config':config.to_dict(),'samples':[],'stages':[]}
    write_json(out/'config.json',config.to_dict());write_json(out/'manifest.json',manifest)
    combos=[];videos=[];start=time.monotonic()
    try:
        preview=p.layout_preview(scene['scenario'],scene['placements'],scene['origin_fuel'],origin=scene['origin'],cameras=scene['cameras'],gas_domain_override=scene['gas_domain'],viewpoints=views,lights=scene['lights'],simulation=scene['simulation'],structures=scene['structures'],domain=scene['domain'],frame_count=frames)
        for repeat in range(generation['count']):
            raw=root/f'original-{repeat}';raw.mkdir()
            layout=p.prepare(spec,scene['placements'],scene['origin_fuel'],preview['gas_domain'])
            script=module.render_blender(spec,generation['wind_speed']+repeat*generation['wind_step'],generation['temperature'],generation['humidity'],scene['origin_fuel'],render_output=str((raw/'frames').resolve()),layout=layout,viewpoints=views,looks=[(preview['environment'],w) for w in weathers],frame_count=frames,seed=(config.seed if generation['seed'] is None else generation['seed'])+repeat,camera_overrides=scene['cameras'],lights=preview['lights'],simulation=scene['simulation'])
            (raw/'scene.py').write_text(script,encoding='utf-8')
            write_json(root/'editor-progress.json',{'phase':'mantaflow','repeat':repeat+1,'repeats':generation['count'],'total_frames':len(views)*len(weathers)*frames*generation['count'],'started':time.time()})
            subprocess.run([blender,'--background','--factory-startup','--python',str(raw/'scene.py')],check=True,timeout=1200)
            for wi,weather in enumerate(weathers):
                for vi,view in enumerate(views):
                    index=len(combos);ids=[];timeline=[]
                    for f in range(frames):
                        stem=f'v{vi}_l{wi}_f{f:03d}';image_file=raw/'frames/rgb'/f'{stem}.png'
                        mask_files=list((raw/'frames/mask').glob(stem+'_flame_*.png'))
                        if not image_file.is_file() or not mask_files:raise ValueError('原版渲染缺少帧或火焰掩码，禁止图片回退')
                        with Image.open(image_file) as image,Image.open(mask_files[0]) as mask:
                            image=image.convert('RGB');mask=mask.convert('L').point(lambda v:255 if v>40 else 0)
                            arr=np.array(mask);ys,xs=np.nonzero(arr);boxes=[[int(xs.min()),int(ys.min()),int(xs.max()+1),int(ys.max()+1)]] if len(xs) else []
                            for augmentation in [None]+generation['augmentations']:
                                sid=f'{config.scene_id}_{index:03d}_{f:03d}'+('' if augmentation is None else '_'+str(generation['augmentations'].index(augmentation)))
                                picture=image.copy()
                                if augmentation=='噪声':picture=Image.fromarray(np.uint8(np.clip(np.asarray(picture,dtype=float)+np.random.default_rng(config.seed+f).normal(0,5,np.asarray(picture).shape),0,255)))
                                elif augmentation=='模糊':picture=picture.filter(ImageFilter.GaussianBlur(.8))
                                elif augmentation=='光照变化':picture=ImageEnhance.Brightness(picture).enhance(.8)
                                target=out/'images'/f'{sid}.png';picture.save(target);mask.save(out/'masks'/f'{sid}.png')
                                manifest['samples'].append({'sample_id':sid,'image':f'images/{sid}.png','mask':f'masks/{sid}.png','sha256':sha256(target),'width':image.width,'height':image.height,'source':'classical_photometric' if augmentation else 'original_mantaflow_not_fds','seed':config.seed+repeat,'parent_id':None if augmentation is None else f'{config.scene_id}_{index:03d}_{f:03d}','group_id':f'{config.scene_id}_{repeat}','expected_fire':True,'boxes':boxes,'annotation_status':'pending_review','scene_editor':{'revision':scene['revision'],'viewpoint':view},'combo_index':index,'frame_index':f,'augmentation':augmentation,'weather':weather,'flame_area':float((arr>0).mean()),'auto_screen_pass':float((arr>0).mean())>=generation['min_flame_area']})
                                ids.append(sid)
                                if augmentation is None:timeline.append({'time_s':f/12,'file':str(target.resolve()),'sha256':sha256(target)})
                    output=video/f'camera-{index}.mp4';specification={'width':image.width,'height':image.height,'fps':12,'root':'/','output':str(output.resolve()),'frames':timeline}
                    write_json(video/f'encode-{index}.json',specification)
                    subprocess.run([blender,'--background','--factory-startup','--python',str(Path(__file__).with_name('video_encode.py')),'--',str(video/f'encode-{index}.json')],check=True,timeout=180)
                    videos.append({'file':output.name,'sha256':sha256(output),'viewpoint':view,'weather':weather,'source_frames':frames,'start_s':0,'end_s':(frames-1)/12,'timeline':timeline})
                    combos.append({'index':index,'repeat_index':repeat,'scene':preview['environment'],'weather':weather,'viewpoint':view,'frames':frames,'sample_ids':ids,'video_index':index})
                    write_json(root/'editor-result.json',{'combos':combos})
                    write_json(out/'manifest.json',manifest)
        manifest['status']='success_candidates_only';manifest['stages']=[{'name':'original_mantaflow','status':'success','elapsed_s':round(time.monotonic()-start,2)}]
        write_json(out/'manifest.json',manifest);write_json(out/'quality.json',inspect_run(out,manifest))
        write_json(video/'video.json',{'schema':'ai07.simulation-video.v1','status':'success','config':config.to_dict(),'scene_revision':scene['revision'],'videos':videos,'sampling':'原版Mantaflow逐帧模拟；每个天气独立烘焙；不是FDS三维场'})
    except Exception as exc:
        write_json(out/'manifest.json',{**manifest,'status':'failed','error':str(exc)});raise

