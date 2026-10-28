"""Catalog and view models: adapt existing pipeline files without changing algorithms."""
import csv
import hashlib
import json
import os
import secrets
import time
from pathlib import Path
from sqlalchemy import select
from .db import ROOT, STATE, Session, Base, engine, Project, Scene, Run, Job, Version, Event, Setting
from fire_modeling.io import read_json, resolve_artifact

DEFAULT_PROJECT='ai07'

def uid(): return secrets.token_hex(12)

def audit(db,project,actor,action,**detail):
    db.add(Event(id=uid(),project_id=project,actor=actor,action=action,detail=detail))

def root_for(run):
    root=(ROOT/run.relative_path).resolve()
    if not root.is_relative_to(ROOT/'artifacts'): raise ValueError('产物路径不在允许目录')
    return root

def initialize():
    Base.metadata.create_all(engine)
    key=STATE/'worker.key'
    if not key.exists(): key.write_text(secrets.token_urlsafe(40),encoding='utf-8')
    with Session.begin() as db:
        if not db.get(Project,DEFAULT_PROJECT):
            db.add(Project(id=DEFAULT_PROJECT,name='火焰合成研究',owner_id='local'))
        for name in ('room','outdoor'):
            if not db.get(Scene,name):
                config=read_json(ROOT/f'configs/{name}.json')
                db.add(Scene(id=name,project_id=DEFAULT_PROJECT,name='室内房间' if name=='room' else '室外场地',config=config))
        # Only known research artifacts are imported; no recursive scan of private folders.
        candidates=[('artifacts/compose-verified-v3/enhanced','FDS · Blender · SD 实跑','physics'),
                    ('artifacts/demo/room_demo','室内程序预览','preview'),
                    ('artifacts/demo/outdoor_demo','室外程序预览','preview')]
        for relative,name,route in candidates:
            if not (ROOT/relative/'manifest.json').exists(): continue
            id=hashlib.sha256(relative.encode()).hexdigest()[:24]
            if not db.get(Run,id): db.add(Run(id=id,project_id=DEFAULT_PROJECT,name=name,relative_path=relative,route=route))
        # A stopped worker is never silently reclassified as successful.
        for job in db.scalars(select(Job).where(Job.status=='running',Job.updated<time.time()-90)):
            job.status='interrupted'; job.stage='interrupted'; job.log+='\n工作进程中断，需手动重试。'

def sample_views(run):
    root=root_for(run); manifest=read_json(root/'manifest.json')
    reviews=read_json(root/'reviews.json').get('current',{}) if (root/'reviews.json').exists() else {}
    quality=read_json(root/'quality.json') if (root/'quality.json').exists() else {}
    checks={s['sample_id']:s for s in quality.get('samples',[])}
    samples=[]
    for s in manifest.get('samples',[]):
        r=reviews.get(s['sample_id']); check=checks.get(s['sample_id'])
        samples.append({**s,'run_id':run.id,'run_name':run.name,'route':run.route,
                        'simulation_job_id':root.parent.name if (root.parent/'physics/web/simulation.json').is_file() else None,
                        'review':r,'review_status':r['decision'] if r else 'pending',
                        'boxes':r['boxes'] if r else s['boxes'],'quality':check,
                        'url':f'/api/runs/{run.id}/samples/{s["sample_id"]}/image',
                        'mask_url':f'/api/runs/{run.id}/samples/{s["sample_id"]}/mask' if s.get('mask') else None})
    return samples

def run_view(run):
    samples=sample_views(run)
    return {'id':run.id,'name':run.name,'route':run.route,'created':run.created,'count':len(samples),
            'approved':sum(s['review_status']=='approved' for s in samples),'pending':sum(s['review_status']=='pending' for s in samples),
            'rejected':sum(s['review_status']=='rejected' for s in samples),'sources':sorted({s['source'] for s in samples})}

def job_view(job):
    return {k:getattr(job,k) for k in ('id','project_id','kind','status','stage','payload','result','log','cancel_requested','created','updated')}

