"""Verify stage contracts reject tampering and preserve review boundaries."""
from pathlib import Path
import pytest
from fire_modeling.config import SceneConfig
from fire_modeling.io import sha256,write_json,read_json
from fire_modeling.pipeline import run_pipeline
from fire_modeling import workflow


def handoff(root, config):
    root.mkdir()
    csv=root/"case_hrr.csv"; csv.write_text('Time,HRR\n0,0\n5,100\n',encoding='utf-8')
    write_json(root/"handoff.json",{"status":"success","config":config.to_dict(),"hrr_csv":csv.name,"sha256":sha256(csv)})
    return csv


def test_external_fds_validated_before_render(tmp_path):
    c=SceneConfig(width=64,height=64)
    csv=handoff(tmp_path/"fds",c)
    run_pipeline(c,tmp_path/"good",count=2,enhancer="none",external_fds=csv.parent)
    m=read_json(tmp_path/"good/manifest.json")
    assert m["physics"]=="fds_external"
    assert all(s["annotation_status"]=="pending_review" for s in m["samples"])
    csv.write_text('Time,HRR\n0,0\n5,200\n',encoding='utf-8')
    with pytest.raises(ValueError,match="checksum"):
        run_pipeline(c,tmp_path/"bad",external_fds=csv.parent)


def test_enhance_retains_groups_and_candidate_status(tmp_path,monkeypatch):
    c=SceneConfig(width=64,height=64)
    source=tmp_path/"render"
    run_pipeline(c,source,count=2,enhancer="none")
    class FakeEnhancer:
        def __init__(self,*args,**kwargs): pass
        def run(self,image,seed,**kwargs): return image.transpose(0),{"seed":seed}
    monkeypatch.setattr(workflow,"DiffusionEnhancer",FakeEnhancer)
    workflow.enhance(source,tmp_path/"enhanced",Path("unused"),"cpu")
    m=read_json(tmp_path/"enhanced/manifest.json")
    assert len(m["samples"])==3
    child=m["samples"][-1]; parent=m["samples"][1]
    assert child["group_id"]==parent["group_id"]
    assert child["parent_id"]==parent["sample_id"]
    assert child["annotation_status"]=="pending_review"
    assert not (tmp_path/"enhanced/reviews.json").exists()


def test_model_load_failure_is_not_render_success(tmp_path,monkeypatch):
    source=tmp_path/"render"
    run_pipeline(SceneConfig(width=64,height=64),source,count=2,enhancer="none")
    class MissingModel:
        def __init__(self,*args,**kwargs): raise RuntimeError("weights unavailable")
    monkeypatch.setattr(workflow,"DiffusionEnhancer",MissingModel)
    with pytest.raises(RuntimeError,match="weights unavailable"):
        workflow.enhance(source,tmp_path/"failed",Path("unused"),"cpu")
    assert read_json(tmp_path/"failed/manifest.json")["status"]=="failed"


@pytest.mark.parametrize("status",["running","enhancing","failed"])
def test_incomplete_runs_cannot_export_review_tasks(tmp_path,status):
    from fire_modeling.dataset import label_studio_tasks,publish
    write_json(tmp_path/"manifest.json",{"status":status,"samples":[]})
    with pytest.raises(ValueError,match="not complete"): label_studio_tasks(tmp_path,"/data")
    with pytest.raises(ValueError,match="not complete"): publish(tmp_path,tmp_path/"version","v1")


def test_rejected_sd_candidate_is_excluded_and_recorded(tmp_path,monkeypatch):
    source=tmp_path/'render';run_pipeline(SceneConfig(width=64,height=64),source,count=3,enhancer='none')
    class Engine:
        def __init__(self,*args,**kwargs):self.calls=0
        def run(self,image,*args,**kwargs):
            self.calls+=1
            if self.calls==1:raise workflow.SafetyRejected('test candidate rejected')
            return image,{'method':'test'}
    monkeypatch.setattr(workflow,'DiffusionEnhancer',Engine)
    workflow.enhance(source,tmp_path/'enhanced',Path('unused'),'cpu')
    m=read_json(tmp_path/'enhanced/manifest.json')
    assert len(m['rejected_enhancements'])==1
    assert sum(s['source']=='diffusion' for s in m['samples'])==1
    assert m['stages'][-1]['status']=='partial'
