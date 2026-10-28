"""Compatibility port for the original editor panels; main platform owns jobs/data."""
import time,math
from pathlib import Path
from fastapi import APIRouter,Depends,HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select
from . import app as web
from .db import Job,Scene,Setting
from .services import job_view,uid,audit
from fire_modeling.io import read_json,write_json,resolve_artifact
from fire_modeling.editor_contract import bind_config

router=APIRouter(prefix='/api/projects/{project}/scene-editor')

def generation_spec(data):
    if not isinstance(data,dict):raise ValueError('生成参数必须为对象')
    d={'engine':'blender','wind_speed':1.5,'temperature':28,'humidity':45,'weathers':['晴'],'viewpoints':['侧视'],'frame_count':8,'augmentations':[],'min_flame_area':.002,'seed':None,'count':1,'wind_step':0,**data}
    if d['engine'] not in {'blender','fds'}:raise ValueError('未知仿真引擎')
    for key,low,high in [('wind_speed',0,100),('temperature',-80,100),('humidity',0,100),('min_flame_area',0,.5),('wind_step',0,100)]:
        d[key]=float(d[key])
        if not math.isfinite(d[key]) or not low<=d[key]<=high:raise ValueError('生成参数越界：'+key)
    for key,allowed in [('weathers',{'晴','雨','雪'}),('viewpoints',{'侧视','俯视','第一人称'}),('augmentations',{'噪声','模糊','光照变化'})]:
        if not isinstance(d[key],list) or len(set(d[key]))!=len(d[key]) or set(d[key])-allowed or (key!='augmentations' and not d[key]):raise ValueError('生成选项不合法：'+key)
    for key,high in [('frame_count',48),('count',100)]:
        n=float(d[key]);d[key]=int(n)
        if n!=int(n) or not 1<=n<=high:raise ValueError('数量不合法：'+key)
    if d['seed'] not in ('',None):
        d['seed']=int(d['seed'])
        if not 0<=d['seed']<=2**32-1:raise ValueError('种子应为0至2^32-1')
    else:d['seed']=None
    if d['frame_count']*d['count']*len(d['weathers'])*len(d['viewpoints'])*(1+len(d['augmentations']))>20000:raise ValueError('每批最多20000样本')
    if d['engine']=='fds':
        if '雪' in d['weathers']:raise ValueError('FDS雪粒融化与积雪模型尚未接入；请使用晴/雨物理工况，雪景合成不等于雪天物理预测')
        if d['augmentations']:raise ValueError('传统图像增强不参与FDS求解；请在数据合成环节运行')
        if d['count']*len(d['weathers'])>8:raise ValueError('每批FDS最多8个独立工况')
        for key,default,low,high in [('rain_mm_h',5,.1,50),('rain_diameter_um',1000,100,3000)]:
            d[key]=float(d.get(key,default))
            if not math.isfinite(d[key]) or not low<=d[key]<=high:raise ValueError('雨滴工况参数越界：'+key)
    return d

@router.post('/grid-recommendation')
def grid_recommendation(project:str,data:dict,user=Depends(web.current_user),db=Depends(web.db_session)):
    web.access(db,user,project)
    scene=web.scoped(db,Scene,str(data.get('scene_id','')),user)
    if scene.project_id!=project:raise HTTPException(403,'场景不属于当前项目')
    from fire_modeling.mesh_recommendation import recommend_mesh
    raw=data.get('editor_scene') or scene.config.get('editor_scene')
    if not isinstance(raw,dict):raise ValueError('请先配置三维场景')
    temperature=float(data.get('temperature',scene.config.get('ambient_temperature_c',20)))
    if not math.isfinite(temperature) or not -80<=temperature<=100:raise ValueError('环境温度越界')
    return recommend_mesh({**scene.config,'ambient_temperature_c':temperature},raw)

@router.post('/templates/{template_id}')
def create_template(project:str,template_id:str,user=Depends(web.current_user),db=Depends(web.db_session)):
    web.access(db,user,project,True,web.BUILDERS)
    from fire_modeling.scene_templates import build_template,TEMPLATES
    config,_=build_template(template_id)
    row=Scene(id=uid(),name=TEMPLATES[template_id]['name'],project_id=project,config=config.to_dict())
    db.add(row);audit(db,project,user.username,'创建模板场景',scene=row.id,template=template_id);db.commit()
    return {'id':row.id,'name':row.name,'config':row.config}