def hrr_curve(run):
    root=root_for(run)
    # Handoff lives next to render/enhanced in the existing verified run.
    physics=root.parent/'physics'
    if not physics.is_relative_to(ROOT/'artifacts') or not physics.exists(): return []
    paths=list(physics.glob('*_hrr.csv'))
    if not paths: return []
    with paths[0].open(encoding='utf-8-sig') as stream:
        rows=list(csv.reader(stream))
    header=next((i for i,row in enumerate(rows) if any(c.strip().strip('"')=='Time' for c in row)),None)
    if header is None: return []
    names=[c.strip().strip('"') for c in rows[header]]
    if 'HRR' not in names: return []
    points=[]
    for row in rows[header+1:]:
        try: points.append({'time':float(row[names.index('Time')]),'hrr':float(row[names.index('HRR')])})
        except (ValueError,IndexError): continue
    return points[::max(1,len(points)//80)]

def engineering(db,project):
    runs=list(db.scalars(select(Run).where(Run.project_id==project)))
    samples=[s for r in runs for s in sample_views(r)]
    versions=list(db.scalars(select(Version).where(Version.project_id==project)))
    approved=[s for s in samples if s['review_status']=='approved']
    evidence=ROOT/'artifacts/platform/verification.json'
    tests=read_json(evidence) if evidence.exists() else None
    requirements=[
      ('FR-01/02','项目与参数化场景','accounts','已接入','账户权限、项目隔离、室内/室外配置'),
      ('FR-03','物理仿真与批量渲染','simulation','已接入','FDS三维场→OpenVDB→Blender，同批切片与渲染留痕；历史代理保留来源'),
      ('FR-04/05','生成增强与任务编排','jobs','已接入','SD1.5、任务队列、日志、取消、失败重试'),
      ('FR-06/07','候选标注与质量筛选','samples','已接入','框编辑、审核、哈希与结构质检；Label Studio可同步'),
      ('FR-08','DVC版本与导出','versions','已接入','人工审核门禁、不可变快照、DVC/Git、本地备份、COCO/YOLO'),
      ('FR-09','真实数据对照评价','evaluation','需评价数据','FID/物理误差/检测指标入口；没有真实数据不显示虚假成绩'),
    ]
    criteria=[
      {'id':'AT-01','name':'数据规模','target':'发布≥100张；无火≥10；增强≥20','actual':f'{len(approved)}张已审核；{len(versions)}个快照','status':'未验收'},
      {'id':'AT-02','name':'视觉质量','target':'≥100张，两名评价者，合格率≥80%','actual':'需独立双人视觉评价记录','status':'待证据'},
      {'id':'AT-03','name':'物理一致性','target':'独立参照误差≤5%','actual':'FDS曲线可查看，尚无独立参照','status':'待证据'},
      {'id':'AT-04','name':'候选标注','target':'IoU≥0.5时Precision≥85%','actual':'需人工真值与预测对照','status':'待证据'},
      {'id':'AT-05','name':'检测收益','target':'mAP@0.5相对提升≥15%','actual':'需固定真实测试集和等预算对照','status':'待证据'},
      {'id':'AT-06','name':'性能与可用性','target':'3用户；P95≤5s；7天≥99.5%','actual':'需压测与连续监控窗口','status':'待证据'},
      {'id':'AT-07','name':'自动化测试','target':'覆盖率≥70%','actual':tests or '尚未登记本次测试报告','status':'有记录' if tests else '待证据'},
    ]
    files=[('需求规格说明书','SRS.md'),('软件设计与实施方案','docs/design/软件设计与低成本实施方案.md'),
           ('全局ER图','docs/design/10_ER全局联系.png'),('平台使用与部署手册','docs/统一平台使用与部署.md'),
           ('开源参考说明','docs/开源参考与实现映射.md'),('测试计划与报告','docs/平台测试计划与报告.md'),('自动化测试记录','artifacts/platform/verification.json'),
           ('演示PPT','docs/demo.pptx'),('演示视频','docs/demo.mp4')]
    return {'requirements':[dict(id=i,name=n,page=p,status=s,detail=d) for i,n,p,s,d in requirements],
            'criteria':criteria,'deliverables':[{'name':n,'path':p,'exists':(ROOT/p).is_file()} for n,p in files],
            'value':{'reviewed':len(approved),'pending':sum(s['review_status']=='pending' for s in samples),
                     'versions':len(versions),'real_samples':sum(s['source']=='real' for s in samples),
                     'note':'通过预标注修订减少重复劳动；尚无人工基线工时，不能声称节省固定百分比。'}}
