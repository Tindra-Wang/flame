"""Batch workflow and evaluation application API; engines execute in workers."""
from collections import Counter
from fastapi import APIRouter,Depends
from sqlalchemy import select
from .dependencies import application,current_user,db_session
from .db import Run,Scene,Version,Job,Link
from .services import sample_views,root_for,uid
from fire_modeling.evaluation_data import freeze_reviewed,detector_inputs
from fire_modeling.io import read_json,write_json,sha256
from fire_modeling.synthesis_contracts import fingerprint

router=APIRouter(prefix='/api/projects/{project}')

@router.get('/workflow')
def workflow(project:str,user=Depends(current_user),db=Depends(db_session)):
    web=application();web.access(db,user,project)
    scenes=list(db.scalars(select(Scene).where(Scene.project_id==project)))
    result=[];weather=Counter();views=Counter();groups=set()
    for run in db.scalars(select(Run).where(Run.project_id==project).order_by(Run.created.desc())):
        samples=sample_views(run);counts=Counter(s['review_status'] for s in samples)
        for s in samples:
            if run.route!='real':
                weather[s.get('weather','unknown')]+=1;views[(s.get('scene_editor') or {}).get('viewpoint','unknown')]+=1;groups.add(s['group_id'])
        result.append({'id':run.id,'name':run.name,'route':run.route,'total':len(samples),'auto_pass':sum(bool(s.get('quality',{} ) and s['quality'].get('auto_screen_pass')) for s in samples),
            'pending':counts['pending'],'approved':counts['approved'],'rejected':counts['rejected'],'enhanced':sum(s['source']=='diffusion' for s in samples),'label_studio_connected':bool(db.get(Link,run.id))})
    return {'coverage':{'saved_scenes':len(scenes),'scenario_types':dict(Counter((s.config.get('editor_scene') or {}).get('scenario',s.config.get('scene_type','unknown')) for s in scenes)),
            'source_groups':len(groups),'weather_samples':dict(weather),'viewpoint_samples':dict(views),'note':'场景名称数量不代表独立物理工况或真实数据覆盖；unknown表示历史样本缺少条件记录。'},'runs':result}


def version_root(db,project,id,user):
    web=application();v=web.scoped(db,Version,str(id),user)
    if v.project_id!=project or v.status!='published':raise ValueError('请选择当前项目已发布的数据版本')
    return web.STATE/'dvc-repository/datasets'/v.id


@router.get('/evaluations/capabilities')
def capabilities(project:str,user=Depends(current_user),db=Depends(db_session)):
    web=application();web.access(db,user,project)
    return {'weights':[p.name for p in (web.ROOT/'models').glob('*.pt') if p.name=='yolo11n.pt'],'real_data_required':True}


@router.post('/evaluations/distribution')
def distribution(project:str,data:dict,user=Depends(current_user),db=Depends(db_session)):
    web=application();web.access(db,user,project,True,{'product','architect','tester'})
    real=web.scoped(db,Run,str(data.get('real_run','')),user);synthetic=web.scoped(db,Run,str(data.get('synthetic_run','')),user)
    if real.project_id!=project or synthetic.project_id!=project or real.route!='real' or synthetic.route not in {'physics'}:raise ValueError('需选择同项目真实参照和物理/扩散合成批次；程序预览不可用于该评价')
    metric=data.get('metric','fid');dims=data.get('dims',64)
    if metric not in {'fid','color-js'} or type(dims)!=int or dims not in {64,192,768,2048}:raise ValueError('评价指标或特征维度不合法')
    id=uid();relative='artifacts/platform/evaluation-inputs/'+id;base=web.ROOT/relative
    from .integrations import review_lock
    with review_lock:
        a=freeze_reviewed(root_for(real),base/'real');b=freeze_reviewed(root_for(synthetic),base/'synthetic',data.get('selection','all'))
    if {s['sha256'] for s in a['samples']}&{s['sha256'] for s in b['samples']}:raise ValueError('真实与合成参照存在重复图像')
    metadata={'real_run':real.id,'synthetic_run':synthetic.id,'real_snapshot_sha256':sha256(base/'real/snapshot.json'),'synthetic_snapshot_sha256':sha256(base/'synthetic/snapshot.json'),
        'selection':data.get('selection','all'),'review_gate':True,'counts':{'real':len(a['samples']),'synthetic':len(b['samples'])}}
    write_json(base/'comparison.json',metadata)
    return web.enqueue(db,project,user,{'name':'审核后分布评价','real_path':relative+'/real/images','synthetic_path':relative+'/synthetic/images','metric':metric,'dims':dims,
        'evaluation_snapshot':metadata,'idempotency_key':uid()},'fid')


@router.post('/evaluations/detector-comparisons')
def detector_comparison(project:str,data:dict,user=Depends(current_user),db=Depends(db_session)):
    web=application();web.access(db,user,project,True,{'product','architect','tester'})
    real=version_root(db,project,data.get('real_version',''),user);synthetic=version_root(db,project,data.get('synthetic_version',''),user)
    splits,syn,_=detector_inputs(real,synthetic)
    params={'epochs':data.get('epochs',5),'batch':data.get('batch',4),'imgsz':data.get('imgsz',384),'seed':data.get('seed',42),'device':'0'}
    for k,lo,hi in [('epochs',1,50),('batch',1,16),('imgsz',64,640),('seed',0,2147483647)]:
        if type(params[k])!=int or not lo<=params[k]<=hi:raise ValueError('训练参数越界：'+k)
    if params['imgsz']%32:raise ValueError('输入尺寸需为32的倍数')
    weights=data.get('weights','yolo11n.pt')
    if weights!='yolo11n.pt' or not (web.ROOT/'models'/weights).is_file():raise ValueError('请选择已安装的公开检测初始权重')
    return web.enqueue(db,project,user,{'name':'真实 / 真实＋合成 检测对照','real_version':str(data['real_version']),'synthetic_version':str(data['synthetic_version']),
        'real_version_sha256':sha256(real/'version.json'),'synthetic_version_sha256':sha256(synthetic/'version.json'),'weights':weights,'weights_sha256':sha256(web.ROOT/'models'/weights),
        'parameters':params,'counts':{**{k:len(v) for k,v in splits.items()},'synthetic_train':len(syn)},'idempotency_key':uid()},'detector-pair')
