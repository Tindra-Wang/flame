"""FDS -> fdsreader -> bounded, versioned web data. No renderer dependencies."""
from importlib.metadata import version
from pathlib import Path
import re

import numpy as np

from .io import read_json, sha256, write_json
from .physics import read_hrr

SCHEMA = 'ai07.simulation.v1'
FIELDS = {'temperature': ('TEMPERATURE', '温度'),
          'soot': ('SOOT DENSITY', '烟炱密度'),
          'velocity': ('VELOCITY', '速度大小')}


def export_simulation(directory: Path) -> dict:
    """Read only locally generated FDS output; never deserialize a pickle cache."""
    import fdsreader

    execution = read_json(directory / 'execution.json')
    if execution.get('status') != 'success':
        raise ValueError('FDS尚未成功结束，不能导出结果')
    if len(list(directory.glob('*.smv'))) != 1:
        raise ValueError('需要唯一的FDS .smv结果')
    fdsreader.settings.ENABLE_CACHING = False
    fdsreader.settings.DEBUG = True
    sim = fdsreader.Simulation(str(directory))
    csv = directory / (Path(execution['input']).stem + '_hrr.csv')
    times, hrr = read_hrr(csv)
    selected = np.unique(np.linspace(0, len(times)-1, min(301, len(times))).astype(int))
    report = {'schema': SCHEMA, 'status': 'success', 'solver': 'FDS',
              'reader': {'name': 'fdsreader', 'version': version('fdsreader')},
              'hrr': [{'time_s': float(times[i]), 'kw': float(hrr[i])} for i in selected],
              'fields': [], 'plane': 'XZ',
              'limitation': '实际FDS中心切片；浏览器抽样显示，不是三维全场重建，也不是独立精度验收。'}
    out = directory / 'web'; out.mkdir(exist_ok=True)
    for key, (quantity, label) in FIELDS.items():
        slices = [s for s in sim.slices if s.quantity.name.upper() == quantity and s.orientation == 2]
        if len(slices) != 1:
            raise ValueError(f'缺少或存在歧义的XZ切片：{quantity}')
        slc = slices[0]
        data = slc.to_global()
        if data.ndim != 3 or data.size > 10_000_000 or not np.isfinite(data).all():
            raise ValueError('切片为空、过大或含非有限数据')
        coords = slc.get_coordinates()
        indices = np.unique(np.linspace(0, len(slc.times)-1, min(41,len(slc.times))).astype(int))
        xi = np.unique(np.linspace(0, data.shape[1]-1, min(96,data.shape[1])).astype(int))
        zi = np.unique(np.linspace(0, data.shape[2]-1, min(96,data.shape[2])).astype(int))
        frames=[]
        for index in indices:
            # Rows go bottom to top (z); columns go left to right (x).
            values = data[index][np.ix_(xi,zi)].T
            frame = {'schema': SCHEMA, 'field': key, 'time_s': float(slc.times[index]),
                     'x_m': [float(x) for x in coords['x'][xi]],
                     'z_m': [float(z) for z in coords['z'][zi]],
                     'values': values.tolist(), 'min': float(values.min()), 'max': float(values.max())}
            file = f'{key}-{len(frames)}.json'
            write_json(out / file, frame)
            frames.append({'time_s': frame['time_s'], 'file':file, 'sha256':sha256(out/file)})
        report['fields'].append({'id': key, 'name': label, 'quantity': quantity, 'unit': slc.quantity.unit,
                                 'min':float(data.min()), 'max':float(data.max()), 'frames':frames,
                                 'y_m':float(coords['y'][0]),'original_shape':list(data.shape),
                                 'display_shape':[len(zi),len(xi)], 'sampling':'nearest-grid; ≤41 frames, ≤96×96 nodes'})
    log = (directory / 'solver.log').read_text(encoding='utf-8',errors='replace')
    revision = re.search(r'Revision\s*:\s*(.+)', log)
    report['solver_revision'] = revision.group(1).strip() if revision else 'see solver.log'
    sources = [p for p in directory.iterdir() if p.is_file() and p.suffix in {'.fds','.smv','.sf','.csv'}]
    report['sources'] = [{'file':p.name,'sha256':sha256(p)} for p in sorted(sources)]
    write_json(out/'simulation.json',report)
    return report


def load_simulation(directory: Path) -> dict:
    if not (directory/'web/simulation.json').is_file():
        raise ValueError('仿真场结果尚不存在')
    report=read_json(directory/'web/simulation.json')
    if report.get('schema') != SCHEMA or report.get('status') != 'success':
        raise ValueError('仿真结果不完整或版本不受支持')
    if {f['id'] for f in report.get('fields',[])} != set(FIELDS):
        raise ValueError('仿真物理场不完整')
    return report
