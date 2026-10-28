"""Recompute PERT/CPM, fixed-team resource leveling and transparent budget."""
import csv
import json
import math
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'docs/design'
ROLES={'PM':'产品经理','AR':'架构师','DEV':'开发工程师','QA':'测试师','OPS':'运维师'}
TASKS=[
 ('A','需求、数据授权与参照可用性',3,[],['PM','QA']),
 ('B','架构、ER与API契约',4,['A'],['AR']),
 ('C','测试/CI/Sonar骨架',4,['B'],['QA','OPS']),
 ('D','Web页面与交互骨架',5,['B'],['DEV']),
 ('E','API、账户与项目隔离',5,['B'],['DEV']),
 ('F','FDS/Blender建模与算法验证',8,['B'],['AR']),
 ('G','SD增强原型与可复现性',6,['F'],['AR']),
 ('H','异步任务、取消重试与预算',5,['E'],['DEV']),
 ('I','统一Web贯通与结果对比',5,['D','H','G'],['DEV']),
 ('J','Label Studio同步、审核与质检',5,['C','E'],['DEV','QA']),
 ('K','DVC冻结、版本与导出',4,['H','J'],['DEV']),
 ('L','真实数据与物理/检测评价',7,['G','J','K'],['AR','QA']),
 ('M','云预部署、监控告警与备份',5,['I','K'],['OPS']),
 ('N','全流程、性能安全与文档测试',6,['M','L'],['QA','DEV']),
 ('O','云Demo、手册、PPT与视频',4,['N'],['PM','OPS']),
 ('P','连续可用性观测与缺陷复核',7,['M'],['OPS']),
 ('Q','验收证据、追溯与交付',3,['O','P'],['PM','AR','DEV','QA','OPS']),
]


def calculate():
    rows=[]; by_id={}
    for id,name,m,deps,roles in TASKS:
        o=m-2; p=m+2; d=(o+4*m+p)/6
        es=max((by_id[x]['ED'] for x in deps),default=0)
        row=dict(id=id,name=name,optimistic=o,most_likely=m,pessimistic=p,D=d,variance=((p-o)/6)**2,dependencies=deps,roles=roles,ES=es,ED=es+d,hours=d*3*len(roles),labor_cost=None)
        rows.append(row); by_id[id]=row
    finish=max(t['ED'] for t in rows)
    for t in reversed(rows):
        succ=[x for x in rows if t['id'] in x['dependencies']]
        t['LE']=min((x['LS'] for x in succ),default=finish)
        t['LS']=t['LE']-t['D']; t['TF']=t['LS']-t['ES']
        t['FF']=min((x['ES'] for x in succ),default=finish)-t['ED']
        t['critical']=abs(t['TF'])<1e-9
    # Serial schedule generation; one task per person at a time, 3h/workday.
    calendars={r:set() for r in ROLES}
    for t in rows:
        start=int(max((by_id[x]['resource_finish'] for x in t['dependencies']),default=0))
        while any(day in calendars[r] for r in t['roles'] for day in range(start,start+int(t['D']))): start+=1
        t['resource_start']=start; t['resource_finish']=start+int(t['D'])
        for r in t['roles']: calendars[r].update(range(start,t['resource_finish']))
    leveled=max(t['resource_finish'] for t in rows)
    for t in rows:
        assert t['ED']==t['ES']+t['D'] and t['LE']==t['LS']+t['D']
        assert t['TF']>=0 and t['FF']>=0
        assert all(t['resource_start']>=by_id[d]['resource_finish'] for d in t['dependencies'])
    for role in ROLES:
        intervals=[t for t in rows if role in t['roles']]
        for i,a in enumerate(intervals):
            for b in intervals[i+1:]: assert a['resource_finish']<=b['resource_start'] or b['resource_finish']<=a['resource_start']
    project_buffer=math.ceil(leveled*.15)
    labor=sum(t['hours'] for t in rows)
    resource_plan=[
        dict(resource='cloud_cpu',quantity=28,unit='day',unit_price=None),
        dict(resource='gpu',quantity=24,unit='GPU_hour',unit_price=None),
        dict(resource='local_compute',quantity=100,unit='hour',unit_price=None),
        dict(resource='input_tokens',quantity=2,unit='million_token',unit_price=None),
        dict(resource='output_tokens',quantity=.3,unit='million_token',unit_price=None),
        dict(resource='storage_backup_egress',quantity=None,unit='GB_month_or_GB',unit_price=None),
        dict(resource='electricity',quantity=None,unit='kWh',unit_price=None),
    ]
    for t in rows:
        for key in ['labor_cost','cash_cost','token_cost','hardware_cost','total_cost']: t[key]=None
        t['cost_formula']='sum(role_hours * role_rate) + attributed_resource_usage * quoted_unit_price'
    result=dict(assumptions={'team':5,'roles':ROLES,'hours_per_person_per_workday':3,'deadline_workdays':70,'pricing_status':'unpriced; no currency amounts or assumed rates','scope':'remaining completion work; existing hardware and public weights reused'},tasks=rows,logical_finish=finish,resource_finish=leveled,project_buffer=project_buffer,planned_commitment=leveled+project_buffer,deadline_slack=70-leveled-project_buffer,critical_tasks=[t['id'] for t in rows if t['critical']],labor_hours=labor,role_hours={r:len(v)*3 for r,v in calendars.items()},resource_plan=resource_plan,cost_formulas={'labor':'sum over all tasks and roles: hours * role_rate','resource':'sum: metered_quantity * quoted_unit_price','reserve':'eligible_cash_cost * reserve_ratio','total':'sum all task costs + approved reserve; do not sum only critical path'},cash_base=None,cash_reserve=None,cash_ceiling=None,labor_imputed=None,hardware_imputed=None,total_economic=None)
    assert result['planned_commitment']<=70, 'Re-plan staffing or scope; do not hide overload'
    return result


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    data=calculate(); (OUT/'estimate.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    fields=['id','name','optimistic','most_likely','pessimistic','D','ES','ED','LS','LE','TF','FF','critical','resource_start','resource_finish','hours','labor_cost','cash_cost','token_cost','hardware_cost','total_cost','roles','dependencies']
    with (OUT/'PERT明细.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore'); w.writeheader(); w.writerows({**t,'roles':','.join(t['roles']),'dependencies':','.join(t['dependencies'])} for t in data['tasks'])
    with (OUT/'五角色人力成本.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.writer(f); w.writerow(['角色代码','角色','人数','实际任务人时','影子单价_元每小时','人力成本_元','参与工作包'])
        for role,name in ROLES.items():
            hours=data['role_hours'][role]
            w.writerow([role,name,1,hours,None,None,','.join(t['id'] for t in data['tasks'] if role in t['roles'])])
    print(json.dumps({k:v for k,v in data.items() if k not in {'tasks','cash_items'}},ensure_ascii=False,indent=2))


if __name__=='__main__': main()
