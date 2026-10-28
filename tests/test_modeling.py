from dataclasses import replace
import json
from pathlib import Path
import subprocess
import sys

import numpy as np
from PIL import Image
import pytest

from fire_modeling.annotations import boxes_from_mask, box_iou, validate_boxes, yolo_lines
from fire_modeling.config import SceneConfig
from fire_modeling.dataset import review, publish, export_version, split_groups, label_studio_tasks, import_label_studio
from fire_modeling.evaluation import detection_metrics, distribution, physical_error, train_color_detector, predict_color_detector
from fire_modeling.io import read_json, resolve_artifact, write_json, sha256
from fire_modeling.physics import fds_input, read_hrr, visual_hrr
from fire_modeling.pipeline import run_pipeline, prepare
from fire_modeling.procedural import render
from fire_modeling.quality import inspect_run


@pytest.fixture
def config():
    return replace(SceneConfig(),width=96,height=96,plume_steps=12,particles_per_step=4)


@pytest.fixture
def run(tmp_path,config):
    root=tmp_path/"run"; run_pipeline(config,root,count=8)
    return root


@pytest.mark.parametrize("changes",[
    {"scene_id":"../escape"},{"cell_size_m":0},{"room_size_m":[4.1,4,3]},
    {"fire_center_m":[0,0]},{"peak_hrr_kw":float("nan")},{"duration_s":1},
    {"weather":["rain"]},{"camera_angles_deg":[]},{"width":10},{"wind_m_s":1},
    {"seed":-1},{"unknown":1},
])
def test_config_rejects_invalid(changes):
    with pytest.raises((ValueError,TypeError)):
        SceneConfig.from_dict(changes)


def test_fds_units_and_boundaries(config):
    text=fds_input(config)
    assert "HRRPUA=156.25" in text  # 100 kW / 0.64 m2
    assert "IJK=20,20,15" in text and "SURF_ID='OPEN'" in text
    assert "T_CENTER" in text and "SPEC_ID='SOOT'" in text
    outdoor=fds_input(replace(config,scene_type="outdoor",wind_m_s=-.5))
    assert "MB='XMAX', SURF_ID='WIND'" in outdoor
    assert "VEL=-0.5" in outdoor


def test_hrr_reads_units_header_and_disallows_extrapolation(tmp_path,config):
    path=tmp_path/"hrr.csv"; path.write_text('s,kW,kW\n"Time","HRR","Q_RADI"\n0,0,0\n5,100,10\n')
    times,values=read_hrr(path); assert values.tolist()==[0,100]
    assert visual_hrr(config,2.5,path)["hrr_kw"]==50
    assert visual_hrr(config,2.5)["source"]=="configured_hrr_not_solved"
    with pytest.raises(ValueError): visual_hrr(config,6,path)
    path.write_text("Time,HRR\n1,1\n1,2\n")
    with pytest.raises(ValueError): read_hrr(path)


def test_masks_coordinates_and_negatives(config):
    mask=np.zeros((10,20),dtype=np.uint8); mask[2:6,3:10]=255
    boxes=boxes_from_mask(mask)
    assert boxes==[[3,2,10,6]]
    assert yolo_lines(boxes,20,10)=="0 0.32500000 0.40000000 0.35000000 0.40000000\n"
    assert box_iou(boxes[0],boxes[0])==1
    with pytest.raises(ValueError): validate_boxes([[0,0,21,10]],20,10)
    with pytest.raises(ValueError): boxes_from_mask(np.zeros((10,10,3)))
    image,negative=render(config,42,25,"clear",1,False)
    assert np.asarray(image).max()>100  # Warm distractor does not create a fire annotation.
    assert boxes_from_mask(np.asarray(negative))==[]


def test_preview_repeatable_and_has_fire(config):
    a,mask=render(config,7,25,"clear",1,True)
    b,mask2=render(config,7,25,"clear",1,True)
    assert np.array_equal(a,b) and np.array_equal(mask,mask2)
    assert boxes_from_mask(np.asarray(mask))


def test_prepare_is_not_simulation(tmp_path,config):
    root=tmp_path/"prepared"; report=prepare(config,root)
    assert report["status"]=="prepared_not_simulated"
    assert (root/f"{config.scene_id}.fds").exists()
    with pytest.raises(ValueError): prepare(config,root)


def test_missing_engine_is_failed_not_preview(tmp_path,config):
    root=tmp_path/"failed"
    with pytest.raises(RuntimeError): run_pipeline(config,root,count=1,renderer="blender",blender_exe="__missing_blender__")
    assert read_json(root/"manifest.json")["status"]=="failed"
    assert not read_json(root/"manifest.json")["samples"]


def test_pipeline_provenance_and_review_gate(run,tmp_path):
    data=read_json(run/"manifest.json"); assert data["status"]=="success_candidates_only"
    assert any(s["source"]=="classical_photometric" for s in data["samples"])
    with pytest.raises(ValueError,match="No manually approved"): publish(run,tmp_path/"version","v1")
    child=next(s for s in data["samples"] if s["parent_id"])
    parent=next(s for s in data["samples"] if s["sample_id"]==child["parent_id"])
    assignments=split_groups(data["samples"])
    assert assignments[child["sample_id"]]==assignments[parent["sample_id"]]
    review(run,parent["sample_id"],"test-reviewer")
    report=publish(run,tmp_path/"version","v1")
    assert len(report["samples"])==1  # Approving a parent does NOT approve its child.


