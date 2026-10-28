"""Canonical JSON-as-YAML draw.io specs, from a single calculated estimate."""
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'docs/design'; TMP=ROOT/'docs/design/specs'
EST=json.loads((OUT/'estimate.json').read_text(encoding='utf-8'))
BLUE='#EAF2FC'; GREEN='#E9F4EE'; GRAY='#F1F3F5'; AMBER='#FFF2DB'; RED='#FCEBEB'


def node(id,label,x,y,w=256,h=104,type='service',fill=BLUE,**style):
    return dict(id=id,label=label,type=type,bounds=dict(x=x,y=y,width=w,height=h),style={**dict(fontSize=18,fontFamily='Microsoft YaHei',fillColor=fill,strokeColor='#64748B'),**style})


def text(id,label,x,y,w=1500,h=40,size=20):
    return dict(id=id,label=label,type='text',bounds=dict(x=x,y=y,width=w,height=h),style=dict(fontSize=size,align='left',fontFamily='Microsoft YaHei'))


def edge(a,b,label='',**style):
    return dict(from_=a,to=b,label=label,type='primary',labelOffset=dict(x=0,y=-16),style={**dict(endArrow='open',endSize=12,strokeWidth=2),**style})


def save(name,title,subtitle,nodes,edges,w=1816,h=1120):
    for e in edges: e['from']=e.pop('from_')
    # Labels report inherited candidate state; all images remain manual-review gated.
    if name=='01_总体框架':
        edges[2]['style']['exitX']=124/1712
        edges[-1]['style']['entryX']=1564/1712
    if name=='02_系统架构':
        nodes=[n for n in nodes if n['id']!='cloudnote']
        for e in edges:
            if (e['from'],e['to'])==('api','pg'):
                e['waypoints']=[{'x':480,'y':254},{'x':480,'y':512}]
                e['style'].update(exitX=0,exitY=.65,entryX=1,entryY=.5)
    if name=='04_UML类图':
        for n in nodes:
            if n['type']!='text': n['style']['fontSize']=16
        for e in edges:
            if (e['from'],e['to'])==('jobs','repo'):
                e['waypoints']=[{'x':824,'y':260},{'x':824,'y':720},{'x':628,'y':720}]
                e['style'].update(exitX=1,exitY=.5,entryX=.5,entryY=0)
            if (e['from'],e['to'])==('fds','engine'):
                e['style']['dashed']=1
            if e['from']=='diff' and e['to']=='engine':
                e['waypoints']=[{'x':1744,'y':960},{'x':1744,'y':136},{'x':1044,'y':136}]
                e['style'].update(exitX=1,exitY=.5,entryX=.5,entryY=0)
    if name=='05_UML状态':
        edges[:]=[e for e in edges if not(e['from']=='done' and e['to']=='cancel')]
        for e in edges:
            if e['from']=='running' and e['to']=='cancel': e['waypoints']=[{'x':590,'y':208},{'x':1436,'y':208}]
    if name=='06_ER核心数据':
        for e in edges:
            if (e['from'],e['to'])==('annotation','review'):
                e['waypoints']=[{'x':1092,'y':672},{'x':660,'y':672}]
                e['style'].update(exitX=.5,exitY=1,entryX=.5,entryY=0)
                e['labelOffset']={'x':-96,'y':-16}
            if (e['from'],e['to'])==('artifact','sample'):
                e['waypoints']=[{'x':228,'y':664},{'x':552,'y':664}]
                e['style'].update(exitX=.5,exitY=0,entryX=.2,entryY=1)
            if (e['from'],e['to'])==('sample','item'):
                e['waypoints']=[{'x':864,'y':589},{'x':864,'y':696},{'x':1744,'y':696},{'x':1744,'y':808}]
                e['style'].update(exitX=1,exitY=.8,entryX=1,entryY=.5)
    if name=='07_ER治理评价':
        for n in nodes:
            if n['id']=='footer': n['style']['fontSize']=16
        for e in edges:
            if (e['from'],e['to'])==('user','worker'):
                e['waypoints']=[{'x':228,'y':400},{'x':1092,'y':400}]
                e['style'].update(exitX=.5,exitY=1,entryX=.5,entryY=1)
            if (e['from'],e['to'])==('user','audit'):
                e['waypoints']=[{'x':228,'y':144},{'x':1524,'y':144}]
                e['style'].update(exitX=.5,exitY=0,entryX=.5,entryY=0)
                e['labelOffset']={'x':0,'y':20}
    spec=dict(meta=dict(title=title,theme='tech-blue',profile='default',layout='horizontal',canvas=f'{w}x{h}',font=dict(primary='Microsoft YaHei',cjk='Microsoft YaHei',formula='Microsoft YaHei')),nodes=[text('title',title,48,24,w-96,48,28),text('subtitle',subtitle,48,80,w-96,48,18),*nodes],edges=edges)
    TMP.mkdir(parents=True,exist_ok=True)
    (TMP/f'{name}.spec.yaml').write_text(json.dumps(spec,ensure_ascii=False,indent=2),encoding='utf-8')


