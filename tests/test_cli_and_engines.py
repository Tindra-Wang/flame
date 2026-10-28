from dataclasses import replace
from pathlib import Path
import subprocess
import sys

from PIL import Image
import pytest

from fire_modeling.cli import main,doctor
from fire_modeling.config import SceneConfig
from fire_modeling.dataset import import_coco,merge_runs,review,publish
from fire_modeling.enhancement import DiffusionEnhancer,weight_fingerprint
from fire_modeling.io import read_json,write_json
from fire_modeling.physics import run_fds


def test_command_line_model_to_reviewed_export(tmp_path,capsys):
    config=replace(SceneConfig(),width=96,height=96,plume_steps=12,particles_per_step=4)
    path=tmp_path/"config.json"; write_json(path,config.to_dict())
    run=tmp_path/"run"; version=tmp_path/"version"; export=tmp_path/"export"
    assert main(["doctor"])==0
    assert main(["prepare","--config",str(path),"--output",str(tmp_path/"prepared")])==0
    assert main(["generate","--config",str(path),"--output",str(run),"--count","4"])==0
    assert main(["quality","--run",str(run)])==0
    assert main(["label-studio","--run",str(run),"--image-base-url","https://example.test/data","--output",str(tmp_path/"tasks.json")])==0
    samples=read_json(run/"manifest.json")["samples"]
    for sample in samples:
        assert main(["review","--run",str(run),"--sample",sample["sample_id"],"--reviewer","test-fixture-reviewer"])==0
    assert main(["publish","--run",str(run),"--output",str(version),"--version","v1"])==0
    assert main(["export","--version-dir",str(version),"--output",str(export)])==0
    assert main(["distribution","--real",str(run/"images"),"--synthetic",str(run/"images"),"--output",str(tmp_path/"distribution.json")])==0
    assert read_json(tmp_path/"distribution.json")["value"]==pytest.approx(0)
    write_json(tmp_path/"prediction.json",[])
    assert main(["detection-metrics","--truth",str(export/"coco.json"),"--predictions",str(tmp_path/"prediction.json"),"--output",str(tmp_path/"metrics.json")])==0
    assert read_json(tmp_path/"metrics.json")["AP50"]==0
    assert main(["generate","--config",str(path),"--output",str(run)])==2
    capsys.readouterr()


def test_cli_demo_and_physical_comparison(tmp_path,capsys):
    configs=tmp_path/"configs"; configs.mkdir()
    for name,scene in [("room","indoor"),("outdoor","outdoor")]:
        cfg=replace(SceneConfig(),scene_id=name,scene_type=scene,width=96,height=96,plume_steps=8,particles_per_step=3)
        write_json(configs/f"{name}.json",cfg.to_dict())
    output=tmp_path/"demo"
    assert main(["demo","--configs-dir",str(configs),"--output",str(output),"--count","2"])==0
    assert read_json(output/"manifest.json")["route"]=="procedural_preview_not_cfd_or_diffusion"
    assert (output/"contact_sheet.png").is_file()
    ref={"quantity":"T","unit":"C","time_s":[0,1],"values":[10,20]}
    write_json(tmp_path/"reference.json",ref)
    assert main(["physical-error","--reference",str(tmp_path/"reference.json"),"--prediction",str(tmp_path/"reference.json"),"--output",str(tmp_path/"physical.json")])==0
    assert read_json(tmp_path/"physical.json")["normalized_absolute_error"]==0
    capsys.readouterr()


def test_coco_import_requires_review_and_keeps_groups(tmp_path):
    images=tmp_path/"images"; images.mkdir()
    for i in range(2): Image.new("RGB",(32,32),(20+i*40,30,40)).save(images/f"{i}.png")
    coco={"categories":[{"id":1,"name":"fire"}],"images":[{"id":0,"file_name":"0.png","width":32,"height":32,"group_id":"eventA"},{"id":1,"file_name":"1.png","width":32,"height":32,"group_id":"eventA"}],"annotations":[{"image_id":1,"category_id":1,"bbox":[8,8,16,16]}]}
    annotations=tmp_path/"annotations.json"; write_json(annotations,coco)
    root=tmp_path/"real"; import_coco(images,annotations,root,"real","https://example.test","test-fixtures-only")
    manifest=read_json(root/"manifest.json")
    assert manifest["samples"][0]["group_id"]==manifest["samples"][1]["group_id"]
    with pytest.raises(ValueError): publish(root,tmp_path/"version","v1")
    review(root,"real_1","fixture-reviewer")
    merged=tmp_path/"merged"; merge_runs([root],merged)
    assert read_json(merged/"reviews.json")["current"]["real_1"]["decision"]=="approved"
    assert publish(merged,tmp_path/"version","v1")["samples"][0]["source"]=="real"
    with pytest.raises(ValueError): merge_runs([root,root],tmp_path/"duplicate")


