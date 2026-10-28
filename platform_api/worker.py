"""Outbound authenticated local worker: only allowlisted, argv-based engine stages."""
import argparse
import os
from pathlib import Path
import queue
import signal
import subprocess
import sys
import threading
import time
import httpx
from fire_modeling.io import read_json, write_json

ROOT=Path(os.getenv('AI07_ROOT',Path(__file__).resolve().parents[1])).resolve()

class Cancelled(Exception): pass


def native_command(args, container):
    """Translate our allowlisted stage plan to local executables, without Docker access."""
    if not container:
        return args
    start=args.index('--no-deps')+1
    if args[start:start+1]!=['--name']:
        raise ValueError('Invalid engine command')
    service=args[start+2]; stage_args=args[start+3:]
    if service not in {'physics','blender','enhance','gpu'}:
        raise ValueError('Unsupported native engine')
    module='fire_modeling' if service=='gpu' else 'fire_modeling.workflow'
    return [sys.executable,'-m',module,*stage_args]


def terminate_process(proc, native):
    if native and os.name!='nt':
        try: os.killpg(proc.pid,signal.SIGTERM)
        except ProcessLookupError: return
    else: proc.terminate()
    try: proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        if native and os.name!='nt':
            try: os.killpg(proc.pid,signal.SIGKILL)
            except ProcessLookupError: pass
        else: proc.kill()

def command_plan(job):
    id=job['id']
    if len(id)!=24 or any(c not in '0123456789abcdef' for c in id): raise ValueError('Invalid task ID')
    payload=job['payload']; relative=f'artifacts/platform/jobs/{id}'
    host=ROOT/relative; host.mkdir(parents=True,exist_ok=True)
    container='/app/'+relative
    compose=['docker','compose','run','--rm','--no-deps']
    if job['kind']=='synthesis':
        from fire_modeling.synthesis_contracts import fingerprint
        import shutil
        write_json(host/'config.json',payload['config']);write_json(host/'synthesis-plan.json',payload['plan'])
        source=payload.get('resume_from');render_ready=False
        if source:
            if len(source)!=24 or any(c not in '0123456789abcdef' for c in source):raise ValueError('合成续跑来源ID不合法')
            old=ROOT/f'artifacts/platform/jobs/{source}'
            if read_json(old/'synthesis-plan.json')!=payload['plan']:raise ValueError('续跑合成计划不一致')
            for folder in ('render','enhanced'):
                if (old/folder).is_dir():shutil.copytree(old/folder,host/folder,dirs_exist_ok=True,ignore=shutil.ignore_patterns('*.blend','*.vdb','*.tmp'))
            if (old/'editor-result.json').is_file():shutil.copy2(old/'editor-result.json',host/'editor-result.json')
            path=host/'render/manifest.json'
            render_ready=path.is_file() and read_json(path).get('status')=='success_candidates_only' and read_json(path).get('plan_hash')==fingerprint(payload['plan'])
        stages=([] if render_ready else [('blender','synthesis-render')])+([('enhance','synthesis-enhance')] if payload['enhance'] else [])
        return [(stage,compose+['--name',f'ai07-{id}-{stage}',service,stage,'--config',container+'/config.json','--root',container],f'ai07-{id}-{stage}') for service,stage in stages]
    if job['kind']=='editor':
        write_json(host/'config.json',payload['config']);write_json(host/'generation.json',payload['generation'])
        name=f'ai07-{id}-original'
        return [('original',compose+['--name',name,'blender','original','--config',container+'/config.json','--root',container],name)]
    if job['kind']=='video':
        write_json(host/'config.json',payload['config'])
        source=payload.get('resume_from');extra=[]
        if source:
            if len(source)!=24 or any(c not in '0123456789abcdef' for c in source):raise ValueError('续跑来源ID不合法')
            if (ROOT/f'artifacts/platform/jobs/{source}/physics/handoff.json').is_file():extra=['--source-root','/app/artifacts/platform/jobs/'+source]
        return [('physics' if stage=='simulate' else 'video',compose+['--name',f'ai07-{id}-{stage}',service,stage,'--config',container+'/config.json','--root',container]+(extra if stage=='video' else []),f'ai07-{id}-{stage}') for service,stage in ([] if extra else [('physics','simulate')])+[('blender','video')]]
    if job['kind']=='fid':
        for key in ('real_path','synthetic_path'):
            path=(ROOT/payload[key]).resolve()
            if not path.is_relative_to(ROOT/'artifacts'): raise ValueError('Evaluation path outside artifacts')
        args=compose+['--name',f'ai07-{id}-fid','gpu','distribution','--real','/app/'+payload['real_path'],'--synthetic','/app/'+payload['synthetic_path'],'--metric',payload.get('metric','fid'),'--dims',str(payload.get('dims',64)),'--output',container+'/evaluation.json']
        return [('fid',args,f'ai07-{id}-fid')]
    if job['kind']=='detector-pair':
        import shutil
        from fire_modeling.io import sha256
        for name in ('real','synthetic'):
            version=payload[name+'_version']
            if len(version)!=24 or any(c not in '0123456789abcdef' for c in version):raise ValueError('训练版本ID不合法')
            source=ROOT/'.cache/platform/dvc-repository/datasets'/version
            if sha256(source/'version.json')!=payload[name+'_version_sha256']:raise ValueError('训练版本已改变')
            shutil.copytree(source,host/'inputs'/name,dirs_exist_ok=True)
        write_json(host/'learning-request.json',payload)
        name=f'ai07-{id}-detector'
        return [('detector-pair',compose+['--name',name,'gpu','detector-pair','--root',container],name)]
    if job['kind']=='simulation':
        write_json(host/'config.json',payload['config'])
        name=f'ai07-{id}-physics'
        return [('physics',compose+['--name',name,'physics','simulate-web','--config',container+'/config.json','--root',container],name)]
    if job['kind']!='generate': raise ValueError('Unsupported task')
    write_json(host/'config.json',payload['config'])
    if payload['route']=='preview':
        return [('preview',[sys.executable,'-m','fire_modeling','generate','--config',str(host/'config.json'),'--output',str(host/'render'),'--count',str(payload['count']),'--renderer','preview','--physics','none','--enhancer','photometric' if payload.get('enhance') else 'none'],None)]
    steps=[]
    source=payload.get('source_simulation_id')
    if source and (len(source)!=24 or any(c not in '0123456789abcdef' for c in source)):raise ValueError('求解来源ID不合法')
    for service,stage in ([] if source else [('physics','simulate')])+[('blender','render')]+([('enhance','enhance')] if payload.get('enhance') else []):
        name=f'ai07-{id}-{service}'
        extra=['--source-root','/app/artifacts/platform/jobs/'+source] if source and stage=='render' else []
        steps.append((service,compose+['--name',name,service,stage,'--config',container+'/config.json','--root',container,'--count',str(payload['count'])]+extra,name))
    return steps

