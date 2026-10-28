from types import SimpleNamespace
import numpy as np
import pytest
from PIL import Image
from fire_modeling.volume import QUANTITIES, export_volume, select_frame, validate_arrays
from fire_modeling.enhancement import protect_flame
from fire_modeling.io import write_json
from fire_modeling.io import sha256


def test_xyz_volume_contract_and_source_tampering(tmp_path,monkeypatch):
    import fdsreader
    coords={k:np.arange(3)*.1 for k in ('x','y','z')}
    data=np.zeros((2,3,3,3),dtype=np.float32); data[1,1,2,0]=123
    slices=[SimpleNamespace(orientation=0,quantity=SimpleNamespace(name=q),times=np.array([0.,1.]),
                            to_global=lambda **_: (data,coords)) for q in QUANTITIES.values()]
    monkeypatch.setattr(fdsreader,'Simulation',lambda _:SimpleNamespace(slices=slices))
    write_json(tmp_path/'execution.json',{'status':'success'})
    report=export_volume(tmp_path)
    assert report['shape']==[3,3,3] and report['axis_order']=='XYZ'
    path,entry=select_frame(tmp_path/'volume',.8)
    with np.load(path) as d: assert d['hrrpuv_kw_m3'][1,2,0]==123
    assert entry['time_s']==1
    assert entry['combustion_centroid_m']==pytest.approx([.1,.2,0])
    path.write_bytes(b'changed')
    with pytest.raises(ValueError,match='校验失败'):select_frame(tmp_path/'volume',.8)
    with pytest.raises(ValueError,match='覆盖范围'):select_frame(tmp_path/'volume',2)


@pytest.mark.parametrize('failure',['nan','axis','shape','negative'])
def test_invalid_physical_volume_fails_closed(failure):
    coords={k:np.arange(3,dtype=float)*.1 for k in ('x','y','z')}
    arrays={k:np.ones((3,3,3),dtype=float) for k in QUANTITIES}
    if failure=='nan':arrays['temperature_c'][0,0,0]=np.nan
    if failure=='axis':coords['z'][1]=-.1
    if failure=='shape':arrays['temperature_c']=np.ones((2,2,2))
    if failure=='negative':arrays['soot_kg_m3'][0,0,0]=-1
    with pytest.raises(ValueError):validate_arrays(arrays,coords)


def test_background_guard_restores_flame_and_keeps_background_editable():
    src=np.zeros((64,64,3),dtype=np.uint8); src[26:38,26:38]=[230,120,10]
    mask=np.zeros((64,64),dtype=np.uint8);mask[26:38,26:38]=255
    result=np.asarray(protect_flame(Image.fromarray(src),Image.new('RGB',(64,64),(70,90,100)),Image.fromarray(mask)))
    assert np.array_equal(result[17:47,17:47],src[17:47,17:47])
    assert tuple(result[0,0])==(70,90,100)
    with pytest.raises(ValueError):protect_flame(Image.fromarray(src),Image.fromarray(src),Image.new('L',(8,8)))


def test_completion_gate_rejects_proxy_backend_and_changed_frame(tmp_path):
    from fire_modeling.config import SceneConfig
    from fire_modeling.volume import SCHEMA, validate_volume_run
    config=SceneConfig(width=64,height=64).to_dict()
    physics=tmp_path/'physics'; root=tmp_path/'render'; volume=physics/'volume'; volume.mkdir(parents=True)
    frame=volume/'frame.npz'; frame.write_bytes(b'contract-fixture')
    entry={'time_s':4.,'file':'frame.npz','sha256':sha256(frame)}
    write_json(volume/'volume.json',{'schema':SCHEMA,'status':'success','frames':[entry]})
    csv=physics/'case_hrr.csv';csv.write_text('Time,HRR\n0,0\n5,100\n')
    write_json(physics/'handoff.json',{'config':config,'status':'success','hrr_csv':csv.name,'sha256':sha256(csv),
                                     'volume_manifest':'volume/volume.json','volume_sha256':sha256(volume/'volume.json')})
    root.mkdir();image=root/'frame.png';Image.new('RGB',(64,64)).save(image)
    write_json(root/'manifest.json',{'samples':[{'image':image.name,'sha256':sha256(image),'parent_id':None,
                   'physical_volume':{**entry,'backend':'FDS'}}]})
    info=root/'blender/00000/render.json';write_json(info,{'route':'fds_openvdb_volume','physical_backend':'FDS'})
    validate_volume_run(root,config)
    write_json(info,{'route':'mantaflow_proxy','physical_backend':'parameterized-plume'})
    with pytest.raises(ValueError,match='参数化回退'):validate_volume_run(root,config)
    frame.write_bytes(b'changed')
    with pytest.raises(ValueError,match='校验失败'):validate_volume_run(root,config)
