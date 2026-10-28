"""Shared scene contract for the original 3D editor, FDS and Blender.

No database/HTTP dependencies. The provided editor source stays unmodified.
"""
import importlib
import json
import math
import os
from pathlib import Path
import sys
import types

SCHEMA='ai07.editor-scene.v1'


def upstream():
    path=Path(__file__).resolve().parents[1]/'integrations/firephantom'
    os.environ.setdefault('FIREPHANTOM_ASSETS',str(Path(__file__).resolve().parents[1]/'artifacts/scene-assets'))
    if str(path) not in sys.path: sys.path.insert(0,str(path))
    # The upstream physics __init__ imports its Unix-only full engine. Reuse
    # the pure scene modules as a namespace, without importing that engine.
    if 'firephantom.physics' not in sys.modules:
        namespace=types.ModuleType('firephantom.physics')
        namespace.__path__=[str(path/'firephantom/physics')]
        sys.modules['firephantom.physics']=namespace
    return importlib.import_module('firephantom.physics.placements')


def normalize_scene(raw):
    if raw is None:return None
    if not isinstance(raw,dict) or len(json.dumps(raw,allow_nan=False))>100000:
        raise ValueError('三维场景必须是≤100KB的对象')
    allowed={'schema','revision','scenario','origin_fuel','placements','origin','cameras','gas_domain','simulation','structures','domain','lights','viewpoints'}
    if set(raw)-allowed:raise ValueError('未知的三维场景字段')
    if raw.get('schema',SCHEMA)!=SCHEMA:raise ValueError('三维场景版本不支持')
    module=upstream()
    scenario=raw.get('scenario','房间火灾');fuel=raw.get('origin_fuel','木材')
    if fuel not in module.FUELS:raise ValueError('未知燃烧物')
    views=raw.get('viewpoints') or ['侧视']
    if not isinstance(views,list) or not 1<=len(views)<=3 or len(set(views))!=len(views):raise ValueError('请选择1至3个不同视角')
    spec,domain,structures,origin=module.prepared_spec(scenario,raw.get('domain'),raw.get('structures'),raw.get('origin'))
    module.normalize_placements(spec,raw.get('placements',[]),fuel)
    placements=[{k:v for k,v in p.items() if k in {'asset_id','name','x','y','z','yaw','fuel_type','ignition','size'}} for p in raw.get('placements',[])]
    preview=module.layout_preview(scenario,placements,fuel,origin=origin,cameras=raw.get('cameras'),
        gas_domain_override=raw.get('gas_domain'),viewpoints=views,lights=raw.get('lights'),
        simulation=raw.get('simulation'),frame_count=1,structures=structures,domain=domain)
    for item in placements:
        if item.get('fuel_type',fuel) not in module.FUELS:raise ValueError('未知模型燃烧物')
        ident=str(item.get('asset_id',''))
        if ident.startswith('upload:') and not __import__('re').fullmatch(r'upload:[0-9a-f]{16}',ident):raise ValueError('模型标识不合法')
    revision=raw.get('revision',0)
    if type(revision)!=int or not 0<=revision<=100000:raise ValueError('场景修订号不合法')
    return {'schema':SCHEMA,'revision':revision,'scenario':scenario,'origin_fuel':fuel,'placements':placements,
            'origin':list(preview['origin']),'domain':list(spec.domain),'structures':structures,
            'cameras':preview['cameras'],'viewpoints':views,'gas_domain':raw.get('gas_domain'),
            'simulation':raw.get('simulation'),'lights':raw.get('lights')}


def resolved_scene(raw):
    scene=normalize_scene(raw);module=upstream()
    spec,*_=module.prepared_spec(scene['scenario'],scene['domain'],scene['structures'],scene['origin'])
    return scene,spec


def bind_config(base,raw):
    """Map editor meters to the solver grid; never silently move the saved origin."""
    from .config import SceneConfig
    scene,spec=resolved_scene(raw);config=dict(base)
    dx=float(config.get('cell_size_m',.2))
    size=tuple(round(n/dx)*dx for n in spec.domain)
    center=tuple(round(n/dx)*dx for n in spec.origin[:2])
    fire_size=tuple(max(2*dx,round(n/(2*dx))*2*dx) for n in config.get('fire_size_m',[.4,.4]))
    config.update(editor_scene=scene,room_size_m=size,fire_center_m=center,fire_size_m=fire_size,
                  scene_type='indoor' if scene['scenario']=='房间火灾' else 'outdoor',camera_angles_deg=[25.,65.,90.][:len(scene['viewpoints'])])
    if config['scene_type']=='indoor':config['wind_m_s']=0
    return SceneConfig.from_dict(config)