def framework():
    n=[node('value','价值：减少危险采集与重复标注\n增加场景多样性；保留真实评价证据',48,152,1712,80,fill=GREEN),node('web','统一 Web 可视化平台（待实现）\n场景配置 / 任务日志 / 原图增强对比 / 标注质检 / DVC版本 / 评价监控',48,280,1712,96),node('api','FastAPI 模块化应用：身份与项目隔离、任务编排、审核门禁、发布事务、可追溯性',48,424,1712,72)]
    labels=[('fds','FDS\nCFD＋燃烧模型\n物理量、日志、工况'),('blender','Blender\n多场景/视角/能见度\nRGB＋候选掩膜'),('sd','Stable Diffusion\n预训练 img2img\n种子/模型哈希/父图'),('ls','Label Studio\n候选标注＋人工修订\n审核绑定图像/修订'),('qc','质量筛选\n完整性/重复/框合法性\n视觉人工评价'),('dvc','DVC＋Git\n冻结清单与版本差异\nCOCO/YOLO导出')]
    for i,(id,label) in enumerate(labels): n.append(node(id,label,48+288*i,560,248,136,fill=GREEN if i<4 else AMBER))
    n += [node('eval','验收证据：真实/合成 FID；相同预算下 YOLO 两组对照；物理量与独立参照误差\n现有样例只证明部分链路可运行，不能证明 5%物理误差或15%检测提升',48,768,1712,104,fill=AMBER),node('eng','工程实践贯穿全链路：规范化数据管道 / 人工真值 / 同源分组 / 幂等与取消 / 镜像与模型固定\n统一交付：SRS、SDD、测试、OpenAPI、Git Flow、SonarQube、Compose、CI/CD、监控、云Demo、PPT/视频、合规材料',48,920,1712,112,fill=GRAY)]
    e=[edge('value','web'),edge('web','api'),edge('api','fds',exitX=.08,exitY=1,entryX=.5,entryY=0)]+[edge(labels[i][0],labels[i+1][0]) for i in range(5)]+[edge('dvc','eval',exitX=.5,exitY=1,entryX=.92,entryY=0)]
    save('01_总体框架','AI-07 完整功能框架','指定技术栈全部保留；绿色为已有部分能力，蓝/橙为待完善设计；本图不代表平台已建成',n,e)