def execute(client,job):
    endpoint='/api/internal/jobs/'+job['id']; lease=job['lease']; start=time.time()
    def report(**values):
        response=client.post(endpoint,json={'lease':lease,**values}); response.raise_for_status()
        return response.json()
    try:
        for stage,args,container in command_plan(job):
            native=os.getenv('AI07_EXECUTION_MODE')=='native'
            if native:
                args=native_command(args,container);container=None
            if report(stage=stage,log=f'\n[{stage}] 开始执行\n')['cancel_requested']: raise Cancelled()
            env={**os.environ,'PYTHONUNBUFFERED':'1','PYTHONUTF8':'1'}
            proc=subprocess.Popen(args,cwd=ROOT,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace',shell=False,start_new_session=native and os.name!='nt')
            output=queue.Queue()
            def collect():
                for line in proc.stdout: output.put(line)
            thread=threading.Thread(target=collect,daemon=True); thread.start()
            last=0
            try:
                while proc.poll() is None:
                    if time.time()-last>2:
                        log=''
                        while not output.empty(): log+=output.get_nowait()
                        state=report(log=log[-20000:]); last=time.time()
                        if state['cancel_requested']: raise Cancelled()
                    if time.time()-start>1800: raise RuntimeError('任务达到30分钟交互预算，已停止；视频重试可复用已完成帧')
                    time.sleep(.3)
            except BaseException:
                if container:
                    subprocess.run(['docker','stop','--time','2',container],capture_output=True,timeout=15,shell=False)
                terminate_process(proc,native)
                raise
            thread.join(timeout=2); log=''
            while not output.empty(): log+=output.get_nowait()
            report(log=log[-20000:])
            if proc.returncode: raise RuntimeError(f'{stage}退出码{proc.returncode}；请查看阶段日志')
        result={'elapsed_s':round(time.time()-start,2),'route':job['payload'].get('route'),'paid_llm_tokens':0}
        if job['kind']=='fid': result=read_json(ROOT/f'artifacts/platform/jobs/{job["id"]}/evaluation.json')
        if job['kind']=='detector-pair':result=read_json(ROOT/f'artifacts/platform/jobs/{job["id"]}/comparison.json')
        if job['kind']=='simulation':
            result={**result,'simulation_url':f'/api/simulations/{job["id"]}'}
        report(status='succeeded',result=result,log='\n流程完成；生成产物仍需人工审核。\n')
    except Cancelled: report(status='cancelled',result={'elapsed_s':round(time.time()-start,2)},log='\n已停止进程及后续阶段。\n')
    except Exception as exc:
        try: report(status='failed',result={'error':str(exc)},log=f'\n执行失败：{exc}\n')
        except httpx.HTTPError: pass

def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--api',default='http://127.0.0.1:8090')
    parser.add_argument('--once',action='store_true'); args=parser.parse_args()
    key=os.getenv('AI07_WORKER_KEY') or (ROOT/'.cache/platform/worker.key').read_text(encoding='utf-8')
    with httpx.Client(base_url=args.api,headers={'x-worker-key':key},timeout=20,trust_env=False) as client:
        while True:
            try:
                response=client.post('/api/internal/claim'); response.raise_for_status(); job=response.json()
                if job: execute(client,job)
                if args.once: return
            except httpx.HTTPError as exc:
                print(f'平台连接暂不可用：{type(exc).__name__}',flush=True)
                if args.once: raise
            time.sleep(3)

if __name__=='__main__': main()
