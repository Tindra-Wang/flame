"""Review gates, group-safe splitting and immutable COCO/YOLO snapshots."""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import re
import shutil

from .annotations import validate_boxes, yolo_lines
from .io import new_directory, read_json, resolve_artifact, sha256, write_json
from .quality import inspect_sample


def ready_manifest(root: Path) -> dict:
    manifest=read_json(root/"manifest.json")
    if manifest.get("status") not in {"success_candidates_only","imported_pending_review","merged_pending_review"}:
        raise ValueError("Run is not complete; do not review, export tasks or publish running/failed data")
    return manifest


def review(root: Path, sample_id: str, reviewer: str, decision="approved", boxes=None, timing=None) -> None:
    if not reviewer.strip() or decision not in {"approved","rejected"}: raise ValueError("Reviewer and valid decision are required")
    manifest=ready_manifest(root)
    sample=next((s for s in manifest["samples"] if s["sample_id"]==sample_id),None)
    if sample is None: raise ValueError("Unknown sample ID")
    new_boxes=sample["boxes"] if boxes is None else boxes
    validate_boxes(new_boxes,sample["width"],sample["height"])
    candidate={**sample,"boxes":new_boxes}
    if decision=="approved" and not inspect_sample(root,candidate)["structural_pass"]:
        raise ValueError("Cannot approve a structurally invalid or changed sample")
    path=root/"reviews.json"; data=read_json(path) if path.exists() else {"current":{},"history":[]}
    revision={"sample_id":sample_id,"reviewer":reviewer.strip(),"decision":decision,"boxes":new_boxes,"image_sha256":sample["sha256"],"revision":len(data["history"])+1,"at":datetime.now(timezone.utc).isoformat()}
    if timing and isinstance(timing,dict) and timing.get("mode") in {"scratch","candidate"}:
        active=timing.get("active_s")
        if isinstance(active,(int,float)) and 0<=active<=7200: revision["timing"]={"mode":timing["mode"],"active_s":round(float(active),1)}
    data["current"][sample_id]=revision; data["history"].append(revision); write_json(path,data)


def split_groups(samples: list[dict], seed: int=42) -> dict[str,str]:
    assignment={}
    for group in sorted({s["group_id"] for s in samples}):
        value=int(hashlib.sha256(f"{seed}:{group}".encode()).hexdigest()[:8],16)/2**32
        assignment[group]="train" if value<.7 else "val" if value<.85 else "test"
    return {s["sample_id"]:assignment[s["group_id"]] for s in samples}


def publish(root: Path, output: Path, version: str, seed=42) -> dict:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}",version): raise ValueError("Unsafe version name")
    manifest=ready_manifest(root)
    reviews=read_json(root/"reviews.json")["current"] if (root/"reviews.json").exists() else {}
    approved=[]; seen=set()
    for sample in manifest["samples"]:
        if not re.fullmatch(r"[A-Za-z0-9_-]+",sample["sample_id"]): raise ValueError("Unsafe sample ID")
        result=reviews.get(sample["sample_id"])
        if not result or result["decision"]!="approved": continue
        if result["image_sha256"]!=sample["sha256"]: raise ValueError("Review applies to a different image")
        frozen={**sample,"boxes":result["boxes"],"review":result,"annotation_status":"approved"}
        check=inspect_sample(root,frozen)
        if not check["structural_pass"]: raise ValueError(f"Invalid sample {sample['sample_id']}: {check['errors']}")
        if sample["sha256"] in seen: raise ValueError("Exact duplicate samples cannot be published")
        seen.add(sample["sha256"]); approved.append(frozen)
    if not approved: raise ValueError("No manually approved samples; review the images first")
    target=new_directory(output); assignments=split_groups(approved,seed)
    for sample in approved:
        relative=f"images/{sample['sample_id']}.png"; destination=target/relative; destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(resolve_artifact(root,sample["image"]),destination)
        sample["image"]=relative; sample["split"]=assignments[sample["sample_id"]]
    report={"schema_version":1,"version":version,"source_run":str(root.resolve()),"source_manifest_sha256":sha256(root/"manifest.json"),"samples":approved,"counts":{split:sum(s["split"]==split for s in approved) for split in ("train","val","test")},"note":"Empty splits are possible with few independent groups. Do not split one source group to fill them."}
    write_json(target/"version.json",report)
    shutil.copy2(root/"manifest.json",target/"source_manifest.json")
    write_json(target/"checksums.json",{str(p.relative_to(target)).replace("\\","/"):sha256(p) for p in sorted(target.rglob("*")) if p.is_file()})
    return report


