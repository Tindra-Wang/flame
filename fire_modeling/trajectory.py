"""Physical observations and a causal, untrained centroid extrapolation baseline."""
from pathlib import Path
import numpy as np
from .io import read_json,resolve_artifact,sha256


def next_position(history):
    """Use only the contiguous observed prefix; never inspect a future field."""
    if len(history)<3 or any(r['centroid_m'] is None for r in history[-3:]):
        return {'available':False,'reason':'需要连续3个含燃烧区域的时间点'}
    rows=history[-3:];times=np.array([r['time_s'] for r in rows],dtype=float)
    if np.any(np.diff(times)<=0):raise ValueError('时间必须严格递增')
    xyz=np.array([r['centroid_m'] for r in rows]);t=times-times[-1]
    velocity=np.linalg.lstsq(np.column_stack([t,np.ones(3)]),xyz,rcond=None)[0][0]
    horizon=float(times[-1]-times[-2])
    return {'available':True,'method':'causal_linear_centroid_v1','trained':False,
            'issued_at_s':float(times[-1]),'target_time_s':float(times[-1]+horizon),
            'centroid_m':(xyz[-1]+velocity*horizon).tolist(),'velocity_m_s':velocity.tolist(),
            'history_times_s':times.tolist(),'limitation':'仅燃烧重心短时线性外推；不是FDS续算或已训练火势预测模型'}


def trajectory(physics:Path):
    volume=physics/'volume';manifest=volume/'volume.json'
    if not manifest.is_file() or not (physics/'handoff.json').is_file():return {'available':False,'reason':'FDS三维场尚未完成导出；等待求解，不显示虚构位置'}
    report=read_json(manifest);handoff=read_json(physics/'handoff.json')
    if sha256(manifest)!=handoff['volume_sha256']:raise ValueError('三维场清单校验失败')
    frames=[];bounds=None
    for entry in report['frames']:
        path=resolve_artifact(volume,entry['file'])
        if sha256(path)!=entry['sha256']:raise ValueError('三维场帧校验失败')
        with np.load(path,allow_pickle=False) as data:
            axes=[np.asarray(data[k+'_m']) for k in 'xyz'];heat=np.maximum(data['hrrpuv_kw_m3'],0)
            if not np.isfinite(heat).all():raise ValueError('物理场含非有限值')
            if frames and entry['time_s']<=frames[-1]['time_s']:raise ValueError('时间必须严格递增')
            bounds=[[float(a[0]),float(a[-1])] for a in axes]
            weight=float(heat.sum());active=heat>1.0
            centroid=[float((heat.sum(axis=tuple(j for j in range(3) if j!=i))*a).sum()/weight) for i,a in enumerate(axes)] if weight>1e-9 and active.any() else None
            indices=np.where(active)
            bbox=[[float(a[idx.min()]),float(a[idx.max()])] for a,idx in zip(axes,indices)] if active.any() else None
            cell=float(np.prod([float(np.diff(a)[0]) for a in axes]))
            row={'time_s':float(entry['time_s']),'centroid_m':centroid,'reaction_bbox_m':bbox,
                 'reaction_volume_m3':float(active.sum()*cell),'max_temperature_c':float(data['temperature_c'].max()),
                 'max_hrrpuv_kw_m3':float(heat.max()),'volume_sha256':entry['sha256']}
        frames.append(row);row['forecast']=next_position(frames)
    for i,row in enumerate(frames):
        next_row=frames[i+1] if i+1<len(frames) else None
        row['fds_next']={'available':next_row is not None,'method':'fds_conditioned_simulation','target_time_s':next_row['time_s'] if next_row else None,'centroid_m':next_row['centroid_m'] if next_row else None,'max_temperature_c':next_row['max_temperature_c'] if next_row else None,'source_volume_sha256':next_row['volume_sha256'] if next_row else None,'limitation':'已完成FDS工况的下一求解帧；不是观测驱动预测，不作为预测模型输入'}
    sequences=[{'input_indices':list(range(i-2,i+1)),'target_index':i+1} for i in range(2,len(frames)-1)]
    return {'schema':'ai07.temporal-training.v1','available':True,'source':'FDS','frames':frames,'bounds_m':bounds,
            'training_windows':sequences,'split_group':'simulation_id','volume_manifest_sha256':sha256(manifest),
            'coordinate_system':'场景世界坐标，米；Z向上',
            'reaction_threshold_kw_m3':1.0,'position_definition':'HRRPUV加权燃烧重心；不是最外层火焰前沿',
            'training_note':'历史帧为输入，下一时刻FDS场为仿真监督目标；forecast不是训练真值。同一工况及增强派生图须同组划分，真实泛化待独立评价。'}
