"""Connected Chen ER overview with native nodes and obstacle-aware routing."""
import heapq
import json
from pathlib import Path

from build_diagrams import node, text, edge, save, BLUE, AMBER

ROOT=Path(__file__).resolve().parents[2]
NAME='10_ER全局联系'
ENTITIES=[
 ('user','用户','user_account',320,320),('member','项目成员','project_member',960,320),
 ('project','项目','project',1600,320),('scene','场景配置','scene_config',2240,320),('job','任务','job',2880,320),
 ('audit','审计事件','audit_event',320,720),('worker','计算节点','worker_node',960,720),
 ('source','数据来源','source_record',1600,720),('artifact','产物','artifact',2240,720),('stage','任务阶段','job_stage',2880,720),
 ('model','模型资产','model_asset',320,1120),('experiment','评价实验','experiment',960,1120),
 ('sample','样本','sample',1600,1120),('annotation','标签修订','annotation_revision',2240,1120),('box','标注框','label_box',2880,1120),
 ('budget','成本记录','budget_usage',320,1520),('arm','实验组','experiment_arm',960,1520),
 ('quality','质量结果','quality_result',1600,1520),('review','审核决定','review_decision',2240,1520),('evidence','交付证据','delivery_evidence',2880,1520),
 ('metric','指标结果','metric_result',320,1920),('version','数据集版本','dataset_version',960,1920),
 ('item','版本样本项','version_sample',1600,1920),('export','导出记录','export_record',2240,1920),
]
# Parent entity, child entity, relationship, parent cardinality, child cardinality.
# Every entry is backed by the design DDL; optional references use 0..1.
RELATIONS=[
 ('user','member','加入','1','0..N'),('project','member','设成员','1','0..N'),
 ('project','scene','配置','1','0..N'),('scene','job','采用','0..1','0..N'),
 ('user','audit','执行操作','0..1','0..N'),('user','worker','认证节点','1','0..N'),
 ('project','source','管理来源','1','0..N'),('job','stage','分阶段','1','0..N'),
 ('job','artifact','产生文件','0..1','0..N'),('source','sample','提供','1','0..N'),
 ('source','model','授权模型','1','0..N'),('model','experiment','用于评价','0..1','0..N'),
 ('experiment','arm','设置','1','0..N'),('sample','annotation','修订','1','0..N'),
 ('annotation','box','包含','1','0..N'),('annotation','review','接受审核','1','0..N'),
 ('sample','quality','质量检查','1','0..N'),('quality','item','质量证据','1','0..N'),
 ('review','item','审核证据','1','0..N'),('version','item','收录','1','0..N'),
 ('sample','item','冻结样本','1','0..N'),('annotation','item','冻结标签','1','0..N'),
 ('version','arm','训练集','0..1','0..N'),('arm','metric','产生指标','0..1','0..N'),
 ('artifact','evidence','交付证据','1','0..N'),('version','export','导出','1','0..N'),
 ('job','budget','资源计量','0..1','0..N'),('project','budget','归属成本','1','0..N'),
 ('job','sample','生成样本','0..1','0..N'),('artifact','sample','图像文件','1','0..N'),
]

# Compact layout preserves native shape/text sizes; shorten spacing, not the text.
# Keep the generation/annotation/version spine together and put leaf entities nearby.
ENTITIES=[(id,zh,table,240+int((x-320)/640)*480,260+int((y-320)/400)*300)
          for id,zh,table,x,y in ENTITIES]
ENTITIES=[(id,zh,table,2160 if id=='budget' else x,
           1460 if id=='budget' else 1160 if id=='metric' else y)
          for id,zh,table,x,y in ENTITIES]
CANVAS_WIDTH=2440
ROUTE_BOTTOM=1680
DOMAIN_COLORS={
    **dict.fromkeys(['user','member','worker','audit'],'#F1F3F5'),
    **dict.fromkeys(['project','scene','job','stage','source','artifact'],BLUE),
    **dict.fromkeys(['sample','annotation','box','quality','review'],'#E9F4EE'),
    **dict.fromkeys(['version','item','export'],'#FFF2DB'),
    **dict.fromkeys(['model','experiment','arm','metric'],'#F0ECFA'),
    **dict.fromkeys(['budget','evidence'],'#F1F3F5'),
}


def overlaps(a,b,gap=16):
    return a[0]<b[2]+gap and a[2]>b[0]-gap and a[1]<b[3]+gap and a[3]>b[1]-gap