def export_version(root: Path, output: Path) -> dict:
    for relative,digest in read_json(root/"checksums.json").items():
        if sha256(resolve_artifact(root,relative))!=digest: raise ValueError("Published version content changed")
    version=read_json(root/"version.json"); target=new_directory(output)
    coco={"images":[],"annotations":[],"categories":[{"id":1,"name":"fire"}]}; aid=1
    for i,sample in enumerate(version["samples"],1):
        if not re.fullmatch(r"[A-Za-z0-9_-]+",sample["sample_id"]) or sample["split"] not in {"train","val","test"}: raise ValueError("Unsafe sample ID or split")
        path=resolve_artifact(root,sample["image"])
        if sha256(path)!=sample["sha256"]: raise ValueError("Published image content changed")
        split=sample["split"]; image_relative=f"images/{split}/{sample['sample_id']}.png"
        destination=target/image_relative; destination.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(path,destination)
        labels=target/f"labels/{split}/{sample['sample_id']}.txt"; labels.parent.mkdir(parents=True,exist_ok=True)
        labels.write_text(yolo_lines(sample["boxes"],sample["width"],sample["height"]),encoding="utf-8")
        coco["images"].append({"id":i,"file_name":image_relative,"width":sample["width"],"height":sample["height"],"group_id":sample["group_id"],"split":split,"source":sample["source"]})
        for x0,y0,x1,y1 in sample["boxes"]:
            coco["annotations"].append({"id":aid,"image_id":i,"category_id":1,"bbox":[x0,y0,x1-x0,y1-y0],"area":(x1-x0)*(y1-y0),"iscrowd":0}); aid+=1
    write_json(target/"coco.json",coco)
    for split in ("train","val","test"):
        ids={i["id"] for i in coco["images"] if i["split"]==split}
        write_json(target/f"coco_{split}.json",{**coco,"images":[i for i in coco["images"] if i["id"] in ids],"annotations":[a for a in coco["annotations"] if a["image_id"] in ids]})
        (target/f"images/{split}").mkdir(parents=True,exist_ok=True)
        (target/f"labels/{split}").mkdir(parents=True,exist_ok=True)
    # Absolute YAML path keeps data loading independent of the current directory.
    yaml=f'path: "{target.as_posix()}"\ntrain: images/train\nval: images/val\ntest: images/test\nnames:\n  0: fire\n'
    (target/"data.yaml").write_text(yaml,encoding="utf-8")
    write_json(target/"dataset_card.json",{"version":version["version"],"counts":version["counts"],"sources":sorted({s["source"] for s in version["samples"]}),"label_status":"human_reviewed","usage":"Research prototype; preview/Mantaflow proxies are not validated FDS field reconstructions.","coordinate_mapping":{"COCO":"category_id=1; pixel xywh","YOLO":"class_id=0; normalized cxcywh"}})
    checksums={str(p.relative_to(target)).replace("\\","/"):sha256(p) for p in sorted(target.rglob("*")) if p.is_file()}
    write_json(target/"checksums.json",checksums)
    return {"count":len(coco["images"]),"output":str(target),"splits":version["counts"]}


def label_studio_tasks(root: Path, image_base_url: str) -> list[dict]:
    """URL base must expose images with authentication in the eventual platform."""
    manifest=ready_manifest(root); tasks=[]
    for sample in manifest["samples"]:
        results=[]
        for i,(x0,y0,x1,y1) in enumerate(sample["boxes"]):
            w,h=sample["width"],sample["height"]
            results.append({"id":str(i),"from_name":"fire_box","to_name":"image","type":"rectanglelabels","original_width":w,"original_height":h,"image_rotation":0,"value":{"x":100*x0/w,"y":100*y0/h,"width":100*(x1-x0)/w,"height":100*(y1-y0)/h,"rotation":0,"rectanglelabels":["fire"]}})
        tasks.append({"data":{"image":image_base_url.rstrip("/")+"/"+sample["image"],"sample_id":sample["sample_id"]},"predictions":[{"model_version":"candidate_not_approved","result":results}]})
    return tasks


def import_label_studio(root: Path, tasks: list[dict], reviewer: str) -> int:
    manifest=ready_manifest(root); samples={s["sample_id"]:s for s in manifest["samples"]}
    pending=[]
    for task in tasks:
        sid=task["data"]["sample_id"]
        if sid not in samples: raise ValueError("Label Studio export refers to an unknown sample")
        annotations=[a for a in task.get("annotations",[]) if not a.get("was_cancelled",False)]
        if len(annotations)!=1: raise ValueError("Import exactly one completed human annotation per sample; predictions are not reviews")
        sample=samples[sid]; w,h=sample["width"],sample["height"]; boxes=[]
        for result in annotations[0]["result"]:
            value=result.get("value",{})
            if result.get("type")!="rectanglelabels" or value.get("rectanglelabels")!=["fire"] or value.get("rotation",0)!=0:
                raise ValueError("Only unrotated fire rectangles are supported")
            if result.get("original_width")!=w or result.get("original_height")!=h: raise ValueError("Annotation dimensions differ")
            x,y,bw,bh=[float(value[k]) for k in ("x","y","width","height")]
            boxes.append([x*w/100,y*h/100,(x+bw)*w/100,(y+bh)*h/100])
        validate_boxes(boxes,w,h); pending.append((sid,boxes))
    for sid,boxes in pending: review(root,sid,reviewer,boxes=boxes)
    return len(pending)