def architecture():
    n=[node('web','浏览器：Vue3＋TypeScript\n场景/任务/对比/审核/版本/评价\n单一项目权限上下文',48,160,376,128),node('api','Nginx TLS → FastAPI 模块化应用\nAuth / Projects / Jobs / Samples\nReview / Versions / Experiments\nOpenAPI + /metrics',544,160,576,144),node('worker','本机或按需 GPU Worker\n主动 HTTPS 拉取任务\nlease / heartbeat / timeout\n只通过内部API回传业务状态',1280,408,432,144),node('pg','PostgreSQL\n项目元数据＋持久任务队列\n事务 claim / SKIP LOCKED\n单写入边界：平台应用',48,440,376,144,type='database'),node('ls','Label Studio（内部服务）\nAPI 同步真实任务与标签\n平台框编辑 → 受限代理API\n不共享管理员令牌给浏览器',544,440,576,144),node('store','Artifact StoragePort\n本地文件卷＋云端已审核产物\n鉴权上传/下载、SHA256、配额\n后续可换 S3，业务不依赖路径',48,736,376,144,type='database'),node('dvc','DVC / Git Adapter\n准备快照 → DVC提交/备份\n核验成功后标记已发布\n失败保持不可见，可对账恢复',544,736,576,144),node('engines','隔离引擎与算法适配器\nFDS → Blender → SD\n质检 / COCO-YOLO / FID / 检测\nCPU与GPU并发配额独立',1280,736,432,144,fill=GREEN),node('ops','工程与运维接口：GitHub Actions → 测试≥70% → SonarQube门禁 → 镜像构建/灰度/回滚\nPrometheus＋Grafana告警；Sonar按需运行；独立备份/恢复；成本计量事件；云端CPU Demo接入在线Worker',48,976,1664,112,fill=GRAY),text('cloudnote','云 CPU：Web/API、PG、LS、产物与轻量监控；重任务不占HTTP进程',48,336,1100,48,18),text('localnote','本地/临租计算区',1280,336,432,48,18)]
    e=[edge('web','api','HTTPS'),edge('api','pg','事务',exitX=.1,exitY=1,entryX=1,entryY=.2),edge('api','ls','受限服务账号',exitX=.5,exitY=1,entryX=.5,entryY=0),edge('pg','store','元数据引用',exitX=.5,exitY=1,entryX=.5,entryY=0),edge('ls','dvc','审核完成事件',exitX=.5,exitY=1,entryX=.5,entryY=0),edge('dvc','store','内容寻址',exitX=0,exitY=.5,entryX=1,entryY=.5),edge('worker','api','出站HTTPS',exitX=0,exitY=.1,entryX=1,entryY=.6),edge('worker','engines','显式 argv＋阶段清单',exitX=.5,exitY=1,entryX=.5,entryY=0)]
    save('02_系统架构','AI-07 低耦合系统架构（目标态）','低成本取舍：一个模块化API＋少量Worker；PG复用为队列，不新增Redis/Celery/K8s',n,e,h=1152)


def usecase():
    n=[node('builder','«actor»\n数据构建人员',48,328,224,120,type='user',fill=GRAY),node('reviewer','«actor»\n审核/评价人员',48,656,224,120,type='user',fill=GRAY),node('admin','«actor»\n管理员',1456,488,224,120,type='user',fill=GRAY)]
    n=[node('builder','«actor»\n数据构建人员',48,456,224,120,type='user',fill=GRAY),node('reviewer','«actor»\n审核/评价人员',1456,280,224,120,type='user',fill=GRAY),node('admin','«actor»\n管理员',1456,704,224,120,type='user',fill=GRAY)]
    items=[('scene','配置工况/视角/天气',400,176),('jobs','提交/取消/重试任务',400,384),('compare','原图增强对比与检索',400,592),('review','修订标签与审核质检',1040,176),('version','冻结DVC版本与导出',400,800),('evaluate','物理/FID/检测评价',1040,384),('auth','账户与项目授权',1040,592),('ops','监控/配额/审计/恢复',1040,800)]
    for id,label,x,y in items: n.append(node(id,label,x,y,256,104,type='user'))
    n.append(node('gate','检查审核/质量门禁',752,800,240,104,type='user',fill=AMBER))
    e=[edge('builder',i,endArrow='none',exitX=1,exitY=.5,entryX=0,entryY=.5) for i in ['scene','jobs','compare','version']]+[edge('reviewer',i,endArrow='none',exitX=0,exitY=.5,entryX=1,entryY=.5) for i in ['review','evaluate']]+[edge('admin',i,endArrow='none',exitX=0,exitY=.5,entryX=1,entryY=.5) for i in ['auth','ops']]+[edge('version','gate','«include»',dashed=1,exitX=1,exitY=.5,entryX=0,entryY=.5)]
    n.append(text('note','全部用例先校验项目权限；发布引用人工审核修订；评价需要独立真实数据；管理员不能绕过数据发布质量门禁',48,1000,1664,48,18))
    save('03_UML用例','UML 用例图','角色可以由同一成员承担；平台原生框编辑与LS API同步属于同一审核用例',n,e)


