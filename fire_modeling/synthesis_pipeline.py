"""Synthesis stage executors; all cross-stage state is versioned files."""
from pathlib import Path
import copy,shutil
import numpy as np
from PIL import Image
from .io import read_json,write_json,sha256,resolve_artifact
from .config import SceneConfig
from .adapters import RenderRequest,create_renderer
from .annotations import boxes_from_mask
from .quality import inspect_run
from .synthesis_contracts import fingerprint,BASELINE


def verify_source(jobs,source):
    root=resolve_artifact(jobs,source['id']+'/physics');handoff=read_json(root/'handoff.json')
    volume=root/'volume/volume.json'
    if sha256(volume)!=source['volume_manifest_sha256'] or handoff['volume_sha256']!=sha256(volume):raise ValueError('源三维场清单校验失败')
    if SceneConfig.from_dict(handoff['config'])!=SceneConfig.from_dict(source['config']):raise ValueError('源场景配置不一致')
    if sha256(resolve_artifact(root,handoff['hrr_csv']))!=handoff['sha256']:raise ValueError('源HRR校验失败')
    from .editor_contract import resolved_scene,upstream
    editor=read_json(resolve_artifact(root,handoff['editor_manifest']))
    if sha256(root/handoff['editor_manifest'])!=handoff['editor_sha256']:raise ValueError('源场景交接被修改')
    scene,spec=resolved_scene(source['config']['editor_scene'])
    actual=upstream().normalize_placements(spec,scene['placements'],scene['origin_fuel'])
    for model,entry in zip(actual,editor['models'],strict=True):
        digest=sha256(Path(model['asset_path'])) if model['asset_path'] else None
        if model['asset_id']!=entry['asset_id'] or digest!=entry['sha256']:raise ValueError('场景模型在求解后发生变化')
    return root


