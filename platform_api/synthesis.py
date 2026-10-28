"""Application boundary for explicit synthesis plans and authorized FDS reuse."""
from fastapi import APIRouter,Depends
from .dependencies import application,current_user,db_session
from .db import Job
from fire_modeling.io import read_json,sha256
from fire_modeling.synthesis_contracts import build_plan,fingerprint
from fastapi import HTTPException
from fastapi.responses import FileResponse
from fire_modeling.io import resolve_artifact

router=APIRouter(prefix='/api/projects/{project}/synthesis')

@router.get('/capabilities')
def capabilities(project:str,user=Depends(current_user),db=Depends(db_session)):
    web=application()
    web.access(db,user,project)
    import os
    return {'inpainting':os.getenv('AI07_GPU_ENABLED')!='0' and (web.ROOT/'models/sd15/model_index.json').is_file(),
            'controlnet_depth':(web.ROOT/'models/controlnet-depth/config.json').is_file(),
            'weathers':['clear','fog','rain','snow'],'weather_role':'visual_only'}


def plan_for(project,data,user,db):
    web=application()
    web.access(db,user,project)
    ids=data.get('source_ids')
    if not isinstance(ids,list) or not 1<=len(ids)<=8:raise ValueError('请选择1至8个已完成的FDS工况')
    sources=[]
    for id in ids:
        job=web.scoped(db,Job,str(id),user)
        if job.project_id!=project:raise ValueError('仿真来源不属于当前项目')
        if job.kind not in {'video','generate'} or job.status!='succeeded' or job.payload.get('route')!='physics':raise ValueError('来源必须为已完成的FDS工况')
        root=web.ROOT/f'artifacts/platform/jobs/{job.id}/physics'
        handoff=read_json(root/'handoff.json');manifest=root/'volume/volume.json'
        if sha256(manifest)!=handoff['volume_sha256']:raise ValueError('源三维场清单已改变')
        if handoff['config']!=job.payload['config']:raise ValueError('源工况与交接配置不一致')
        sources.append({'id':job.id,'scene_id':job.payload['scene_id'],'scene_revision':job.payload['scene_revision'],
                        'config':job.payload['config'],'volume_manifest_sha256':sha256(manifest),'frames':read_json(manifest)['frames']})
    return build_plan(sources,data.get('options',{}))


@router.post('/preview')
def preview(project:str,data:dict,user=Depends(current_user),db=Depends(db_session)):
    web=application()
    p=plan_for(project,data,user,db)
    return {'schema':p['schema'],'counts':p['counts'],'items':[{k:v for k,v in x.items() if k!='field'}|{'time_s':x['field']['time_s']} for x in p['items']],
            'plan_hash':fingerprint(p),'options':p['options'],'weather_role':p['weather_role']}


@router.post('')
def submit(project:str,data:dict,user=Depends(current_user),db=Depends(db_session)):
    web=application()
    web.access(db,user,project,True,web.BUILDERS);p=plan_for(project,data,user,db)
    if data.get('plan_hash')!=fingerprint(p):raise ValueError('组合计划已变化，请重新预览后提交')
    first=p['sources'][0]
    return web.enqueue(db,project,user,{'name':str(data.get('name','多条件受控合成'))[:80],'plan':p,'plan_hash':fingerprint(p),
        'config':first['config'],'scene_id':first['scene_id'],'scene_ids':list(dict.fromkeys(s['scene_id'] for s in p['sources'])),
        'scene_revision':first['scene_revision'],'route':'physics','enhance':bool(p['options']['modes']),
        'pipeline_schema':'synthesis-v1','idempotency_key':data.get('idempotency_key','')},'synthesis')


def result_for(project,id,user,db):
    web=application()
    job=web.scoped(db,Job,id,user)
    if job.project_id!=project or job.kind!='synthesis':raise HTTPException(404,'合成作业不存在')
    root=web.ROOT/f'artifacts/platform/jobs/{id}'
    folder=root/'render'
    if (root/'enhanced/manifest.json').is_file() and read_json(root/'enhanced/manifest.json').get('status')=='success_candidates_only':folder=root/'enhanced'
    manifest=read_json(folder/'manifest.json') if (folder/'manifest.json').is_file() else {'samples':[]}
    return job,root,folder,manifest


@router.get('/jobs/{id}/result')
def result(project:str,id:str,user=Depends(current_user),db=Depends(db_session)):
    web=application()
    job,root,folder,m=result_for(project,id,user,db)
    url=f'/api/projects/{project}/synthesis/jobs/{id}/files/'
    raw={s['sample_id']:s for s in m['samples'] if s.get('parent_id') is None}
    quality=read_json(folder/'quality.json') if (folder/'quality.json').is_file() else {'samples':[]}
    q={s['sample_id']:s for s in quality['samples']}
    rejected=m.get('rejected_enhancements',[])
    failed=root/'enhanced/manifest.json'
    if failed.is_file() and job.status=='failed':rejected=read_json(failed).get('rejected_enhancements',[])
    return {'id':id,'status':job.status,'stage':job.stage,'error':job.result.get('error'),'run_id':job.result.get('run_id'),
        'counts':job.result.get('synthesis_counts'),'requested':job.payload['plan']['counts'],
        'samples':[{'id':s['sample_id'],'image':url+s['image'],'mask':url+s['mask'],'depth':url+s['depth'],
                    'parent_image':url+raw[s['parent_id']]['image'] if s.get('parent_id') else None,
                    'source':s['source'],'mode':s.get('enhancement',{}).get('mode'),'weather':s['weather'],
                    'scene':next(c['config']['editor_scene']['scenario'] for c in job.payload['plan']['sources'] if c['id']==s['source_simulation_id']),
                    'viewpoint':s['scene_editor']['viewpoint'],'time_s':s['physical_volume']['time_s'],
                    'quality':q.get(s['sample_id']), 'physical_ground_truth':s.get('physical_ground_truth',True)} for s in m['samples']],
        'comparisons':[{**c,'baseline':url+c['baseline'],'current':url+c['current']} for c in m.get('comparisons',[])],
        'rejected':rejected}


@router.get('/jobs/{id}/files/{relative:path}')
def file(project:str,id:str,relative:str,user=Depends(current_user),db=Depends(db_session)):
    web=application()
    _,_,folder,m=result_for(project,id,user,db)
    allowed={s[k] for s in m['samples'] for k in ('image','mask','depth','depth_m')}
    allowed.update(c['baseline'] for c in m.get('comparisons',[]))
    if relative not in allowed:raise HTTPException(404,'合成文件不存在')
    p=resolve_artifact(folder,relative)
    if not p.is_file():raise HTTPException(404,'产物尚未生成')
    return FileResponse(p,media_type='image/png' if p.suffix=='.png' else 'application/octet-stream')