def classes():
    labels=[('controller','ApplicationService\n────────────\nsubmitJob / reviewSample\npublishVersion / runExperiment',48,176,BLUE),('jobs','JobOrchestrator\n────────────\nclaimLease / heartbeat\nretry / cancel / checkpoint',464,176,BLUE),('engine','«interface» EnginePort\n────────────\nprepare(config)\nexecute(context) → StageResult',880,176,AMBER),('fds','FdsAdapter / BlenderAdapter\n────────────\n参数校验 / 子进程超时\n文件清单与物理代理说明',1296,176,GREEN),('review','ReviewService\n────────────\nimageSHA + annotationRevision\n人工修订 / 冲突检测',48,464,BLUE),('label','«interface» LabelPort\n────────────\ncreateTask / importRevision\nWebhook去重/项目校验',464,464,AMBER),('version','VersionService\n────────────\n冻结审核标签与分组\nprepare / commit / publish',880,464,BLUE),('dvc','«interface» VersionPort\n────────────\nDvcAdapter.prepare/push/verify\nGit SHA＋manifest SHA',1296,464,AMBER),('storage','«interface» StoragePort\n────────────\nput / get / signedDownload\nLocalVolume → SSH/S3',48,752,AMBER),('repo','Repository / UnitOfWork\n────────────\n项目隔离 / 乐观锁\nPG事务 / Outbox',464,752,AMBER),('eval','EvaluationService\n────────────\nFID / 物理误差 / YOLO对照\n版本、预算与参照快照',880,752,BLUE),('diff','Diffusion / Detection Adapter\n────────────\nSD1.5 / YOLO11n\n模型哈希、种子与真实结果',1296,752,GREEN)]
    n=[node(id,label,x,y,328,168,fill=fill) for id,label,x,y,fill in labels]
    e=[edge('controller','jobs','调用'),edge('jobs','engine','依赖端口'),edge('fds','engine','实现',endArrow='block',endFill=0),edge('review','label','依赖端口'),edge('version','dvc','依赖端口'),edge('controller','review','调用',exitX=.5,exitY=1,entryX=.5,entryY=0),edge('review','storage','读图像',exitX=.5,exitY=1,entryX=.5,entryY=0),edge('jobs','repo','持久状态',exitX=.5,exitY=1,entryX=.5,entryY=0),edge('version','eval','版本快照',exitX=.5,exitY=1,entryX=.5,entryY=0),edge('eval','diff','执行'),edge('diff','engine','实现',endArrow='block',endFill=0,dashed=1)]
    n.append(text('note','业务层不导入 bpy/torch；第三方调用只在适配器；Worker不直接写平台PG；重试复用已验证产物，审核/发布事务禁止静默降级',48,992,1664,64,18))
    save('04_UML类图','UML 设计类图与端口边界','类图表示目标设计接口；现有 Renderer、文件契约和算法函数可适配复用',n,e)


def states():
    n=[node('queued','queued\n幂等提交＋配额校验',48,240,240,104),node('running','running\nlease＋心跳＋检查点',400,240,272,104),node('done','succeeded\n产物完整并校验通过',832,240,272,104,fill=GREEN),node('retry','retry_wait\n有限次数＋指数退避',400,464,272,104,fill=AMBER),node('failed','failed\n留存日志/阶段/预算',832,464,272,104,fill=RED),node('cancel','cancel_requested\n停止派发＋终止子进程',1248,240,376,104,fill=AMBER),node('cancelled','cancelled\n保留已完成产物',1248,464,376,104,fill=GRAY),node('candidate','candidate\n未审核样本',48,752,272,104),node('reviewed','reviewed\n绑定图像SHA和标签修订',448,752,328,104),node('staging','dvc_pending\n冻结清单＋DVC备份核验',904,752,328,104,fill=AMBER),node('published','published\n不可变旧版本',1360,752,328,104,fill=GREEN)]
    e=[edge('queued','running','claim'),edge('running','done','全部阶段成功'),edge('running','retry','可重试错误',exitX=.5,exitY=1,entryX=.5,entryY=0),edge('retry','running','重新入队',exitX=0,exitY=.5,entryX=0,entryY=.7),edge('retry','failed','耗尽/不可恢复'),edge('done','cancel','完成后不接受取消',dashed=1,endArrow='none'),edge('running','cancel','取消请求',exitX=.7,exitY=0,entryX=.5,entryY=0),edge('cancel','cancelled','确认进程退出'),edge('candidate','reviewed','人工审核'),edge('reviewed','staging','质检＋授权＋分组通过'),edge('staging','published','DVC提交/备份成功')]
    n+=[text('joblabel','任务状态（执行成功不代表数据已审核）',48,152,1300,48,22),text('datalabel','样本/版本状态（与任务状态独立）',48,656,1400,48,22),text('note','增强生成新样本，状态重新为candidate；修改标签生成新修订，旧版本不变；DVC失败停留不可见暂存态并告警；迟到心跳必须核验lease代次',48,968,1664,80,18)]
    save('05_UML状态','UML 任务与数据发布状态机','不可把完成推理、生成候选框、人工审核、版本发布混成同一个“成功”',n,e)