def render_plan(root,plan,renderer=None):
    out=root/'render';out.mkdir(exist_ok=True)
    for name in ('images','masks','controls'): (out/name).mkdir(exist_ok=True)
    manifest={'schema_version':1,'status':'running','config':plan['sources'][0]['config'],'samples':[],
              'plan_hash':fingerprint(plan),'stages':[],'comparisons':[],'physics':'fds_reused','renderer':'blender','source_cases':[{k:s[k] for k in ('id','scene_id','scene_revision','config','volume_manifest_sha256')} for s in plan['sources']]}
    sources={s['id']:s for s in plan['sources']};locations={id:verify_source(root.parent,s) for id,s in sources.items()}
    engine=renderer or create_renderer('blender');groups={};profile=plan['options']['profile']
    implementation=sha256(Path(__file__).with_name('fds_volume_scene.py'))
    try:
        for index,item in enumerate(plan['items']):
            s=sources[item['source_id']]
            # Camera selection is a render concern; it does not change the source physics snapshot.
            config=SceneConfig.from_dict({**s['config'],'editor_scene':{**s['config']['editor_scene'],'viewpoints':plan['options']['viewpoints']}});field=item['field']
            volume=resolve_artifact(locations[s['id']]/'volume',field['file'])
            if sha256(volume)!=field['sha256']:raise ValueError('源场帧校验失败')
            work=out/'cache'/item['cache_key'];state=work/'state.json'
            signature=fingerprint({'plan':item['cache_key'],'implementation':implementation})
            reusable=False
            if state.is_file():
                saved=read_json(state);reusable=saved.get('signature')==signature and all((work/n).is_file() and sha256(work/n)==h for n,h in saved.get('files',{}).items()) and set(saved.get('files',{}))=={'rgb.png','mask.png','depth.png','depth_m.exr','render.json'}
            if not reusable:
                engine.render(RenderRequest(config,work,config.seed,25,item['weather'],1,True,volume,item['viewpoint'],profile,True))
                files={n:sha256(work/n) for n in ('rgb.png','mask.png','depth.png','depth_m.exr','render.json')}
                write_json(state,{'signature':signature,'files':files})
            sid=item['sample_id'];paths={'image':f'images/{sid}.png','mask':f'masks/{sid}.png','depth':f'controls/{sid}_depth.png','depth_m':f'controls/{sid}_depth.exr'}
            for key,name in [('image','rgb.png'),('mask','mask.png'),('depth','depth.png'),('depth_m','depth_m.exr')]:shutil.copy2(work/name,out/paths[key])
            with Image.open(out/paths['mask']) as mask:boxes=boxes_from_mask(np.asarray(mask.convert('L'))>32)
            group=(s['id'],item['weather'],item['viewpoint']);combo=groups.setdefault(group,len(groups))
            sample={'sample_id':sid,**paths,'sha256':sha256(out/paths['image']),'control_hashes':{k:sha256(out/paths[k]) for k in ('mask','depth','depth_m')},
                'width':config.width,'height':config.height,'boxes':boxes,'source':'fds_openvdb_volume','group_id':s['id'],'parent_id':None,'seed':config.seed,
                'expected_fire':True,'physical_volume':{**field,'backend':'FDS','optical_transfer':'uncalibrated'},'source_simulation_id':s['id'],
                'scene_editor':{'revision':s['scene_revision'],'viewpoint':item['viewpoint'],'camera':read_json(work/'render.json').get('saved_camera')},'weather':item['weather'],'weather_role':'visual_only',
                'combo_index':combo,'frame_index':index,'annotation_status':'pending_review','label_source':'emission_candidate_requires_review','render_profile':profile}
            manifest['samples'].append(sample)
            if index==0:
                baseline=out/'baseline';engine.render(RenderRequest(config,baseline,config.seed,25,item['weather'],1,True,volume,item['viewpoint'],BASELINE,False))
                shutil.copy2(baseline/'rgb.png',out/'images/baseline.png')
                manifest['comparisons'].append({'sample_id':sid,'baseline':'images/baseline.png','current':paths['image'],'same_volume_sha256':field['sha256'],'baseline_profile':BASELINE,'current_profile':profile})
            write_json(out/'manifest.json',manifest)
            write_json(root/'synthesis-progress.json',{'stage':'render','completed':index+1,'total':len(plan['items'])})
            print(f'组合渲染 {index+1}/{len(plan["items"])} · {item["weather"]} · {item["viewpoint"]} · {field["time_s"]:.2f}s',flush=True)
        manifest['status']='success_candidates_only';manifest['stages']=[{'name':'explicit_combination_render','status':'success','count':len(manifest['samples'])}]
        combos=[{'index':i,'scene':sources[source]['scene_id'],'weather':weather,'viewpoint':view} for (source,weather,view),i in groups.items()]
        write_json(root/'editor-result.json',{'combos':combos})
        write_json(out/'quality.json',inspect_run(out,manifest));write_json(out/'manifest.json',manifest)
        return manifest
    except Exception as exc:
        manifest.update(status='failed',error=str(exc));write_json(out/'manifest.json',manifest);raise


