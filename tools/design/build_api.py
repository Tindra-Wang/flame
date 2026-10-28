"""Generate explicit target API contracts without pretending endpoints are implemented."""
import json
from pathlib import Path

OUT=Path(__file__).resolve().parents[2]/'docs/design'


def main():
    schemas={
      'Error':{'type':'object','required':['code','message'],'properties':{'code':{'type':'string'},'message':{'type':'string'},'request_id':{'type':'string'}}},
      'JobRequest':{'type':'object','additionalProperties':False,'required':['scene_id','count','budget'],'properties':{'scene_id':{'type':'string','format':'uuid'},'count':{'type':'integer','minimum':1,'maximum':10000},'model_id':{'type':'string','format':'uuid'},'budget':{'type':'object','required':['gpu_seconds','max_attempts'],'properties':{'gpu_seconds':{'type':'integer','minimum':0},'max_attempts':{'type':'integer','minimum':1,'maximum':3},'storage_bytes':{'type':'integer','minimum':0}}}}},
      'Job':{'type':'object','required':['id','status'],'properties':{'id':{'type':'string','format':'uuid'},'status':{'type':'string','enum':['queued','running','retry_wait','cancel_requested','cancelled','failed','succeeded']},'stages':{'type':'array','items':{'type':'object'}},'usage':{'type':'object'},'error':{'type':['object','null']}}},
      'AnnotationUpdate':{'type':'object','additionalProperties':False,'required':['image_sha256','base_revision','boxes'],'properties':{'image_sha256':{'type':'string','pattern':'^[0-9a-f]{64}$'},'base_revision':{'type':'integer','minimum':0},'boxes':{'type':'array','items':{'type':'array','minItems':4,'maxItems':4,'items':{'type':'number','minimum':0}}}}},
      'ReviewRequest':{'type':'object','required':['annotation_revision_id','image_sha256','decision'],'properties':{'annotation_revision_id':{'type':'string','format':'uuid'},'image_sha256':{'type':'string','pattern':'^[0-9a-f]{64}$'},'decision':{'enum':['approved','rejected']},'reason':{'type':'string'}}},
      'WorkerResult':{'type':'object','required':['lease_generation','stage','status','manifest_sha256'],'properties':{'lease_generation':{'type':'integer','minimum':1},'stage':{'enum':['fds','render','diffusion','annotation','quality','export','evaluation']},'status':{'enum':['succeeded','failed','cancelled']},'manifest_sha256':{'type':'string'},'artifact_ids':{'type':'array','items':{'type':'string','format':'uuid'}},'actual_usage':{'type':'object'},'error':{'type':'object'}}},
      'ExperimentRequest':{'type':'object','required':['kind','config'],'properties':{'kind':{'enum':['physical','fid','detection_pair','visual_review']},'config':{'type':'object','description':'Typed per kind in implementation; freeze dataset/model/reference hashes and matched budgets'},'version_ids':{'type':'array','items':{'type':'string','format':'uuid'}}}},
      'VersionRequest':{'type':'object','required':['name','sample_ids'],'properties':{'name':{'type':'string','minLength':1},'sample_ids':{'type':'array','minItems':1,'items':{'type':'string','format':'uuid'}},'group_seed':{'type':'integer','default':42}}},
      'TaskAccepted':{'type':'object','required':['job_id','status_url'],'properties':{'job_id':{'type':'string','format':'uuid'},'status_url':{'type':'string'},'status':{'type':'string','const':'queued'}}},
      'AnnotationRevision':{'type':'object','required':['id','sample_id','revision','image_sha256'],'properties':{'id':{'type':'string','format':'uuid'},'sample_id':{'type':'string','format':'uuid'},'revision':{'type':'integer','minimum':1},'image_sha256':{'type':'string'},'label_studio_annotation_id':{'type':'string'}}},
      'ReviewDecision':{'type':'object','required':['id','annotation_revision_id','decision'],'properties':{'id':{'type':'string','format':'uuid'},'annotation_revision_id':{'type':'string','format':'uuid'},'decision':{'enum':['approved','rejected']}}},
      'Page':{'type':'object','required':['items','total'],'properties':{'items':{'type':'array','items':{'type':'object'}},'total':{'type':'integer','minimum':0}}}
    }
    paths={}
    def add(path,method,summary,request=None,response='Page',code='200',worker=False,public=False):
        op={'summary':summary,'description':'目标设计契约；本次未实现该HTTP端点。所有业务资源必须验证project_id归属。','operationId':method+'_'+path.strip('/').replace('/','_').replace('{','').replace('}','').replace('-','_'),'responses':{code:{'description':'Accepted asynchronous task' if code=='202' else 'Success','content':{'application/json':{'schema':{'$ref':f'#/components/schemas/{response}'}}}},**{c:{'description':d,'content':{'application/json':{'schema':{'$ref':'#/components/schemas/Error'}}}} for c,d in [('400','Invalid input'),('401','Unauthenticated'),('403','Wrong project or role'),('409','Revision/lease/conflict'),('422','Missing legal/data/budget preconditions'),('503','Dependency unavailable')]}},'security':[] if public else [{'WorkerKey':[]}] if worker else [{'BearerAuth':[]}]}
        params=[]
        for segment in path.split('/'):
            if segment.startswith('{'): params.append({'name':segment[1:-1],'in':'path','required':True,'schema':{'type':'string','format':'uuid'}})
        if method=='get' and response=='Page': params += [{'name':'offset','in':'query','schema':{'type':'integer','minimum':0,'default':0}},{'name':'limit','in':'query','schema':{'type':'integer','minimum':1,'maximum':100,'default':20}}]
        if method=='post' and code=='202': params.append({'name':'Idempotency-Key','in':'header','required':True,'schema':{'type':'string','minLength':1,'maxLength':128}})
        if params: op['parameters']=params
        if request: op['requestBody']={'required':True,'content':{'application/json':{'schema':{'$ref':f'#/components/schemas/{request}'}}}}
        paths.setdefault(path,{})[method]=op
    add('/projects','get','项目列表'); add('/projects/{project_id}/members','get','成员与角色')
    add('/projects/{project_id}/scenes','get','场景配置'); add('/projects/{project_id}/jobs','post','提交后台任务','JobRequest','TaskAccepted','202')
    add('/projects/{project_id}/jobs','get','任务列表'); add('/projects/{project_id}/jobs/{job_id}','get','任务及阶段状态',response='Job')
    for action in ['cancel','retry']: add('/projects/{project_id}/jobs/{job_id}/'+action,'post','请求'+action,response='TaskAccepted',code='202')
    add('/projects/{project_id}/jobs/{job_id}/logs','get','脱敏日志分页')
    add('/projects/{project_id}/samples','get','样本筛选：scene/source/group/status')
    add('/projects/{project_id}/samples/{sample_id}/annotations','put','乐观锁修订并同步LS','AnnotationUpdate',response='AnnotationRevision')
    add('/projects/{project_id}/samples/{sample_id}/reviews','post','人工审核绑定图像与修订','ReviewRequest',response='ReviewDecision')
    add('/projects/{project_id}/versions','post','准备不可见冻结快照','VersionRequest','TaskAccepted','202')
    add('/projects/{project_id}/versions','get','版本列表及DVC状态')
    for action in ['publish','exports']: add('/projects/{project_id}/versions/{version_id}/'+action,'post','异步'+action+'，核验质量/授权/DVC前置条件',response='TaskAccepted',code='202')
    add('/projects/{project_id}/versions/{version_id}/diff','get','冻结版本差异')
    add('/projects/{project_id}/experiments','post','物理/FID/视觉/检测对照','ExperimentRequest','TaskAccepted','202')
    add('/projects/{project_id}/experiments/{experiment_id}','get','实验配置与指标证据')
    add('/projects/{project_id}/artifacts/{artifact_id}/download','get','鉴权下载；实现返回短期URL或受控二进制流')
    add('/projects/{project_id}/audit','get','只读审计'); add('/projects/{project_id}/budget','get','预算与实际计量')
    add('/auth/logout','post','退出并撤销会话/令牌')
    add('/projects/{project_id}/samples/{sample_id}','get','图像、掩膜、父子来源和标签历史')
    add('/projects/{project_id}/sources','post','数据/模型来源、授权及合规记录')
    add('/projects/{project_id}/artifacts','post','申请受限上传；实现时返回上传ID/URL与限额')
    add('/internal/projects/{project_id}/artifacts/{artifact_id}/complete','post','核验实际字节与SHA256后接受产物',worker=True)
    add('/internal/projects/{project_id}/worker/claim','post','事务领取匹配能力的任务',response='Job',worker=True)
    add('/internal/projects/{project_id}/jobs/{job_id}/heartbeat','post','核验lease_generation，返回取消信号','WorkerResult','Job',worker=True)
    add('/internal/projects/{project_id}/jobs/{job_id}/stage-result','post','阶段回报＋校验清单','WorkerResult','Job',worker=True)
    add('/internal/projects/{project_id}/label-studio/webhook','post','签名校验、项目映射、幂等与修订冲突',worker=True)
    # Explicit specs for routes whose payloads differ from shared schemas.
    for path,method,summary,payload in [('/auth/login','post','本地账户登录（限速/安全Cookie或Bearer）',{'type':'object','required':['email','password'],'properties':{'email':{'type':'string','format':'email'},'password':{'type':'string','minLength':8}}}),('/projects','post','创建项目',{'type':'object','required':['name'],'properties':{'name':{'type':'string','minLength':1}}}),('/projects/{project_id}/scenes','post','创建校验后的场景修订',{'type':'object','required':['name','config'],'properties':{'name':{'type':'string'},'config':{'type':'object','description':'与SceneConfig单位/网格/引擎支持规则一致'}}})]:
        add(path,method,summary,public=path=='/auth/login')
        paths[path][method]['requestBody']={'required':True,'content':{'application/json':{'schema':payload}}}
    paths['/auth/login']['post']['responses']['200']={'description':'Access token / secure session; never return password hash','content':{'application/json':{'schema':{'type':'object','properties':{'access_token':{'type':'string'},'token_type':{'type':'string','const':'bearer'}}}}}}
    for action in ['publish','exports']:
        if action=='exports': paths['/projects/{project_id}/versions/{version_id}/exports']['post']['requestBody']={'required':True,'content':{'application/json':{'schema':{'type':'object','required':['format'],'properties':{'format':{'enum':['coco','yolo']}}}}}}
    paths['/internal/projects/{project_id}/jobs/{job_id}/heartbeat']['post']['requestBody']['content']['application/json']['schema']={'type':'object','required':['lease_generation'],'properties':{'lease_generation':{'type':'integer','minimum':1}}}
    api=dict(openapi='3.1.0',info=dict(title='AI-07 Platform DESIGN contract',version='design-1.0',description='Target API; not running implementation. Authentication, responses and detailed migration schemas must be finalized with the Web platform.'),servers=[{'url':'/api/v1'}],paths=paths,components=dict(schemas=schemas,securitySchemes={'BearerAuth':{'type':'http','scheme':'bearer','bearerFormat':'JWT'},'WorkerKey':{'type':'apiKey','in':'header','name':'X-Worker-Key','description':'Scoped service credential; LS callback additionally verifies a webhook signature'}}))
    # Verify all local schema references and operation IDs deterministically.
    ids=[]
    for p,ops in paths.items():
        for method,op in ops.items(): ids.append(op['operationId'])
    assert len(ids)==len(set(ids))
    text=json.dumps(api,ensure_ascii=False,indent=2)
    import re
    assert all(ref in schemas for ref in re.findall(r'#/components/schemas/([^"\s]+)',text))
    (OUT/'openapi.design.yaml').write_text(text,encoding='utf-8')
    print(f'Wrote {len(paths)} target paths / {len(ids)} operations; refs checked')


if __name__=='__main__': main()
