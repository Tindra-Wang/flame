"""Evaluation gates use deliberate test fixtures, never simulated acceptance scores."""
import copy
import pytest
from PIL import Image
from fire_modeling.io import read_json,write_json,sha256
from fire_modeling.evaluation_data import freeze_reviewed,prepare_detector_pair,detector_inputs,validate_pair_report
from fire_modeling.dataset import review


def version(root,source='real',splits=('train','val','test')):
    rows=[]
    for i,split in enumerate(splits):
        path=root/f'images/{i}.png';path.parent.mkdir(parents=True,exist_ok=True);Image.new('RGB',(64,64),(i*50+3,50 if source=='real' else 90,8)).save(path)
        rows.append({'sample_id':f'x{i}','source':source,'image':f'images/{i}.png','sha256':sha256(path),'width':64,'height':64,'boxes':[[3,4,15,16]],'annotation_status':'approved','group_id':f'{source}_{i}','split':split})
    write_json(root/'version.json',{'samples':rows});write_json(root/'checksums.json',{'version.json':sha256(root/'version.json')});return rows


def test_reviewed_snapshot_filters_and_freezes(tmp_path):
    root=tmp_path/'run';rows=version(root)
    rows.append({**rows[0],'sample_id':'enh','source':'diffusion','image':'images/enh.png'})
    Image.new('RGB',(64,64),'orange').save(root/'images/enh.png');rows[-1]['sha256']=sha256(root/'images/enh.png')
    write_json(root/'manifest.json',{'status':'success_candidates_only','samples':rows})
    with pytest.raises(ValueError,match='人工审核'):freeze_reviewed(root,tmp_path/'empty')
    for r in rows:review(root,r['sample_id'],'test-reviewer')
    snapshot=freeze_reviewed(root,tmp_path/'frozen','raw');assert len(snapshot['samples'])==3
    review(root,'x0','test-reviewer','rejected')
    assert len(read_json(tmp_path/'frozen/snapshot.json')['samples'])==3
    with pytest.raises(ValueError,match='至少'):freeze_reviewed(root,tmp_path/'few','enhanced')
    (root/'images/1.png').write_bytes(b'changed')
    with pytest.raises(ValueError,match='结构'):freeze_reviewed(root,tmp_path/'changed')


def test_detector_pair_preserves_real_holdout_and_rejects_group_leak(tmp_path):
    a=tmp_path/'real';b=tmp_path/'synthetic';version(a);rows=version(b,'diffusion',('train',))
    spec,lineage=prepare_detector_pair(a,b,tmp_path/'prepared',tmp_path/'weights.pt',{'epochs':1})
    assert lineage['counts']=={'train':1,'val':1,'test':1,'synthetic_train':1}
    assert (tmp_path/'prepared/baseline_test.txt').read_text(encoding='utf-8')==(tmp_path/'prepared/augmented_test.txt').read_text(encoding='utf-8')
    assert len((tmp_path/'prepared/augmented_train.txt').read_text(encoding='utf-8').splitlines())==2
    rows[0]['group_id']='real_2';write_json(b/'version.json',{'samples':rows});write_json(b/'checksums.json',{'version.json':sha256(b/'version.json')})
    with pytest.raises(ValueError,match='泄漏'):detector_inputs(a,b)
    (a/'images/0.png').write_bytes(b'changed')
    with pytest.raises(ValueError,match='改变'):detector_inputs(a,b)


def test_detection_report_preserves_negative_delta_and_budget_gate():
    r={'groups':{name:{'mAP50':n,'mAP50_95':n,'precision':n,'recall':n,'train_iterations':5} for name,n in [('baseline',.5),('augmented',.4)]},'comparable_training_iterations':True}
    assert validate_pair_report(r)['mAP50']==pytest.approx(-10)
    r['groups']['augmented']['train_iterations']=6
    with pytest.raises(ValueError,match='预算'):validate_pair_report(r)


def test_learning_uses_frozen_versions_and_records_model_lineage(tmp_path,monkeypatch):
    from fire_modeling import learning
    job=tmp_path/'job';a=job/'inputs/real';b=job/'inputs/synthetic';version(a);version(b,'diffusion')
    weights=tmp_path/'models/yolo11n.pt';weights.parent.mkdir();weights.write_bytes(b'unit-fixture-not-a-model')
    request={'real_version':'a'*24,'synthetic_version':'b'*24,'real_version_sha256':sha256(a/'version.json'),'synthetic_version_sha256':sha256(b/'version.json'),'weights':'yolo11n.pt','weights_sha256':sha256(weights),'parameters':{'epochs':1}}
    write_json(job/'learning-request.json',request)
    def fixture(spec,output):
        assert read_json(spec)['weights']==str(weights)
        return {'groups':{name:{'mAP50':n,'mAP50_95':n,'precision':n,'recall':n,'train_iterations':2} for name,n in [('baseline',.2),('augmented',.3)]},'comparable_training_iterations':True,'weights_sha256':sha256(weights)}
    monkeypatch.setattr(learning,'paired_yolo_experiment',fixture)
    r=learning.run(job,weights.parent)
    assert r['delta_pp']['mAP50']==pytest.approx(10)
    assert r['lineage']['group_checked'] and r['real_version']==request['real_version']
    weights.write_bytes(b'changed')
    with pytest.raises(ValueError,match='权重'):learning.run(job,weights.parent)