@router.post('/generate')
def generate(project:str,data:dict,user=Depends(web.current_user),db=Depends(web.db_session)):
    web.access(db,user,project,True,web.BUILDERS)
    scene=web.scoped(db,Scene,str(data.get('scene_id','')),user)
    if scene.project_id!=project or not scene.config.get('editor_scene'):raise ValueError('先保存编辑场景')
    if scene.config['editor_scene']['revision']!=data.get('scene_revision'):raise HTTPException(409,'场景版本变化，请重新载入')
    spec=generation_spec(data.get('generation',{}));raw={**scene.config['editor_scene'],'viewpoints':spec['viewpoints']}
    base={**scene.config,'ambient_temperature_c':spec['temperature']};recommendation=None
    if spec.get('mesh_policy','manual') not in {'auto','manual'}:raise ValueError('未知网格策略')
    if spec['engine']=='fds' and spec.get('mesh_policy')=='auto':
        from fire_modeling.mesh_recommendation import recommend_mesh
        recommendation=recommend_mesh(base,raw)
        spec['cell_size_m']=recommendation['recommended']['cell_size_m']
    if spec['engine']=='fds' and 'cell_size_m' in spec:
        dx=float(spec['cell_size_m'])
        if not math.isfinite(dx) or not .05<=dx<=2:raise ValueError('FDS网格尺寸需在0.05至2米之间')
        base['cell_size_m']=dx
    config=bind_config(base,raw)
    from .scene_editor import assert_assets
    assert_assets(web.ROOT,project,raw)
    if spec['engine']=='fds':
        # 提交时即校验“起火点被实体掩埋”等会产出零燃烧工况的布局，避免跑完才发现黑视频
        from fire_modeling.editor_contract import editor_fds_input
        editor_fds_input(config)
        from dataclasses import replace
        if spec['frame_count']<2:raise ValueError('FDS视频至少需要2个时间帧')
        duration=float(spec.get('duration_s',config.duration_s))
        if not math.isfinite(duration) or not 3<=duration<=60:raise ValueError('FDS求解时长需在3至60秒之间，且须长于火源增长时间')
        config=replace(config,duration_s=duration,output_frames=spec['frame_count'],ambient_temperature_c=spec['temperature'],ambient_relative_humidity_pct=spec['humidity'],wind_m_s=0 if config.scene_type=='indoor' else spec['wind_speed'])
        planned=[]
        from fire_modeling.fds_weather import condition
        for weather in spec['weathers']:
            for repeat in range(spec['count']):
                actual=replace(config,physical_weather=weather,rain_mm_h=spec['rain_mm_h'] if weather=='雨' else 0,rain_diameter_um=spec['rain_diameter_um'],wind_m_s=0 if config.scene_type=='indoor' else spec['wind_speed']+repeat*spec['wind_step'])
                actual.validate();web.simulation_config({'config':actual.to_dict()})
                planned.append((actual,{**spec,'weathers':[weather],'count':1,'repeat_index':repeat}))
        key=str(data.get('idempotency_key',''))
        if not 8<=len(key)<=100:raise ValueError('请求需包含8至100位幂等键')
        import hashlib
        jobs=[]
        for i,(actual,generation) in enumerate(planned):
            childkey=key if len(planned)==1 else hashlib.sha256((key+':fds-weather:'+str(i)).encode()).hexdigest()
            payload={'scene_id':scene.id,'scene_revision':raw['revision'],'config':actual.to_dict(),'generation':generation,'mesh_recommendation':recommendation,'physical_conditions':condition(actual),'name':scene.name+' · '+actual.physical_weather+' · FDS'+(f' · {i+1}' if len(planned)>1 else ''),'route':'physics','enhance':False,'idempotency_key':childkey,'batch_key':hashlib.sha256(key.encode()).hexdigest()}
            jobs.append(web.enqueue(db,project,user,payload,'video'))
        return {**jobs[0],'batch_jobs':[j['id'] for j in jobs]}
    return web.enqueue(db,project,user,{'scene_id':scene.id,'scene_revision':raw['revision'],'config':config.to_dict(),'generation':spec,'name':scene.name+' · 原版Mantaflow','route':'physics','enhance':False,'idempotency_key':data.get('idempotency_key','')},'editor')