def test_fds_runner_checks_actual_time_and_records_failure(tmp_path,monkeypatch):
    config=SceneConfig(); root=tmp_path/"fds"; root.mkdir()
    def fake_solver(command,**kwargs):
        (kwargs["cwd"]/f"{config.scene_id}_hrr.csv").write_text("Time,HRR\n0,0\n5,100\n")
        return subprocess.CompletedProcess(command,0)
    monkeypatch.setattr(subprocess,"run",fake_solver)
    assert run_fds(config,root,sys.executable).is_file()
    assert read_json(root/"execution.json")["status"]=="success"
    with pytest.raises(ValueError): run_fds(config,root,sys.executable)
    failed=tmp_path/"failed"; failed.mkdir()
    def failing_solver(command,**kwargs): return subprocess.CompletedProcess(command,1)
    monkeypatch.setattr(subprocess,"run",failing_solver)
    with pytest.raises(RuntimeError): run_fds(config,failed,sys.executable)
    assert read_json(failed/"execution.json")["status"]=="failed"
    missing=tmp_path/"missing"; missing.mkdir()
    with pytest.raises(RuntimeError): run_fds(config,missing,"__missing_fds__")


def test_diffusion_does_not_fall_back_to_classical(tmp_path):
    with pytest.raises(ValueError): DiffusionEnhancer(str(tmp_path))
    write_json(tmp_path/"model_index.json",{"_class_name":"StableDiffusionPipeline"})
    (tmp_path/"weights.safetensors").write_bytes(b"unit-test-fixture-not-real-weights")
    assert len(weight_fingerprint(tmp_path))==2
    with pytest.raises(ValueError): DiffusionEnhancer(str(tmp_path),strength=.01,steps=1)


def test_cli_train_predict_commands(tmp_path,capsys):
    from fire_modeling.dataset import export_version
    from fire_modeling.io import sha256
    import numpy as np
    root=tmp_path/"version"; root.mkdir(); samples=[]
    for i in range(2):
        pixels=np.full((32,32,3),40,dtype="uint8"); pixels[8:24,8:24]=[255,120+i*10,10]
        Image.fromarray(pixels).save(root/f"{i}.png")
        samples.append({"sample_id":f"fixture_{i}","image":f"{i}.png","sha256":sha256(root/f"{i}.png"),"split":"train","width":32,"height":32,"group_id":"fixture","source":"test_fixture","boxes":[[8,8,24,24]]})
    write_json(root/"version.json",{"version":"test","counts":{"train":2,"val":0,"test":0},"samples":samples})
    write_json(root/"checksums.json",{str(p.relative_to(root)):sha256(p) for p in root.iterdir() if p.is_file()})
    export=tmp_path/"export"; export_version(root,export)
    assert main(["train-color","--version-dir",str(root),"--output",str(tmp_path/"model.json")])==0
    assert main(["predict-color","--model",str(tmp_path/"model.json"),"--dataset",str(export),"--truth",str(export/"coco.json"),"--output",str(tmp_path/"predictions.json")])==0
    assert read_json(tmp_path/"predictions.json")
    capsys.readouterr()


def test_renderer_contract_can_be_replaced_without_pipeline_changes(tmp_path):
    from fire_modeling.adapters import RenderResult
    from fire_modeling.pipeline import run_pipeline
    from PIL import ImageDraw
    class ContractRenderer:
        def render(self,request):
            image=Image.new("RGB",(request.config.width,request.config.height),(80,80,80))
            mask=Image.new("L",image.size,0)
            if request.positive:
                ImageDraw.Draw(image).rectangle((20,20,40,40),fill=(255,120,0))
                ImageDraw.Draw(mask).rectangle((20,20,40,40),fill=255)
            return RenderResult(image,mask,"test_contract_renderer")
    root=tmp_path/"contract"
    run_pipeline(replace(SceneConfig(),width=96,height=96),root,count=2,enhancer="none",renderer_adapter=ContractRenderer())
    samples=read_json(root/"manifest.json")["samples"]
    assert samples[1]["boxes"]==[[20,20,41,41]]
    assert samples[1]["source"]=="test_contract_renderer" and samples[1]["annotation_status"]=="pending_review"


def test_export_detects_frozen_label_tampering(tmp_path):
    images=tmp_path/"images"; images.mkdir(); Image.new("RGB",(32,32)).save(images/"0.png")
    coco={"categories":[{"id":1,"name":"fire"}],"images":[{"id":0,"file_name":"0.png","width":32,"height":32}],"annotations":[]}
    write_json(tmp_path/"coco.json",coco)
    run=tmp_path/"run"; import_coco(images,tmp_path/"coco.json",run,"fixture","https://example.test","fixture")
    review(run,"fixture_0","fixture-reviewer"); version=tmp_path/"version"; publish(run,version,"v1")
    frozen=read_json(version/"version.json"); frozen["samples"][0]["boxes"]=[[0,0,10,10]]; write_json(version/"version.json",frozen)
    from fire_modeling.dataset import export_version
    with pytest.raises(ValueError,match="Published version content changed"): export_version(version,tmp_path/"export")