def solver_boxes(config):
    scene,spec=resolved_scene(config.editor_scene);module=upstream();dx=config.cell_size_m
    result=[]
    for i,box in enumerate(spec.obstacles):
        if box.role=='ignition':continue
        # role='fuel'（如罐体）是可燃结构，必须作为燃烧体进入求解；旧实现误将其当惰性实体
        result.append({'name':f'structure_{i}','bounds':list(box.xb),'fuel':scene['origin_fuel'] if box.role=='fuel' else None})
    for i,item in enumerate(module.normalize_placements(spec,scene['placements'],scene['origin_fuel'])):
        result.append({'name':f'object_{i}','bounds':item['xb'],'fuel':item.get('fuel_type') if item.get('ignition') else None})
    snapped=[]
    for box in result:
        bounds=[max(0,min(config.room_size_m[k//2],round(n/dx)*dx)) for k,n in enumerate(box['bounds'])]
        if all(bounds[k+1]-bounds[k]>=dx*.9 for k in (0,2,4)):
            snapped.append({**box,'bounds':bounds})
    return snapped


def editor_fds_input(config):
    from dataclasses import replace
    from .physics import fds_input
    from firephantom.physics.fields import fuel_properties
    scene,spec=resolved_scene(config.editor_scene)
    boxes=solver_boxes(config)
    dx=config.cell_size_m;x0,x1,y0,y1=config.burner_bounds
    z=max(0,min(config.room_size_m[2]-dx,round(spec.origin[2]/dx)*dx))
    def _buries_burner(b):
        # 3D 判定：仅当实体在起火点所在高度真实占据该位置才算掩埋（天花板/高处结构不误伤）
        a=b['bounds']
        if a[0]>=x1 or a[1]<=x0 or a[2]>=y1 or a[3]<=y0:return False
        return a[4]<=z<a[5]
    ignited=[b for b in boxes if b['fuel']]
    buried=any(_buries_burner(b) for b in boxes)
    auto_note=None
    if buried and not ignited:
        # 保火回退：起火点被埋但用户摆放了可燃物（未勾点燃）→ 把火落到离起火点最近的可燃物上
        cx=(x0+x1)/2;cy=(y0+y1)/2
        flammable=[(i,p) for i,p in enumerate(scene['placements']) if p.get('fuel_type')]
        if flammable:
            idx,placed=min(flammable,key=lambda ip:(ip[1]['x']-cx)**2+(ip[1]['y']-cy)**2)
            patch=dict(scene['placements'][idx]);patch['ignition']=True
            patched=[*scene['placements'][:idx],patch,*scene['placements'][idx+1:]]
            boxes=solver_boxes(replace(config,editor_scene={**config.editor_scene,'placements':patched}))
            ignited=[b for b in boxes if b['fuel']]
            auto_note=f"起火点被结构掩埋；已自动将火源落到最近可燃物「{placed.get('name') or placed.get('asset_id')}」"
        else:
            raise ValueError('起火点被结构/物件掩埋，且场景中没有任何可燃物可以承接火源——请移动起火点、移开结构或添加一件可燃物后再提交')
    use_auto=not buried
    burners=len(ignited)+(1 if use_auto else 0)
    base=fds_input(replace(config,editor_scene=None,scene_type='outdoor',peak_hrr_kw=config.peak_hrr_kw/burners))
    lines=[line for line in base.splitlines() if not (line.startswith('&VENT XB=') and "SURF_ID='BURNER'" in line) and not line.startswith('&TAIL')]
    if not use_auto:
        lines=[line for line in lines if "SURF_ID='BURNER'" not in line]
    soot=fuel_properties(scene['origin_fuel'])['soot_yield']
    lines=[line.replace('SOOT_YIELD=0.01',f'SOOT_YIELD={soot:g}') for line in lines]
    if use_auto:
        if z>0:lines.append(f"&OBST ID='origin_support', XB={x0:g},{x1:g},{y0:g},{y1:g},0,{z:g}, SURF_ID='INERT' /")
        lines.append(f"&VENT XB={x0:g},{x1:g},{y0:g},{y1:g},{z:g},{z:g}, SURF_ID='BURNER' /")
    for i,box in enumerate(boxes):
        bounds=','.join(f'{n:g}' for n in box['bounds']);surface='INERT'
        if box['fuel']:
            a=box['bounds']
            if box['name'].startswith('structure_'):
                # 顶面＋四侧全部燃烧：按真实燃烧面积分摊，保证总 HRR 回到标称值
                w,d,h=a[1]-a[0],a[3]-a[2],a[5]-a[4];area=w*d+2*(w*h+d*h)
            else:
                area=(a[1]-a[0])*(a[3]-a[2])
            surface=f'IGNITION_{i}'
            lines.append(f"&SURF ID='{surface}', HRRPUA={config.peak_hrr_kw/burners/area:g}, RAMP_Q='FIRE_RAMP' /")
            if box['name'].startswith('structure_'):
                # 可燃结构（罐体/油池等）顶面与四周全部燃烧，火包住结构，任何机位可见
                lines.append(f"&OBST ID='{box['name']}', XB={bounds}, SURF_IDS='{surface}','{surface}','INERT' /")
            else:
                lines.append(f"&OBST ID='{box['name']}', XB={bounds}, SURF_IDS='{surface}','INERT','INERT' /")
        else:lines.append(f"&OBST ID='{box['name']}', XB={bounds}, SURF_ID='INERT' /")
    if auto_note:
        lines.insert(0,f'! {auto_note}')
    lines.extend(["&TAIL /",''])
    return '\n'.join(lines)