def owned(db,user,project,id):
    j=web.scoped(db,Job,id,user)
    if j.project_id!=project:raise HTTPException(403,'作业不属于当前项目')
    if j.status=='running' and time.time()-j.updated>90:
        j.status='interrupted';j.stage='interrupted';j.log+='\n执行器90秒无心跳，已中断；可续跑已完成帧。';db.commit()
    return j

def summary(j):
    result={'job_id':j.id,'scene_ids':[j.payload.get('scene_id')],'state':j.status,'created_at':j.created*1000,'completed':len(read_json(web.ROOT/f'artifacts/platform/jobs/{j.id}/editor-result.json')['combos']) if (web.ROOT/f'artifacts/platform/jobs/{j.id}/editor-result.json').is_file() else (len(j.payload['config'].get('editor_scene',{}).get('viewpoints',[])) if j.status=='succeeded' else 0),'total':len(j.payload.get('generation',{}).get('weathers',['晴']))*len(j.payload['config'].get('editor_scene',{}).get('viewpoints',['侧视']))*j.payload.get('generation',{}).get('count',1),'kept':j.result.get('samples',0),'dropped':0,'error':j.result.get('error'),'request':[j.payload]}

    items,_=assets(j)
    generation=j.payload.get('generation',{})
    result['total']=len(generation.get('weathers',['晴']))*len(generation.get('viewpoints',j.payload['config'].get('editor_scene',{}).get('viewpoints',['侧视'])))*generation.get('count',1)
    result['kept']=sum(s.get('auto_screen_pass',True) for s in items)
    result['dropped']=len(items)-result['kept']
    result['kind']=j.kind
    if j.kind=='synthesis':result['total']=len({(i['source_id'],i['weather'],i['viewpoint']) for i in j.payload['plan']['items']})
    if j.status=='interrupted':result.update(state='failed',error='执行器中断，可重跑或续跑')
    return result
@router.get('/compat/jobs')
def jobs(project:str,scene:str='',user=Depends(web.current_user),db=Depends(web.db_session)):
    web.access(db,user,project)
    rows=db.scalars(select(Job).where(Job.project_id==project).order_by(Job.created.desc()).limit(100))
    return {'jobs':[summary(j) for j in rows if j.payload.get('scene_id')==scene or scene in j.payload.get('scene_ids',[])]}

def assets(j):
    root=web.ROOT/f'artifacts/platform/jobs/{j.id}'
    manifest_path=root/'render/manifest.json'
    enhanced=root/'enhanced/manifest.json'
    if j.kind=='synthesis' and enhanced.is_file() and read_json(enhanced).get('status')=='success_candidates_only':manifest_path=enhanced
    if not manifest_path.is_file() and (root/'video/manifest.json').is_file():manifest_path=root/'video/manifest.json'
    if manifest_path.is_file():
        rows=read_json(manifest_path).get('samples',[]);qfile=manifest_path.parent/'quality.json'
        checks={q['sample_id']:q for q in read_json(qfile).get('samples',[])} if qfile.is_file() else {}
        return [{**s,'auto_screen_pass':checks.get(s['sample_id'],{}).get('auto_screen_pass',s.get('auto_screen_pass',True))} for s in rows],manifest_path.parent
    video=root/'video/video.json';samples=[]
    if video.is_file():
        for vi,v in enumerate(read_json(video)['videos']):
            for f,e in enumerate(v['timeline']):samples.append({'sample_id':f'v{vi}_f{f:03d}','image':e['file'],'mask':str(Path(e['file']).parent/'mask.png'),'width':j.payload['config']['width'],'height':j.payload['config']['height'],'frame_index':f,'combo_index':vi,'scene_editor':{'viewpoint':v['viewpoint']},'weather':'晴','boxes':[]})
    return samples,root/'video'

