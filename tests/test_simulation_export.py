"""Verify physical-field orientation, time alignment and parser failure handling."""
from types import SimpleNamespace
import numpy as np
import pytest
from fire_modeling.io import write_json,read_json,sha256
from fire_modeling.simulation import export_simulation,load_simulation,FIELDS


@pytest.fixture
def simulation(tmp_path,monkeypatch):
    import fdsreader
    (tmp_path/'case.smv').write_text('parser fixture')
    (tmp_path/'case.fds').write_text('&TAIL /')
    (tmp_path/'case_hrr.csv').write_text('s,kW\nTime,HRR\n0,0\n1,100\n')
    (tmp_path/'solver.log').write_text('Revision : FDS-test\n')
    write_json(tmp_path/'execution.json',{'status':'success','input':'case.fds'})
    values=np.arange(12,dtype=float).reshape(2,2,3)
    slices=[SimpleNamespace(quantity=SimpleNamespace(name=q,unit='test'),orientation=2,times=np.array([0,1]),to_global=lambda:values,get_coordinates=lambda:{'x':np.array([0,1]),'y':np.array([.5]),'z':np.array([0,1,2])}) for q,_ in FIELDS.values()]
    monkeypatch.setattr(fdsreader,'Simulation',lambda _:SimpleNamespace(slices=slices))
    return tmp_path,values,slices


def test_export_preserves_time_units_and_xz_orientation(simulation):
    root,values,_=simulation
    report=export_simulation(root)
    assert report['solver_revision']=='FDS-test' and len(report['fields'])==3
    field=report['fields'][0];frame=read_json(root/'web'/field['frames'][1]['file'])
    assert frame['time_s']==1 and frame['values']==values[1].T.tolist()
    assert frame['x_m']==[0,1] and frame['z_m']==[0,1,2]
    assert field['frames'][1]['sha256']==sha256(root/'web'/field['frames'][1]['file'])
    assert load_simulation(root)['sources']


def test_export_rejects_nonfinite_physics_and_missing_field(simulation):
    root,values,slices=simulation
    values[0,0,0]=np.nan
    with pytest.raises(ValueError,match='非有限'):export_simulation(root)
    values[0,0,0]=0;slices.pop()
    with pytest.raises(ValueError,match='切片'):export_simulation(root)


def test_export_refuses_unsolved_data(simulation):
    root,_,_=simulation;write_json(root/'execution.json',{'status':'failed'})
    with pytest.raises(ValueError,match='未成功'):export_simulation(root)
    with pytest.raises(ValueError,match='不存在'):load_simulation(root)
