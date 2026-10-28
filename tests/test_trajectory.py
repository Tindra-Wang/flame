import numpy as np
import pytest
from fire_modeling.trajectory import next_position,trajectory
from fire_modeling.io import write_json,sha256


def test_forecast_is_causal_and_requires_contiguous_fire():
    history=[{'time_s':float(i),'centroid_m':[float(i),2.,1.]} for i in range(4)]
    a=next_position(history[:3]);assert a['target_time_s']==3
    assert a['centroid_m']==pytest.approx([3,2,1]) and not a['trained']
    history[3]['centroid_m']=[900,900,900]
    assert next_position(history[:3])==a
    assert not next_position(history[:2])['available']
    history[1]['centroid_m']=None
    assert not next_position(history[:3])['available']


def test_physical_observations_training_windows_and_integrity(tmp_path):
    out=tmp_path/'volume';out.mkdir();frames=[]
    for i in range(4):
        heat=np.zeros((5,4,3));heat[i,2,1]=10
        p=out/f'{i}.npz';np.savez_compressed(p,hrrpuv_kw_m3=heat,temperature_c=np.full(heat.shape,300+i),soot_kg_m3=heat*.001,x_m=np.arange(5),y_m=np.arange(4),z_m=np.arange(3))
        frames.append({'file':p.name,'time_s':float(i),'sha256':sha256(p)})
    write_json(out/'volume.json',{'frames':frames});write_json(tmp_path/'handoff.json',{'volume_sha256':sha256(out/'volume.json')})
    r=trajectory(tmp_path);assert r['frames'][2]['centroid_m']==[2,2,1]
    assert r['frames'][2]['reaction_volume_m3']==1
    assert r['frames'][2]['max_temperature_c']==302
    assert r['training_windows']==[{'input_indices':[0,1,2],'target_index':3}]
    assert r['frames'][2]['forecast']['centroid_m']==pytest.approx([3,2,1])
    assert r['frames'][2]['fds_next']['centroid_m']==[3,2,1]
    assert not r['frames'][-1]['fds_next']['available']
    (out/'0.npz').write_bytes(b'changed')
    with pytest.raises(ValueError,match='帧校验'):trajectory(tmp_path)


def test_unfinished_solver_returns_no_fake_observations(tmp_path):
    assert not trajectory(tmp_path)['available']


def test_fds_volume_output_uses_3d_slice_clock():
    from fire_modeling.physics import fds_input
    from fire_modeling.config import SceneConfig
    text=fds_input(SceneConfig(duration_s=20,output_frames=12))
    assert 'DT_SL3D=0.5' in text
