"""Restricted third-party adapters; secrets never enter browser responses."""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import threading
import zipfile
from pathlib import Path
import httpx
from fire_modeling.dataset import publish, export_version, label_studio_tasks, import_label_studio
from fire_modeling.io import read_json, sha256, write_json
from .db import ROOT, STATE, Setting, Link
from .services import root_for

publish_lock=threading.RLock()
review_lock=threading.RLock()

def run_command(argv,cwd,timeout=180):
    env={**os.environ,'DVC_NO_ANALYTICS':'1','PYTHONUTF8':'1','PYTHONIOENCODING':'utf-8','GIT_TERMINAL_PROMPT':'0'}
    p=subprocess.run(argv,cwd=cwd,env=env,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=timeout,shell=False)
    if p.returncode: raise RuntimeError(' '.join(argv[1:4])+': '+(p.stdout+'\n'+p.stderr)[-6000:])
    return p.stdout.strip()

def dvc_publish(run,version_id,name):
    """Publish only when add/commit/push and a manifest backup verification succeed."""
    with publish_lock:
        source=root_for(run)
        reviews=read_json(source/'reviews.json').get('current',{}) if (source/'reviews.json').exists() else {}
        if not any(r.get('decision')=='approved' for r in reviews.values()):
            raise ValueError('No manually approved samples; review the images first')
        repo=STATE/'dvc-repository'; repo.mkdir(exist_ok=True)
        remote=STATE/'dvc-backup'; remote.mkdir(exist_ok=True)
        git=shutil.which('git')
        if not git: raise RuntimeError('缺少Git，请安装后重试')
        dvc=[sys.executable,'-m','dvc']
        if not (repo/'.git').exists():
            run_command([git,'init'],repo)
            run_command([git,'config','user.name','AI07 Local Workbench'],repo)
            run_command([git,'config','user.email','ai07@localhost'],repo)
            run_command([git,'config','commit.gpgsign','false'],repo)
        if not (repo/'.dvc').exists():
            run_command(dvc+['init'],repo)
            # Relative local URLs avoid Windows drive/Unicode URL normalization and
            # remain valid when the same mounted repository is used by Linux.
            run_command(dvc+['remote','add','-d','local_backup','../dvc-backup'],repo)
        target=repo/'datasets'/version_id
        if target.exists(): raise ValueError('该版本目录已存在；请创建新版本')
        report=publish(root_for(run),target,name)
        export=ROOT/'artifacts/platform/exports'/version_id
        export_report=export_version(target,export)
        relative='datasets/'+version_id
        run_command(dvc+['add',relative],repo)
        run_command([git,'add','.dvc','.dvcignore','datasets'],repo)
        run_command([git,'commit','-m',f'Publish research snapshot {version_id}'],repo)
        commit=run_command([git,'rev-parse','HEAD'],repo)
        run_command(dvc+['push'],repo)
        # Independent metadata copy on the same local volume: not offsite protection.
        backup=remote/'manifests'; backup.mkdir(exist_ok=True)
        shutil.copy2(target/'version.json',backup/f'{version_id}.json')
        if sha256(target/'version.json')!=sha256(backup/f'{version_id}.json'): raise RuntimeError('备份核验失败')
        archive=ROOT/'artifacts/platform/archives'/f'{version_id}.zip'; archive.parent.mkdir(parents=True,exist_ok=True)
        with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
            for file in export.rglob('*'):
                if file.is_file(): z.write(file,file.relative_to(export))
        return {'count':len(report['samples']),'splits':report['counts'],'commit':commit,
                'manifest_sha256':sha256(target/'version.json'),'formats':['COCO','YOLO'],
                'backup':'本地DVC remote已推送并核验清单；不是异机备份',
                'acceptance':'研究快照，不代表达到课程算法/规模验收','export':export_report['count']}

def label_config(db):
    row=db.get(Setting,'label_studio')
    return row.value if row else {'url':os.getenv('AI07_LABEL_STUDIO_URL','http://127.0.0.1:8080'),
                                 'token':os.getenv('AI07_LABEL_STUDIO_TOKEN',''),'auth_type':'Token'}

def label_request(config,method,path,**kwargs):
    if not config.get('token'): raise ValueError('请在工程设置中配置Label Studio服务令牌')
    # Fixed API paths only; no arbitrary URL supplied by labeling payloads.
    response=httpx.request(method,config['url'].rstrip('/')+'/api/'+path,
                           headers={'Authorization':config.get('auth_type','Token')+' '+config['token']},
                           timeout=30,follow_redirects=False,**kwargs)
    if response.status_code>=400: raise RuntimeError(f'Label Studio返回HTTP {response.status_code}；请检查服务令牌与项目权限')
    return response.json() if response.content else {}

def label_storage(config,run,project_id):
    # LS requires a project-owned storage record before serving local images.
    # Grant only this batch's image directory; never the shared artifacts root.
    relative=(root_for(run)/'images').relative_to(ROOT/'artifacts').as_posix()
    path='/data/artifacts/'+relative
    storages=label_request(config,'GET',f'storages/localfiles/?project={project_id}')
    if isinstance(storages,dict): storages=storages.get('results',[])
    if not any(s.get('path','').rstrip('/')==path for s in storages):
        label_request(config,'POST','storages/localfiles/',json={
            'project':project_id,'title':'AI07 batch images','path':path,
            'use_blob_urls':True,'recursive_scan':False,'regex_filter':'.*\\.png$'})

def label_sync(db,run):
    config=label_config(db); link=db.get(Link,run.id)
    if link:
        label_storage(config,run,link.value['project_id'])
        return {**link.value,'url':os.getenv('AI07_LABEL_STUDIO_PUBLIC_URL',config['url']).rstrip('/')+f'/projects/{link.value["project_id"]}/data'}
    project=label_request(config,'POST','projects/',json={'title':'AI07 · '+run.name,'label_config':(ROOT/'configs/label_studio.xml').read_text(encoding='utf-8')})
    label_storage(config,run,project['id'])
    tasks=label_studio_tasks(root_for(run),'http://unused.invalid')
    for task,sample in zip(tasks,read_json(root_for(run)/'manifest.json')['samples']):
        # LS and platform mount the exact same artifacts, no public image URLs needed.
        relative=(root_for(run)/sample['image']).relative_to(ROOT/'artifacts').as_posix()
        task['data']['image']='/data/local-files/?d='+relative
    result=label_request(config,'POST',f'projects/{project["id"]}/import',json=tasks)
    public_url=os.getenv('AI07_LABEL_STUDIO_PUBLIC_URL',config['url'])
    value={'project_id':project['id'],'task_count':len(tasks),'url':public_url.rstrip('/')+f'/projects/{project["id"]}/data','import_result':result}
    db.add(Link(run_id=run.id,value=value)); return value

def label_pull(db,run,reviewer):
    config=label_config(db); link=db.get(Link,run.id)
    if not link: raise ValueError('请先同步该批次到Label Studio')
    tasks=label_request(config,'GET',f'projects/{link.value["project_id"]}/export?exportType=JSON')
    completed=[t for t in tasks if any(not a.get('was_cancelled') for a in t.get('annotations',[]))]
    if not completed: raise ValueError('Label Studio中尚无已完成的人工标注')
    with review_lock: return import_label_studio(root_for(run),completed,reviewer)