CORE=[('project','project\nPK id\nname / owner_id'),('scene','scene_config\nPK id; FK project_id\nconfig_json / config_sha'),('job','job\nPK id; FK project_id, scene_id\nstatus / lease / idempotency'),('stage','job_stage\nPK id; FK job_id\nstage / attempt / image_digest'),('source','source_record\nPK id; FK project_id\nsource_uri / license / PIA'),('sample','sample\nPK id; FK job, source, parent\nimage_artifact / group / source_kind'),('annotation','annotation_revision\nPK id; FK sample_id\nimage_sha / revision / LS_id'),('box','label_box\nPK id; FK annotation_revision_id\nclass=fire / pixel xyxy'),('artifact','artifact\nPK id; FK project, job\nsha256 / uri / bytes / kind'),('review','review_decision\nPK id; FK annotation, reviewer\ndecision / image_sha / at'),('version','dataset_version\nPK id; FK project_id\nstate / manifest_sha / dvc_commit'),('item','version_sample\nPK id; UK(version_id, sample_id)\nFK annotation, review, quality\nsplit / group / frozen hashes')]
GOV=[('user','user_account\nPK id\npassword_hash / disabled'),('member','project_member\nPK (project_id, user_id)\nrole / granted_at'),('worker','worker_node\nPK id; FK service_user_id\ncapabilities / heartbeat / scope'),('audit','audit_event\nPK id; FK project, actor\nobject / action / result / at'),('model','model_asset\nPK id; FK project, source\nrevision / hash / license'),('experiment','experiment\nPK id; FK project, model\nkind / config / reference_uri'),('arm','experiment_arm\nPK id; FK experiment\ntrain/val/test_version / seed\nweight_sha / training_budget'),('metric','metric_result\nPK id; FK experiment, arm\nmetric / value / unit / config'),('quality','quality_result\nPK id; FK sample, annotation\nrule_version / pass / metrics'),('budget','budget_usage\nPK id; FK project, job\ntokens / GPU_s / bytes / price'),('evidence','delivery_evidence\nPK id; FK project, artifact\nrequirement_id / verified_at'),('export','export_record\nPK id; FK dataset_version\nformat / artifact / manifest_sha')]


