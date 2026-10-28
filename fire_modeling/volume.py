"""Lossless FDS 3D slices -> bounded NPZ contract -> Blender/OpenVDB.

Raw SI/solver units remain unchanged; appearance transfer happens in the renderer.
"""
from pathlib import Path
import numpy as np
from .io import read_json, write_json, sha256, resolve_artifact

SCHEMA = 'ai07.fds-volume.v1'
QUANTITIES = {'temperature_c': 'TEMPERATURE', 'soot_kg_m3': 'SOOT DENSITY', 'hrrpuv_kw_m3': 'HRRPUV'}


def validate_arrays(arrays, coordinates):
    shape = tuple(len(coordinates[k]) for k in ('x', 'y', 'z'))
    if min(shape) < 2 or np.prod(shape) > 160000:
        raise ValueError('三维网格尺寸超限或为空')
    for axis in coordinates.values():
        delta = np.diff(axis)
        if not np.isfinite(axis).all() or (delta <= 0).any() or not np.allclose(delta, delta[0], rtol=1e-4, atol=1e-6):
            raise ValueError('体积坐标必须有限、递增、均匀')
    steps = [float(np.diff(coordinates[k])[0]) for k in ('x', 'y', 'z')]
    if not np.allclose(steps, steps[0], rtol=1e-4, atol=1e-6):
        raise ValueError('当前OpenVDB交接仅支持等距立方网格')
    for key in QUANTITIES:
        value = arrays[key]
        if value.shape != shape or not np.isfinite(value).all():
            raise ValueError('体积数据形状或有限性校验失败')
        if key != 'temperature_c' and value.min() < -1e-7:
            raise ValueError('烟炱/热释放率不可为负')
    return shape


def export_volume(directory: Path,frame_count=None):
    import fdsreader
    if read_json(directory/'execution.json').get('status') != 'success':
        raise ValueError('FDS未成功，不可导出体积')
    fdsreader.settings.ENABLE_CACHING = False
    sim = fdsreader.Simulation(str(directory))
    fields = {}
    coordinates = times = None
    for key, quantity in QUANTITIES.items():
        matches = [s for s in sim.slices if s.orientation == 0 and s.quantity.name.upper() == quantity]
        if len(matches) != 1:
            raise ValueError(f'需要唯一完整三维场：{quantity}')
        slc = matches[0]
        value, coords = slc.to_global(return_coordinates=True)
        if value.ndim != 4 or value.size > 20000000:
            raise ValueError('体积场维度或时空预算超限')
        if coordinates is not None and (not np.array_equal(times, slc.times) or any(not np.allclose(coords[k], coordinates[k]) for k in coords)):
            raise ValueError('各物理场的时间/空间坐标未对齐')
        fields[key] = value
        coordinates = coords
        times = np.asarray(slc.times)
    out = directory/'volume'; out.mkdir(exist_ok=True)
    frames = []
    indices = np.unique(np.linspace(0, len(times)-1, min(frame_count or 41, len(times))).astype(int))
    for i in indices:
        arrays = {key: np.asarray(value[i], dtype=np.float32) for key, value in fields.items()}
        shape = validate_arrays(arrays, coordinates)
        path = out/f'frame-{i:04d}.npz'
        np.savez_compressed(path, **arrays, **{k+'_m': v for k,v in coordinates.items()})
        heat=np.maximum(arrays['hrrpuv_kw_m3'],0);weight=float(heat.sum())
        centroid=[float((heat.sum(axis=tuple(j for j in range(3) if j!=axis))*coordinates[key]).sum()/weight) for axis,key in enumerate(('x','y','z'))] if weight>1e-9 else None
        frames.append({'time_s': float(times[i]), 'file':path.name, 'sha256':sha256(path),
                       'max_hrrpuv_kw_m3':float(arrays['hrrpuv_kw_m3'].max()),'combustion_centroid_m':centroid})
    report = {'schema':SCHEMA, 'status':'success', 'axis_order':'XYZ', 'shape':list(shape),
              'quantities':QUANTITIES, 'frames':frames,
              'limitation':'真实FDS三维场；光学传递函数未物理标定，网格插值不会增加求解精度。'}
    write_json(out/'volume.json', report)
    return report


def select_frame(directory: Path, time_s: float):
    report = read_json(directory/'volume.json')
    if report.get('schema') != SCHEMA or report.get('status') != 'success':
        raise ValueError('不支持或不完整的体积交接')
    frames = report['frames']
    if not frames or not frames[0]['time_s'] <= time_s <= frames[-1]['time_s']:
        raise ValueError('请求时间不在体积求解覆盖范围内')
    entry = min(frames, key=lambda f: abs(f['time_s']-time_s))
    path = resolve_artifact(directory,entry['file'])
    if sha256(path) != entry['sha256']:
        raise ValueError('FDS三维场校验失败')
    return path, entry


def validate_volume_run(root: Path, config: dict):
    """Completion gate: source hashes, actual renderer, lineage and image integrity."""
    physics=root.parent/'physics'; handoff=read_json(physics/'handoff.json')
    from .config import SceneConfig
    if SceneConfig.from_dict(handoff['config']) != SceneConfig.from_dict(config):
        raise ValueError('求解与渲染场景配置不一致')
    if handoff.get('status')!='success' or sha256(resolve_artifact(physics,handoff['hrr_csv']))!=handoff['sha256']:
        raise ValueError('FDS源交接未通过')
    volume=resolve_artifact(physics,handoff['volume_manifest'])
    if sha256(volume)!=handoff['volume_sha256']: raise ValueError('三维场清单校验失败')
    manifest=read_json(root/'manifest.json')
    for sample in manifest['samples']:
        if sha256(resolve_artifact(root,sample['image']))!=sample['sha256']: raise ValueError('图像校验失败')
        entry=sample.get('physical_volume')
        if not entry or entry.get('backend')!='FDS': raise ValueError('缺少FDS三维场来源')
        _,actual=select_frame(volume.parent,entry['time_s'])
        if actual['sha256']!=entry['sha256']: raise ValueError('样本物理场来源不一致')
        if sample['parent_id'] is None:
            index=manifest['samples'].index(sample)
            # The enhanced manifest retains all original rows before its children.
            info=read_json(root.parent/'render/blender'/f'{index:05d}'/'render.json')
            if info.get('route')!='fds_openvdb_volume' or info.get('physical_backend')!='FDS':
                raise ValueError('禁止将参数化回退标记为三维场渲染成功')