def progress(j):
    root=web.ROOT/f'artifacts/platform/jobs/{j.id}';path=root/'video/progress.json'
    if j.kind=='synthesis':
        p=root/'synthesis-progress.json'
        if p.is_file():
            state=read_json(p)
            return f"合成 · {state['stage']} · "+(f"{state['completed']}/{state['total']}组合" if 'completed' in state else f"通过{state['accepted']} / 拒绝{state['rejected']} / 请求{state['total']}")
    if path.is_file():
        p=read_json(path);return f"{p['phase']} · {p['completed']}/{p['total']} 帧 · {p.get('viewpoint','')} · 已耗时{p.get('elapsed_s',0):.0f}秒"
    if j.kind=='editor' and j.status=='running':
        count=sum(1 for p in root.glob('original-*/frames/rgb/*.png'));g=j.payload['generation']
        return f"原版Mantaflow烘焙/渲染：已输出{count}/{g['frame_count']*g['count']*len(g['viewpoints'])*len(g['weathers'])}帧；最大执行预算30分钟"
    return {'physics':'FDS三维求解','queued':'等待工作进程','interrupted':'执行器中断，可续跑','succeeded':'产物完成'}.get(j.stage,j.stage)

@router.get('/compat/jobs/{id}')
def detail(project:str,id:str,user=Depends(web.current_user),db=Depends(web.db_session)):
    j=owned(db,user,project,id);return {**summary(j),'run_id':j.result.get('run_id')}

@router.get('/compat/jobs/{id}/trajectory')
def job_trajectory(project:str,id:str,download:bool=False,user=Depends(web.current_user),db=Depends(web.db_session)):
    j=owned(db,user,project,id)
    if j.kind=='synthesis':return {'available':False,'reason':'这是训练图像合成作业；物理时序见来源仿真，增强图不作为新的CFD真值'}
    if j.kind=='editor' or j.payload.get('route')!='physics':
        return {'available':False,'reason':'此作业不是FDS物理路线，不能提供FDS时序参数'}
    from fire_modeling.trajectory import trajectory
    result=trajectory(web.ROOT/f'artifacts/platform/jobs/{id}/physics')
    result.update(simulation_id=id,scene_id=j.payload.get('scene_id'),scene_revision=j.payload.get('scene_revision'),job_status=j.status)
    video=web.ROOT/f'artifacts/platform/jobs/{id}/video/video.json'
    result['videos']=read_json(video).get('videos',[]) if video.is_file() else []
    if download:
        if not result['available']:raise HTTPException(409,result['reason'])
        from fastapi.responses import JSONResponse
        result['frames']=[{k:v for k,v in frame.items() if k!='fds_next'} for frame in result['frames']]
        result['input_guard']='训练输入仅按training_windows选择历史帧，下一FDS展示字段已移除；target_index为监督标签'
        return JSONResponse(result,headers={'Content-Disposition':f'attachment; filename="{id}-temporal.json"'})
    return result

@router.get('/compat/jobs/{id}/stages')
def stages(project:str,id:str,user=Depends(web.current_user),db=Depends(web.db_session)):
    j=owned(db,user,project,id);root=web.ROOT/f'artifacts/platform/jobs/{id}'
    items,_=assets(j);vfile=root/'video/video.json';videos=read_json(vfile)['videos'] if vfile.is_file() else []
    result=root/'editor-result.json';groups=read_json(result)['combos'] if result.is_file() else [{'index':i,'scene':j.payload['config']['scene_type'],'weather':v.get('weather','晴'),'viewpoint':v['viewpoint'],'video_index':i} for i,v in enumerate(videos)]
    queue=root/'review-queue.json';sent=set(read_json(queue)) if queue.is_file() else set()
    combos=[]
    for group in groups:
        samples=[s for s in items if s.get('combo_index')==group['index']];entries=[]
        for s in samples:
            alias=id+'~'+s['sample_id'];status='pending_review' if s['sample_id'] in sent else ('generated' if s.get('auto_screen_pass',True) else 'dropped')
            entries.append({'sample_id':alias,'frame_index':s.get('frame_index',0),'augmentation':s.get('augmentation'),'status':status})
        first=entries[0]['sample_id'] if entries else None
        combos.append({**group,'samples':entries,'frames':sum(s.get('parent_id') is None for s in samples),'kept':sum(e['status']!='dropped' for e in entries),'dropped':sum(e['status']=='dropped' for e in entries),'preview_url':f'/api/projects/{project}/scene-editor/compat/samples/{first}/files/image.png' if first else None,'video_url':f'/api/simulation-videos/{id}/files/{group["video_index"]}' if videos else None})
    heart=db.get(Setting,'worker_heartbeat');online=bool(heart and time.time()-heart.value.get('at',0)<25)
    note=progress(j)
    if j.status in {'queued','running'} and not online:note+='；工作进程离线，请运行scripts/start-platform.ps1'
    return {'combos':combos,'sequences':[{'engine_message':note}]}

