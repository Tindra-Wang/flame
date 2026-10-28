import copy
from pathlib import Path
import numpy as np
import pytest
from PIL import Image,ImageDraw
from fire_modeling.synthesis_contracts import build_plan,fingerprint
from fire_modeling.controlled_augmentation import constrain
from fire_modeling.io import write_json,sha256,read_json


def source(id='a'*24):
    from fire_modeling.config import SceneConfig
    c=SceneConfig(width=64,height=64).to_dict();c['editor_scene']={'viewpoints':['侧视','俯视']}
    return {'id':id,'scene_id':'room','scene_revision':1,'config':c,'volume_manifest_sha256':'f'*64,
            'frames':[{'time_s':i,'file':f'{i}.npz','sha256':str(i)*64,'max_hrrpuv_kw_m3':10 if i else 0} for i in range(4)]}


def test_explicit_cartesian_coverage_no_synthetic_time_or_hidden_negatives():
    p=build_plan([source(),source('b'*24)],{'weathers':['clear','fog'],'viewpoints':['侧视','俯视'],'time_count':2,'modes':['background','flame']})
    assert len(p['items'])==16 and p['counts']['requested_augmented']==32
    assert len({i['sample_id'] for i in p['items']})==16
    assert {i['field']['time_s'] for i in p['items']}=={1,3}
    assert p['counts']['new_fds_solves']==0
    assert fingerprint(p)==fingerprint(build_plan([source(),source('b'*24)],p['options']))
    assert len(build_plan([source()],{'viewpoints':['第一人称']})['items'])==2
    with pytest.raises(ValueError,match='不足'):build_plan([source()],{'time_count':4})
    with pytest.raises(ValueError):build_plan([source()],{'time_count':float('nan')})


def test_augmentation_region_preserved_and_flame_candidate_recomputed():
    original=Image.new('RGB',(64,64),(20,20,20));mask=Image.new('L',(64,64));ImageDraw.Draw(mask).rectangle((25,20,35,45),fill=255)
    generated=Image.new('RGB',(64,64),(255,130,20))
    bg,label,checks=constrain(original,generated,mask,'background')
    assert np.array_equal(np.asarray(bg)[np.asarray(mask)>0],np.asarray(original)[np.asarray(mask)>0])
    assert checks['outside_edit_region_unchanged'] and np.array_equal(np.asarray(label),np.asarray(mask))
    flame,label,checks=constrain(original,generated,mask,'flame')
    assert np.asarray(flame)[0,0].tolist()==[20,20,20]
    assert np.asarray(label).sum()>np.asarray(mask).sum()
    assert 'recomputed' in checks['label_policy'] and not checks['physical_ground_truth']
    with pytest.raises(ValueError):constrain(original,Image.new('RGB',(64,64)),mask,'flame')


def test_render_cache_coverage_validation_and_source_field_integrity(tmp_path,monkeypatch):
    from fire_modeling import synthesis_pipeline as sp
    from fire_modeling.config import SceneConfig
    s=source();s['config']=SceneConfig(width=64,height=64).to_dict();s['config']['editor_scene']={'viewpoints':['侧视']}
    physics=tmp_path/'physics';(physics/'volume').mkdir(parents=True)
    for f in s['frames']:
        path=physics/'volume'/f['file'];path.write_bytes(bytes([int(f['time_s'])]));f['sha256']=sha256(path)
    monkeypatch.setattr(sp,'verify_source',lambda jobs,src:physics)
    # Isolate the engine adapter while exercising real manifests, hashes and masks.
    class Fake:
        calls=0
        def render(self,r):
            self.calls+=1;r.directory.mkdir(parents=True,exist_ok=True)
            Image.new('RGB',(64,64),(30+self.calls,40,50)).save(r.directory/'rgb.png')
            m=Image.new('L',(64,64));ImageDraw.Draw(m).rectangle((20,20,35,45),fill=255);m.save(r.directory/'mask.png')
            Image.new('L',(64,64),120).save(r.directory/'depth.png');(r.directory/'depth_m.exr').write_bytes(b'test-depth')
            write_json(r.directory/'render.json',{'route':'fds_openvdb_volume'})
    plan=build_plan([s],{'modes':[]});root=tmp_path/'job';root.mkdir();engine=Fake()
    m=sp.render_plan(root,plan,engine);assert len(m['samples'])==2 and engine.calls==3
    sp.render_plan(root,plan,engine);assert engine.calls==4 # only the fixed-frame baseline comparison
    payload={'plan':plan,'plan_hash':fingerprint(plan),'enhance':False}
    assert sp.validate_synthesis(root,payload)['raw']==2
    path=root/'render'/m['samples'][0]['mask'];path.write_bytes(b'changed')
    with pytest.raises(ValueError,match='控制'):sp.validate_synthesis(root,payload)