def main():
    nodes=[]; edges=[]; boxes={}; centers={}; usage={}
    def add(n):
        nodes.append(n); b=n['bounds']; boxes[n['id']]=(b['x'],b['y'],b['x']+b['width'],b['y']+b['height'])
        centers[n['id']]=(b['x']+b['width']/2,b['y']+b['height']/2)
    for id,zh,table,x,y in ENTITIES:
        add(node(id,zh+'\n'+table,x-120,y-40,240,80,shape='rectangle',rounded=0,fill=DOMAIN_COLORS[id],fontSize=18))
        pk='project_id / user_id' if id=='member' else 'id'
        add(node(id+'_pk',pk,x-100,y-120,200,48,type='user',shape='ellipse',fontStyle=4,fill='#FFFFFF',fontSize=16))
        edges.append(edge(id,id+'_pk',endArrow='none',startArrow='none',edgeStyle='none'))
    # Reserve all relationship diamonds before routing to prevent through-node edges.
    for i,(a,b,label,ca,cb) in enumerate(RELATIONS):
        ax,ay=centers[a]; bx,by=centers[b]
        mx=round((ax+bx)/40)*20; my=round((ay+by)/40)*20
        found=None
        for radius in range(0,1000,40):
            candidates=[(mx+dx,my+dy) for dx in range(-radius,radius+1,40) for dy in range(-radius,radius+1,40) if max(abs(dx),abs(dy))==radius]
            candidates.sort(key=lambda p:abs(p[0]-mx)+abs(p[1]-my))
            for x,y in candidates:
                rect=(x-60,y-40,x+60,y+40)
                if x<100 or x>CANVAS_WIDTH-100 or y<160 or y>ROUTE_BOTTOM-40: continue
                if not any(overlaps(rect,other,24) for other in boxes.values()): found=(x,y); break
            if found: break
        assert found, (a,b)
        x,y=found
        add(node(f'rel_{i}',label,x-60,y-40,120,80,type='decision',shape='rhombus',fill=AMBER,rounded=0,fontSize=16))

    def port(id,other):
        x,y=centers[id]; ox,oy=centers[other]; l,t,r,b=boxes[id]
        if abs(ox-x)>=abs(oy-y):
            return ((r+20,y),(1,.5)) if ox>x else ((l-20,y),(0,.5))
        return ((x,b+20),(.5,1)) if oy>y else ((x,t-20),(.5,0))

    # Coarse 20px A*; empty margins allow long cross-domain links to go around nodes.
    occupied=set()
    for l,t,r,b in boxes.values():
        for x in range(0,CANVAS_WIDTH+1,20):
            if l-8<=x<=r+8:
                for y in range(120,ROUTE_BOTTOM+1,20):
                    if t-8<=y<=b+8: occupied.add((x,y))

    def route(a,b,card):
        start,exit=port(a,b); goal,entry=port(b,a)
        start=tuple(int(round(v/20))*20 for v in start); goal=tuple(int(round(v/20))*20 for v in goal)
        blocked=occupied-{start,goal}; queue=[(0,0,start,None)]; best={start:0}; parents={}
        while queue:
            _,g,p,prev=heapq.heappop(queue)
            if g>best.get(p,float('inf')): continue
            if p==goal: break
            for dx,dy in [(20,0),(-20,0),(0,20),(0,-20)]:
                q=(p[0]+dx,p[1]+dy)
                if q in blocked or not(20<=q[0]<=CANVAS_WIDTH-20 and 120<=q[1]<=ROUTE_BOTTOM): continue
                turn=1 if prev and (p[0]-prev[0],p[1]-prev[1])!=(dx,dy) else 0
                cost=g+1+usage.get(q,0)*.4+turn*.15
                if cost<best.get(q,float('inf')):
                    best[q]=cost; parents[q]=p
                    h=(abs(q[0]-goal[0])+abs(q[1]-goal[1]))/20
                    heapq.heappush(queue,(cost+h,cost,q,p))
        assert goal in best, (a,b,start,goal)
        path=[goal]
        while path[-1]!=start: path.append(parents[path[-1]])
        path.reverse()
        for p in path: usage[p]=usage.get(p,0)+1
        points=[path[0]]
        for k in range(1,len(path)-1):
            if (path[k][0]-path[k-1][0],path[k][1]-path[k-1][1])!=(path[k+1][0]-path[k][0],path[k+1][1]-path[k][1]): points.append(path[k])
        points.append(path[-1])
        e=edge(a,b,card,endArrow='none',startArrow='none',fontSize=15,strokeWidth=1.5,exitX=exit[0],exitY=exit[1],entryX=entry[0],entryY=entry[1])
        e['waypoints']=[{'x':x,'y':y} for x,y in points]
        edges.append(e)
    for i,(a,b,label,ca,cb) in enumerate(RELATIONS):
        route(a,f'rel_{i}',ca); route(f'rel_{i}',b,cb)
    nodes.append(text('legend','24个实体、30个业务联系；矩形=实体，椭圆=主键，菱形=联系。灰：权限/工程；蓝：生成；绿：标注质检；黄：版本；紫：评价。\n全部实体连通；跨线弧不表示新联系。属性详图见06/07，完整字段和可选外键见schema.design.sql。',48,1720,2336,80,18))
    nodes.append(text('cross','核心关联：任务—样本/产物；版本—样本/标签/审核/质量；版本—实验组；任务—成本；产物—交付证据。\n实验组训练/验证/测试均引用版本实体；统一project_id隔离，图示业务联系不代表流水线执行顺序。',48,1832,2336,72,17))
    save(NAME,'AI-07 全局 ER 联系图（紧凑版）','按业务邻接收拢布局；保留24个实体、30个联系与标准Chen符号；实体和文字保持原尺寸',nodes,edges,w=CANVAS_WIDTH,h=1960)
    (ROOT/'docs/design/er-global-relations.json').write_text(json.dumps({'entities':[{'id':a,'table':c} for a,b,c,x,y in ENTITIES],'relations':RELATIONS,'connected_entity_count':24},ensure_ascii=False,indent=2),encoding='utf-8')
    print('Global Chen ER: 24 entities, 30 explicit relationships')


if __name__=='__main__': main()
