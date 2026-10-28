"""Budget-aware starting meshes; never an FDS accuracy certificate."""
import math
from .editor_contract import bind_config,resolved_scene

CELL_SIZES=(.05,.0625,.075,.1,.125,.15,.2,.25,.3,.4,.5,.6,.625,.75,.8,1,1.25,1.5,2)


def recommend_mesh(base,raw,cell_budget=120000):
    scene,spec=resolved_scene(raw)
    temperature=float(base.get('ambient_temperature_c',20))+273.15
    power=float(base.get('peak_hrr_kw',100))
    if not math.isfinite(power) or power<=0 or not math.isfinite(temperature) or temperature<=0:raise ValueError('热释放率和环境温度不合法')
    # kW, kg/m3, kJ/(kg K), K, m/s2. This is a screening heuristic only.
    burners=1+sum(bool(p.get('ignition')) for p in scene['placements'])
    per_burner_power=power/burners
    dstar=(per_burner_power/(1.2*1.0*temperature*math.sqrt(9.81)))**.4
    burner=min(base.get('fire_size_m',[.8,.8]));target=min(dstar/4,burner/4)
    rows=[]
    for dx in CELL_SIZES:
        try:config=bind_config({**base,'cell_size_m':dx},scene)
        except ValueError:continue
        dims=[round(x/dx) for x in config.room_size_m]
        exact=all(abs(x/dx-round(x/dx))<1e-6 for x in spec.domain)
        cells=math.prod(dims);nodes=math.prod(n+1 for n in dims)
        rows.append({'cell_size_m':dx,'shape':dims,'cells':cells,'volume_nodes':nodes,'within_budget':cells<=cell_budget and nodes<=160000,
            'domain_exact':exact,'aligned_domain_m':list(config.room_size_m),'aligned_fire_size_m':list(config.fire_size_m),
            'dstar_over_dx':dstar/dx,'intended_burner_cells':burner/dx,'detail_starting_target_met':dx<=target+1e-9})
    feasible=[r for r in rows if r['within_budget']]
    exact=[r for r in feasible if r['domain_exact']]
    pool=exact or feasible
    if not pool:raise ValueError('场景无法在当前单网格预算内运行，请缩小求解域')
    detail=[r for r in pool if r['detail_starting_target_met']]
    chosen=max(detail,key=lambda r:r['cell_size_m']) if detail else min(pool,key=lambda r:r['cell_size_m'])
    desired=[r for r in rows if r['domain_exact'] and r['detail_starting_target_met']]
    desired=max(desired,key=lambda r:r['cell_size_m']) if desired else None
    warnings=[]
    if not chosen['detail_starting_target_met']:warnings.append('预算内仅适合粗略预览：火源/羽流解析度不足。建议缩小求解域或离线增加预算；增加图片像素不能恢复CFD细节。')
    if not chosen['domain_exact']:warnings.append('当前尺寸无法整除候选网格，作业将使用所示网格对齐域，请核对边界。')
    thin=sum(any(box.xb[i+1]-box.xb[i]<chosen['cell_size_m']-.00001 for i in (0,2,4)) for box in spec.obstacles if box.role!='ignition')
    if thin:warnings.append(f'{thin}块结构至少一边小于推荐网格，可能被网格吸附改变或丢失，请检查结构。')
    if max(abs(a-b) for a,b in zip(chosen['aligned_fire_size_m'],base.get('fire_size_m',[.8,.8])))>.05:warnings.append('火源尺寸将按网格对齐；请检查作业记录中的实际火源尺寸。')
    return {'schema':'ai07.mesh-recommendation.v1','scene_type':'indoor' if scene['scenario']=='房间火灾' else 'outdoor','burner_count':burners,'per_burner_peak_hrr_kw':per_burner_power,'domain_m':list(spec.domain),'recommended':chosen,
            'characteristic_fire_diameter_m':dstar,'target_cell_size_m':target,'detail_reference':desired,'cell_budget':cell_budget,
            'warnings':warnings,'candidates':rows,'basis':'场景域、火源尺度、峰值HRR与本机单网格预算；D*/dx及火源宽度各4格仅为项目初筛起点，不是通用验收阈值。',
            'limitation':'仍需针对关注的量做粗/中/细网格敏感性研究；未实施多网格局部加密，不能保证火焰纹理或物理误差。'}