def augment_plan(root,plan,engine=None):
    from .controlled_augmentation import InpaintingEnhancer
    from .enhancement import SafetyRejected
    source=root/'render';out=root/'enhanced';out.mkdir(exist_ok=True)
    manifest=copy.deepcopy(read_json(source/'manifest.json'))
    if manifest['status']!='success_candidates_only' or manifest['plan_hash']!=fingerprint(plan):raise ValueError('原图阶段未完成或计划不一致')
    for folder in ('images','masks','controls'):shutil.copytree(source/folder,out/folder,dirs_exist_ok=True)
    options=plan['options'];rejected=[];added=[];done=0;total=plan['counts']['requested_augmented']
    engine=engine or InpaintingEnhancer('/app/models/sd15',controlnet=options['controlnet'])
    cache_signature=fingerprint({'plan':fingerprint(plan),'implementation':sha256(Path(__file__).with_name('controlled_augmentation.py')),
                                 'model':getattr(engine,'model_hashes',None),'controlnet':getattr(engine,'control_hashes',None)})
    try:
        for sample in manifest['samples']:
            for name,key in [('image','sha256'),('mask',None),('depth',None)]:
                expected=sample[key] if key else sample['control_hashes'][name]
                if sha256(resolve_artifact(source,sample[name]))!=expected:raise ValueError('增强输入校验失败')
            with Image.open(source/sample['image']) as im,Image.open(source/sample['mask']) as ma,Image.open(source/sample['depth']) as de:
                image=im.convert('RGB');mask=ma.convert('L');depth=de.copy()
            for mode in options['modes']:
                for variant in range(options['variants']):
                    sid=sample['sample_id']+'_'+mode+'_'+str(variant);seed=int(fingerprint({'id':sid,'plan':fingerprint(plan)})[:8],16)%(2**31)
                    checkpoint=out/'checkpoints'/f'{sid}.json'
                    if checkpoint.is_file():
                        cache=read_json(checkpoint);cached=cache.get('sample',{})
                        if cache.get('signature')==cache_signature and cached.get('parent_id')==sample['sample_id'] and all((out/cached[k]).is_file() for k in ('image','mask')):
                            if sha256(out/cached['image'])==cached['sha256'] and sha256(out/cached['mask'])==cached['control_hashes']['mask']:
                                added.append(cached);done+=1;print(f'复用增强候选 {sid}',flush=True);continue
                    try:
                        result,label,metadata=engine.run(image,mask,depth,mode=mode,seed=seed,weather=sample['weather'],strength=options['strength'],steps=options['steps'])
                    except (ValueError,SafetyRejected) as exc:
                        rejected.append({'sample_id':sid,'parent_id':sample['sample_id'],'reason':str(exc)});write_json(root/'synthesis-progress.json',{'stage':'enhance','accepted':done,'rejected':len(rejected),'total':total});print('增强候选拒绝：'+str(exc),flush=True);continue
                    image_path=f'images/{sid}.png';mask_path=f'masks/{sid}.png';result.save(out/image_path);label.save(out/mask_path)
                    boxes=boxes_from_mask(np.asarray(label)>32)
                    if not boxes:
                        rejected.append({'sample_id':sid,'parent_id':sample['sample_id'],'reason':'没有有效候选框'});continue
                    added.append({**sample,'sample_id':sid,'image':image_path,'mask':mask_path,'sha256':sha256(out/image_path),
                        'control_hashes':{**sample['control_hashes'],'mask':sha256(out/mask_path)},'boxes':boxes,'parent_id':sample['sample_id'],
                        'source':'diffusion','seed':seed,'enhancement':metadata,'augmentation':'背景inpainting' if mode=='background' else '火焰inpainting',
                        'physical_ground_truth':False,'label_source':metadata['checks']['label_policy']})
                    write_json(checkpoint,{'signature':cache_signature,'sample':added[-1]})
                    done+=1;write_json(root/'synthesis-progress.json',{'stage':'enhance','accepted':done,'rejected':len(rejected),'total':total})
                    print(f'受控增强 通过{done} / 拒绝{len(rejected)} / 请求{total}',flush=True)
        manifest['samples']+=added;manifest['rejected_enhancements']=rejected
        manifest['status']='success_candidates_only' if added else 'failed'
        manifest['stages'].append({'name':'controlled_inpainting','status':'partial' if rejected and added else 'success' if added else 'failed','accepted':len(added),'rejected':len(rejected)})
        write_json(out/'manifest.json',manifest);write_json(out/'quality.json',inspect_run(out,manifest))
        if not added:raise RuntimeError('受控增强没有通过候选；原图保留，可查看拒绝原因后重试')
        return manifest
    except Exception as exc:
        manifest.update(status='failed',error=str(exc));write_json(out/'manifest.json',manifest);raise


def validate_synthesis(root,payload):
    plan=payload['plan'];folder='enhanced' if payload['enhance'] else 'render';out=root/folder;m=read_json(out/'manifest.json')
    if fingerprint(plan)!=payload['plan_hash'] or m.get('plan_hash')!=fingerprint(plan) or m.get('status')!='success_candidates_only':raise ValueError('合成未完整完成')
    raw=[s for s in m['samples'] if s['parent_id'] is None]
    if {s['sample_id'] for s in raw}!={i['sample_id'] for i in plan['items']}:raise ValueError('组合覆盖不完整')
    for s in m['samples']:
        if sha256(resolve_artifact(out,s['image']))!=s['sha256']:raise ValueError('图像校验失败')
        for key,h in s['control_hashes'].items():
            if sha256(resolve_artifact(out,s[key]))!=h:raise ValueError('控制图/标签校验失败')
    q=inspect_run(out,m);write_json(out/'quality.json',q)
    return {'raw':len(raw),'augmented':len(m['samples'])-len(raw),'rejected':len(m.get('rejected_enhancements',[])),
            'quality_pass':sum(s['auto_screen_pass'] for s in q['samples']),'requested':plan['counts']}