def sample(db,user,project,alias):
    id,sid=alias.split('~',1);j=owned(db,user,project,id);rows,root=assets(j)
    row=next((s for s in rows if s['sample_id']==sid),None)
    if not row:raise HTTPException(404,'样本不存在')
    return j,row,root

@router.get('/compat/samples/{alias}')
def sample_detail(project:str,alias:str,user=Depends(web.current_user),db=Depends(web.db_session)):
    j,s,root=sample(db,user,project,alias)
    return {'status':'generated','auto_objects':[{'bbox':[b[0],b[1],b[2]-b[0],b[3]-b[1]],'image_width':s['width'],'image_height':s['height']} for b in s.get('boxes',[])],'quality':{'checks':{'flame_area':s.get('flame_area',0),'reasons':[] if s.get('auto_screen_pass',True) else ['火焰占比不足']}}}

@router.get('/compat/samples/{alias}/files/{name}')
def sample_file(project:str,alias:str,name:str,user=Depends(web.current_user),db=Depends(web.db_session)):
    _,s,root=sample(db,user,project,alias)
    if name not in {'image.png','mask.png'}:raise HTTPException(404,'文件不存在')
    path=resolve_artifact(root,s['image' if name=='image.png' else 'mask'])
    if not path.is_file():raise HTTPException(404,'帧尚未生成')
    return FileResponse(path,media_type='image/png')

@router.post('/compat/jobs/{id}/{action}')
def action(project:str,id:str,action:str,data:dict,user=Depends(web.current_user),db=Depends(web.db_session)):
    j=owned(db,user,project,id)
    if action=='cancel':return web.job_action(id,'cancel',user,db)
    if action!='continue':raise HTTPException(404,'未知操作')
    web.access(db,user,project,True,web.BUILDERS)
    payload={**j.payload,'idempotency_key':uid(),'retry_of':id}
    if j.kind=='video':payload['resume_from']=id
    if j.kind=='synthesis':
        payload['resume_from']=id
        if data.get('combo_index') is not None:
            from fire_modeling.synthesis_contracts import build_plan,fingerprint
            original=j.payload['plan'];groups=list(dict.fromkeys((i['source_id'],i['weather'],i['viewpoint']) for i in original['items']))
            index=data['combo_index']
            if type(index)!=int or not 0<=index<len(groups):raise ValueError('合成组合编号不存在')
            source_id,weather,view=groups[index];source=next(s for s in original['sources'] if s['id']==source_id)
            plan=build_plan([source],{**original['options'],'weathers':[weather],'viewpoints':[view]})
            payload.update(plan=plan,plan_hash=fingerprint(plan),config=source['config'],scene_id=source['scene_id'],scene_ids=[source['scene_id']],scene_revision=source['scene_revision'])
            payload.pop('resume_from',None)
    if data.get('combo_index') is not None and j.kind=='editor':
        groups=read_json(web.ROOT/f'artifacts/platform/jobs/{id}/editor-result.json')['combos'];g=next(g for g in groups if g['index']==data['combo_index'])
        original=payload['generation'];repeat=g.get('repeat_index',0)
        payload['generation']={**original,'weathers':[g['weather']],'viewpoints':[g['viewpoint']],'count':1,'wind_speed':original['wind_speed']+repeat*original['wind_step'],'seed':(original['seed'] if original['seed'] is not None else payload['config']['seed'])+repeat}
    return web.enqueue(db,project,user,payload,j.kind)

@router.post('/compat/review-queue')
def review_queue(project:str,data:dict,user=Depends(web.current_user),db=Depends(web.db_session)):
    web.access(db,user,project,True,web.BUILDERS|{'tester'})
    for alias in data.get('samples',[]):
        j,s,_=sample(db,user,project,alias)
        if j.status!='succeeded':raise ValueError('作业未成功，不能送审')
        if not s.get('auto_screen_pass',True):raise ValueError('自动筛除样本不能直接送审')
        path=web.ROOT/f'artifacts/platform/jobs/{j.id}/review-queue.json';ids=set(read_json(path)) if path.is_file() else set();ids.add(s['sample_id']);write_json(path,sorted(ids))
    audit(db,project,user.username,'原版编辑器送审',samples=data.get('samples',[]));db.commit();return {'status':'pending_review'}