def test_snapshot_does_not_change_after_label_edit(run,tmp_path):
    sample=read_json(run/"manifest.json")["samples"][1]
    review(run,sample["sample_id"],"reviewer")
    version=tmp_path/"v1"; publish(run,version,"v1")
    snapshot=read_json(version/"version.json")
    review(run,sample["sample_id"],"reviewer",boxes=[])
    assert read_json(version/"version.json")==snapshot
    output=tmp_path/"export"; export_version(version,output)
    assert len(read_json(output/"coco.json")["annotations"])==len(sample["boxes"])
    for path,digest in read_json(output/"checksums.json").items(): assert sha256(output/path)==digest


def test_negative_has_empty_yolo_label(run,tmp_path):
    sample=read_json(run/"manifest.json")["samples"][0]
    review(run,sample["sample_id"],"reviewer")
    publish(run,tmp_path/"version","v1"); export_version(tmp_path/"version",tmp_path/"export")
    labels=list((tmp_path/"export/labels").rglob("*.txt")); assert len(labels)==1 and labels[0].read_text()==""


def test_changed_image_cannot_be_published(run,tmp_path):
    sample=read_json(run/"manifest.json")["samples"][0]
    review(run,sample["sample_id"],"reviewer")
    Image.new("RGB",(96,96)).save(run/sample["image"])
    with pytest.raises(ValueError,match="Invalid sample"): publish(run,tmp_path/"version","v1")


def test_quality_rejects_duplicates_and_escape(run):
    data=read_json(run/"manifest.json"); data["samples"].append(data["samples"][0].copy())
    report=inspect_run(run,data); assert not report["samples"][-1]["structural_pass"]
    with pytest.raises(ValueError): resolve_artifact(run,"../outside.png")


def test_labelstudio_predictions_are_not_approval(run):
    tasks=label_studio_tasks(run,"https://example.test/data")
    with pytest.raises(ValueError,match="completed human"): import_label_studio(run,tasks,"reviewer")
    task=tasks[1]; task["annotations"]=[{"result":task["predictions"][0]["result"]}]
    assert import_label_studio(run,[task],"reviewer")==1
    review_record=read_json(run/"reviews.json")["current"][task["data"]["sample_id"]]
    assert review_record["decision"]=="approved"


def test_detection_uses_ranking_and_negative_images():
    truth={"images":[{"id":1,"width":20,"height":20},{"id":2,"width":20,"height":20}],"annotations":[{"image_id":1,"category_id":1,"bbox":[2,2,10,10]}]}
    perfect=[{"image_id":1,"score":.9,"bbox":[2,2,10,10]}]
    report=detection_metrics(truth,perfect)
    assert report["AP50"]==1 and report["AP50_95"]==1 and report["negative_image_false_positive_rate"]==0
    false_first=[{"image_id":2,"score":.95,"bbox":[0,0,5,5]},*perfect]
    report=detection_metrics(truth,false_first)
    assert report["AP50"]==.5 and report["negative_image_false_positive_rate"]==1
    with pytest.raises(ValueError): detection_metrics(truth,[{"image_id":9,"score":.9,"bbox":[1,1,2,2]}])


def test_distribution_and_physical_error(tmp_path):
    a=tmp_path/"a"; b=tmp_path/"b"; a.mkdir(); b.mkdir()
    for root in [a,b]:
        for i in range(2): Image.new("RGB",(16,16),(i*100,50,25)).save(root/f"{i}.png")
    assert distribution(a,b)["value"]==pytest.approx(0)
    reference={"quantity":"temperature","unit":"C","time_s":[0,1,2],"values":[20,40,60]}
    prediction={**reference,"values":[21,42,63]}
    assert physical_error(reference,prediction)["normalized_absolute_error"]==pytest.approx(.05)
    with pytest.raises(ValueError): physical_error(reference,{**prediction,"unit":"K"})
    with pytest.raises(ValueError): physical_error({**reference,"values":[0,0,0]},prediction)


def test_learned_baseline_is_fitted_not_hardcoded(tmp_path):
    root=tmp_path/"data"; root.mkdir(); samples=[]; truth={"images":[],"annotations":[]}
    for i in range(4):
        pixels=np.full((32,32,3),40,dtype="uint8"); pixels[8:24,8:24]=[255,130+i*5,15]
        Image.fromarray(pixels).save(root/f"{i}.png")
        samples.append({"image":f"{i}.png","split":"train","boxes":[[8,8,24,24]]})
        truth["images"].append({"id":i,"file_name":f"{i}.png","width":32,"height":32})
        truth["annotations"].append({"image_id":i,"category_id":1,"bbox":[8,8,16,16]})
    write_json(root/"version.json",{"samples":samples})
    model=train_color_detector(root,steps=80)
    assert model["loss"][-1]<model["loss"][0] and np.linalg.norm(model["weights"])>0
    predictions=predict_color_detector(model,root,truth)
    assert detection_metrics(truth,predictions)["AP50"]==1


def test_cli_errors_and_doctor(tmp_path):
    proc=subprocess.run([sys.executable,"-m","fire_modeling","doctor"],capture_output=True,text=True,encoding="utf-8",check=True)
    assert json.loads(proc.stdout)["python"]==sys.executable
    proc=subprocess.run([sys.executable,"-m","fire_modeling","prepare","--config",str(tmp_path/"missing.json"),"--output",str(tmp_path/"output")],capture_output=True,text=True,encoding="utf-8")
    assert proc.returncode==2 and "ERROR:" in proc.stderr