def er(name,title,items,relations,footer):
    # Chen notation: entities, separate attributes, relationship diamonds, no crow's feet.
    attributes={
      'project':('项目','name','owner_id'),'scene':('场景配置','name','config_sha256'),
      'job':('任务','status','lease_generation'),'stage':('任务阶段','name','attempt'),
      'source':('数据来源','license_id','uri'),'sample':('样本','source_kind','group_id'),
      'annotation':('标签修订','revision','image_sha256'),'box':('标注框','class_name','x0'),
      'artifact':('产物','sha256','storage_uri'),'review':('审核决定','decision','reviewer_id'),
      'version':('数据集版本','version','state'),'item':('版本样本项','split','group_id'),
      'user':('用户','email','disabled'),'member':('项目成员','project_id','user_id'),
      'worker':('计算节点','capabilities','last_heartbeat'),'audit':('审计事件','action','created_at'),
      'model':('模型资产','revision','sha256'),'experiment':('评价实验','kind','status'),
      'arm':('实验组','name','seed'),'metric':('指标结果','name','value'),
      'quality':('质量结果','rule_version','passed'),'budget':('成本记录','quantity','amount_cny'),
      'evidence':('交付证据','requirement_id','status'),'export':('导出记录','format','manifest_sha256')}
    relation_names={('project','scene'):'配置',('scene','job'):'采用',('job','stage'):'分阶段',
      ('source','sample'):'提供',('sample','annotation'):'修订',('annotation','box'):'包含',
      ('artifact','sample'):'作为图像',('annotation','review'):'接受审核',('version','item'):'收录',
      ('sample','item'):'被引用',('user','member'):'加入',('user','worker'):'认证节点',
      ('user','audit'):'执行操作',('model','experiment'):'用于评价',('experiment','arm'):'设置',
      ('arm','metric'):'产生',('project','source'):'管理来源'}
    ordered=list(items)
    if name=='06_ER核心数据':
        lookup={a:b for a,b in items}
        ordered=[(a,lookup[a]) for a in ['project','scene','job','stage','source','sample','annotation','box','version','artifact','review','item']]
    n=[]; e=[]; positions={}
    def line(a,b,label='',**style):
        return edge(a,b,label,**dict({'endArrow':'none','startArrow':'none','edgeStyle':'none','rounded':0,'fontSize':18},**style))
    for i,(id,label) in enumerate(ordered):
        x=350+(i%4)*720; y=420+(i//4)*600; positions[id]=(x,y)
        chinese,a,b=attributes[id]; table=label.split('\n')[0]
        n.append(node(id,chinese+'\n'+table,x-120,y-40,240,80,fill=BLUE,shape='rectangle',rounded=0,fontSize=19))
        attrs=[('id',True), (a,False), (b,False)]
        if id=='member': attrs=[('project_id',True),('user_id',True),('role',False)]
        for k,(field,pk) in enumerate(attrs):
            dx,dy=[(-150,-150),(150,-150),(0,150)][k]
            aid=f'{id}_attr{k}'
            n.append(node(aid,field,x+dx-110,y+dy-34,220,68,type='user',shape='ellipse',rounded=0,fill='#FFFFFF',fontStyle=4 if pk else 0,fontSize=18))
            e.append(line(id,aid))
        if id=='stage':
            aid='stage_elapsed'
            n.append(node(aid,'耗时（派生）',x+150-110,y+150-34,220,68,type='user',shape='ellipse',fill='#FFFFFF',dashed=1,fontSize=18))
            # Keep the normal third attribute on the left, derived attribute on right.
            for item in n:
                if item['id']=='stage_attr2': item['bounds']['x']=x-150-110
            e.append(line(id,aid))
    for i,(a,b,cardinality) in enumerate(relations):
        ax,ay=positions[a]; bx,by=positions[b]; rid=f'rel_{i}'
        same_row=ay==by
        if same_row and abs(ax-bx)==720:
            rx=(ax+bx)/2; ry=ay; route=None
        elif ax==bx and abs(ay-by)==600:
            rx=ax+360; ry=(ay+by)/2; route=True
        else:
            # Long/cross-row relationships use the empty horizontal row gutters.
            ry=(ay+by)/2 if ay!=by else ay+300+(i%2)*70
            rx=(ax+bx)/2
            if a=='sample' and b=='item': rx=710; ry=1390
            if a=='user' and b=='worker': rx=710; ry=650
            if a=='user' and b=='audit': rx=1430; ry=720
            route=True
        n.append(node(rid,relation_names[(a,b)],rx-76,ry-48,152,96,type='decision',shape='rhombus',fill=AMBER,rounded=0,fontSize=18))
        ca,cb=cardinality.split(' → ')
        left=line(a,rid,ca); right=line(rid,b,cb)
        if route:
            left['style'].update(edgeStyle='orthogonalEdgeStyle',exitX=1,exitY=.8,entryX=0,entryY=.5)
            right['style'].update(edgeStyle='orthogonalEdgeStyle',exitX=1,exitY=.5,entryX=0,entryY=.8 if by<ry else .2)
            # Route through gaps between attributes, not through their ellipses.
            target_y=by+70 if by<ry else by-70
            left['waypoints']=[{'x':ax+120,'y':ay+70},{'x':ax+330,'y':ay+70},{'x':ax+330,'y':ry},{'x':rx-76,'y':ry}]
            right['waypoints']=[{'x':bx-330,'y':ry},{'x':bx-330,'y':target_y},{'x':bx-120,'y':target_y}]
            if ax==bx:
                left['style'].update(entryX=.5,entryY=0 if ay<by else 1)
                right['style'].update(exitX=.5,exitY=1 if ay<by else 0,entryX=1,entryY=.2 if ay<by else .8)
                source_y=ay+70 if ay<by else ay-70
                left['style']['exitY']=.8 if ay<by else .2
                left['waypoints']=[{'x':ax+120,'y':source_y},{'x':rx,'y':source_y}]
                right['waypoints']=[{'x':rx,'y':target_y},{'x':bx+120,'y':target_y}]
            if (a,b)==('sample','item'):
                left['style'].update(exitX=0,exitY=.8,entryX=.5,entryY=0)
                right['style'].update(exitX=.5,exitY=1,entryX=0,entryY=.2)
                left['waypoints']=[{'x':ax-120,'y':ay+70},{'x':rx,'y':ay+70}]
                right['waypoints']=[{'x':rx,'y':1530},{'x':bx-120,'y':1530}]
            if (a,b)==('user','audit'):
                left['style'].update(exitX=0,exitY=.8)
                left['waypoints']=[{'x':80,'y':ay+24},{'x':80,'y':ry},{'x':rx-76,'y':ry}]
        e.extend([left,right])
    if name=='07_ER治理评价':
        # Repeat referenced entities as context: no duplicate database tables.
        references=[('quality','ref_sample','样本\nsample（跨图）','检验'),('budget','ref_job','任务\njob（跨图）','计量'),('evidence','ref_artifact','产物\nartifact（跨图）','引用证据'),('export','ref_version','数据集版本\ndataset_version（跨图）','导出自')]
        for owner,ref,label,rel in references:
            x,y=positions[owner]; rid=f'{owner}_context_rel'
            n.append(node(ref,label,x-120,2180,240,80,shape='rectangle',rounded=0,fill=GRAY,fontSize=19))
            n.append(node(rid,rel,x+360-76,1920-48,152,96,type='decision',shape='rhombus',rounded=0,fill=AMBER,fontSize=18))
            first=line(owner,rid,'0..N',exitX=1,exitY=.8,entryX=.5,entryY=0,edgeStyle='orthogonalEdgeStyle')
            first['waypoints']=[{'x':x+120,'y':y+70},{'x':x+360,'y':y+70}]
            second=line(rid,ref,'0..1' if owner=='budget' else '1',exitX=.5,exitY=1,entryX=1,entryY=.2,edgeStyle='orthogonalEdgeStyle')
            second['waypoints']=[{'x':x+360,'y':2150},{'x':x+120,'y':2150}]
            e.extend([first,second])
    n.append(text('notation','Chen标准：矩形=实体；椭圆=属性；菱形=联系；下划线=主键；连线两端标基数（0..N可为零）。\n实体仅展示代表属性，完整字段与全部外键见schema.design.sql；跨图联系见下述映射，不能把外键属性当作联系菱形。',48,2080,2840,96,21))
    n.append(text('footer',footer,48,2212,2840,112,20))
    n.append(text('normalization','本模型UUID实体可独立标识，不强加弱实体双矩形；多值数据已拆表，不强加双椭圆。阶段耗时由起止时间计算，使用虚线椭圆且不入库。',48,2356,2840,64,20))
    if name=='07_ER治理评价':
        for item in n:
            if item['id'] in {'notation','footer','normalization'}: item['bounds']['y']+=480
    save(name,title,'Chen概念ER图（目标设计）；主键与属性已分离；关系无方向箭头，外键及项目隔离约束以SQL草案为准',n,e,w=3040,h=2944 if name=='07_ER治理评价' else 2464)


def pert(cost_view=False):
    # Columns follow dependency depth; long edges are routed above/below nodes.
    positions={'A':(48,480),'B':(352,480),'C':(656,160),'D':(656,480),'E':(656,800),'F':(656,1120),'G':(960,1120),'H':(960,800),'I':(1264,480),'J':(1264,1120),'K':(1568,800),'L':(1872,1120),'M':(1872,480),'N':(2176,800),'P':(2176,160),'O':(2480,800),'Q':(2784,480)}
    n=[]; by={x['id']:x for x in EST['tasks']}
    for t in EST['tasks']:
        x,y=positions[t['id']]
        name=t['name']; title=name if len(name)<=13 else name[:12]+'\n'+name[12:]
        label=f"{t['id']}  {title}\nD={t['D']:g}  ES={t['ES']:g}  ED={t['ED']:g}\nLS={t['LS']:g}  LE={t['LE']:g}\nTF={t['TF']:g}  FF={t['FF']:g}  人时={t['hours']:g}"
        if cost_view:
            label=f"{t['id']} {title}\n{'/'.join(t['roles'])}  {t['hours']:g}人时\n人工：Σ角色人时×角色单价\n资源：用量×待定单价\nD={t['D']:g} 资源[{t['resource_start']},{t['resource_finish']})"
        n.append(node(t['id'],label,x,y,256,256,type='user',fill=RED if t['critical'] else BLUE,fontSize=14))
    e=[]
    for t in EST['tasks']:
        for d in t['dependencies']:
            critical=t['critical'] and by[d]['critical'] and by[d]['ED']==t['ES']
            connection=edge(d,t['id'],strokeColor='#B42318' if critical else '#64748B',strokeWidth=3 if critical else 1.5,exitX=1,exitY=.5,entryX=0,entryY=.5)
            sx,sy=positions[d]; tx,ty=positions[t['id']]
            if sy!=ty: connection['waypoints']=[{'x':tx-24,'y':sy+128},{'x':tx-24,'y':ty+128}]
            if (d,t['id'])==('E','J'):
                connection['waypoints']=[{'x':784,'y':1088},{'x':1240,'y':1088},{'x':1240,'y':1248}]
                connection['style'].update(exitX=.5,exitY=1)
            if (d,t['id'])==('G','L'):
                connection['waypoints']=[{'x':1088,'y':1424},{'x':1848,'y':1424},{'x':1848,'y':1248}]
                connection['style'].update(exitX=.5,exitY=1)
            e.append(connection)
    n += [text('summary',f"关键路径：{' → '.join(EST['critical_tasks'])} = {EST['logical_finish']:g}工作日\n资源平衡后 {EST['resource_finish']}日 ＋ 项目缓冲 {EST['project_buffer']}日 = 承诺 {EST['planned_commitment']}日；14周/70工作日内余量 {EST['deadline_slack']}日",48,1480,3000,96,24),text('legend','ED=最早完成（EF）；LE=最迟完成（LF）；D=PERT期望工期；TF=总时差；FF=自由时差。CPM不含资源约束，人员平衡结果另列CSV。',48,1616,3000,56,20)]
    if cost_view:
        n=[item for item in n if item['id'] not in {'summary','legend'}]
        n += [text('summary',f"总人时：{EST['labor_hours']:g}h；人工成本＝Σ全部节点的角色人时×待定角色单价\n资源成本＝GPU时＋云CPU时＋存储/备份/出网＋电量＋输入/输出token用量，各乘对应待定单价\n总成本＝全部17节点人工与资源成本＋经确认的成本储备；当前不填金额、单价或货币预算\n56日资源排程＋9日时间缓冲＝65工作日；只求关键路径成本会漏算其他必要分支",48,1056,3000,156,21),text('legend','PM产品经理 / AR架构师 / DEV开发工程师 / QA测试师 / OPS运维师；均按3h/工作日。用量和价格分别记录；时间缓冲不等于已支付的成本储备。',48,1224,3000,56,19)]
        for item in n:
            if item['id']=='summary': item['bounds']['y']=1480
            if item['id']=='legend': item['bounds']['y']=1680
        save('09_成本与资源','PERT 任务成本网络（五人固定角色）','与工期图使用相同圆形节点和依赖；节点成本=指定人员实际人时×单价＋归属现金＋硬件摊销；红色为逻辑关键路径',n,e,w=3104,h=1776)
    else:
        save('08_PERT网络','PERT / CPM 任务依赖与关键路径','五人固定角色，3h/人/工作日；时间从0起算；红色为逻辑关键路径；人员互斥后的可行排程另列CSV',n,e,w=3104,h=1728)


def main():
    framework(); architecture(); usecase(); classes(); states()
    er('06_ER核心数据','ER 图：生成、标注与数据版本',CORE,[('project','scene','1 → 0..N'),('scene','job','1 → 0..N'),('job','stage','1 → 0..N'),('source','sample','1 → 0..N'),('sample','annotation','1 → 0..N'),('annotation','box','1 → 0..N'),('artifact','sample','1 → 0..N'),('annotation','review','1 → 0..N'),('version','item','1 → 0..N'),('sample','item','1 → 0..N'),('project','source','1 → 0..N')],'补充关系：job→sample/artifact；sample.parent_sample_id→sample；version_sample冻结annotation/review/quality，不读取“最新标签”；每个外键均做项目隔离校验。')
    er('07_ER治理评价','ER 图：权限、评价、预算与交付证据',GOV,[('user','member','1 → 0..N'),('user','worker','1 → 0..N'),('user','audit','0..1 → 0..N'),('model','experiment','0..1 → 0..N'),('experiment','arm','1 → 0..N'),('arm','metric','0..1 → 0..N'),('quality','budget','无直接业务关系')][:6],'跨图关系：member→project；quality→sample/annotation；arm→train/val/test version；budget→job；evidence→artifact；export→dataset_version。审计只追加，成本记录计量口径与单价快照。')
    pert(); pert(cost_view=True)
    print(f'Wrote {len(list(TMP.glob("*.spec.yaml")))} canonical specs in {TMP}')


if __name__=='__main__': main()