def import_coco(images_root: Path, annotations: Path, output: Path, dataset_id: str, source_url: str, license_note: str) -> dict:
    """Import local authorized real images; existing boxes still require review."""
    if not re.fullmatch(r"[A-Za-z0-9_-]+",dataset_id) or not source_url.strip() or not license_note.strip():
        raise ValueError("Safe dataset ID, source and permission note are required")
    from PIL import Image
    coco=read_json(annotations)
    if coco.get("categories")!=[{"id":1,"name":"fire"}]:
        categories=coco.get("categories",[])
        if len(categories)!=1 or categories[0].get("id")!=1 or categories[0].get("name")!="fire": raise ValueError("Import expects one COCO fire category with ID 1")
    by_id={i["id"]:[] for i in coco["images"]}
    if len(by_id)!=len(coco["images"]): raise ValueError("Duplicate image IDs")
    for annotation in coco["annotations"]:
        if annotation["image_id"] not in by_id or annotation["category_id"]!=1: raise ValueError("Unknown image/category in annotation")
        if annotation.get("iscrowd",0): raise ValueError("Crowd boxes are unsupported; resolve them before import")
        x,y,w,h=annotation["bbox"]; by_id[annotation["image_id"]].append([x,y,x+w,y+h])
    root=new_directory(output); samples=[]
    for item in coco["images"]:
        sid=f"{dataset_id}_{item['id']}"
        if not re.fullmatch(r"[A-Za-z0-9_-]+",sid): raise ValueError("Unsafe image ID")
        source=resolve_artifact(images_root,item["file_name"])
        destination=root/f"images/{sid}.png"; destination.parent.mkdir(parents=True,exist_ok=True)
        with Image.open(source) as im:
            if im.size!=(item["width"],item["height"]): raise ValueError("COCO image dimensions differ from file")
            validate_boxes(by_id[item["id"]],*im.size); im.convert("RGB").save(destination)
        samples.append({"sample_id":sid,"image":f"images/{sid}.png","sha256":sha256(destination),"width":item["width"],"height":item["height"],"boxes":by_id[item["id"]],"source":"real","source_file_sha256":sha256(source),"group_id":f"{dataset_id}:{item.get('group_id','entire_import')}","parent_id":None,"annotation_status":"pending_review","label_source":"imported_coco_requires_confirmation"})
    manifest={"schema_version":1,"status":"imported_pending_review","samples":samples,"provenance":{"source_url":source_url,"license_note":license_note,"annotations_sha256":sha256(annotations)},"note":"Missing event group_id places the entire import in one group to prevent unknown-source leakage."}
    write_json(root/"manifest.json",manifest)
    return {"output":str(root),"samples":len(samples),"status":manifest["status"]}


def merge_runs(roots: list[Path], output: Path) -> dict:
    target=new_directory(output); samples=[]; seen=set(); reviews={"current":{},"history":[]}; input_metadata=[]
    for root in roots:
        manifest=read_json(root/"manifest.json")
        input_metadata.append({"run":str(root.resolve()),"metadata":{k:v for k,v in manifest.items() if k!="samples"}})
        if manifest["status"]=="failed": raise ValueError("Do not merge a failed run")
        prior=read_json(root/"reviews.json") if (root/"reviews.json").exists() else {"current":{},"history":[]}
        for sample in manifest["samples"]:
            sid=sample["sample_id"]
            if sid in seen or not re.fullmatch(r"[A-Za-z0-9_-]+",sid): raise ValueError("Duplicate or unsafe sample ID across runs")
            seen.add(sid); updated={**sample,"source_run":str(root.resolve())}
            for key,folder in (("image","images"),("mask","masks")):
                if key not in sample: continue
                relative=f"{folder}/{sid}.png"; destination=target/relative; destination.parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(resolve_artifact(root,sample[key]),destination); updated[key]=relative
            if sha256(target/updated["image"])!=sample["sha256"]: raise ValueError("Source image was modified")
            samples.append(updated)
            if sid in prior["current"]: reviews["current"][sid]=prior["current"][sid]
        reviews["history"].extend(prior["history"])
    write_json(target/"manifest.json",{"schema_version":1,"status":"merged_pending_review","samples":samples,"source_runs":[str(p.resolve()) for p in roots],"source_metadata":input_metadata})
    write_json(target/"reviews.json",reviews)
    return {"output":str(target),"samples":len(samples)}
