"""Real metric implementations and an explicitly named lightweight learned baseline."""
from pathlib import Path
import math

import numpy as np
from PIL import Image

from .annotations import box_iou, boxes_from_mask, validate_boxes
from .io import read_json, resolve_artifact, sha256, write_json


def distribution(real: Path, synthetic: Path, metric="color-js", dims=64) -> dict:
    def images(folder):
        iterator=folder.iterdir() if metric=="fid" else folder.rglob("*")
        return sorted(p for p in iterator if p.is_file() and p.suffix.lower() in {".jpg",".jpeg",".png"})
    a,b=images(real),images(synthetic)
    if len(a)<2 or len(b)<2: raise ValueError("Each distribution needs at least two valid images")
    if metric=="fid":
        if dims not in {64,192,768,2048}: raise ValueError("Unsupported Inception feature dimensionality")
        try:
            from pytorch_fid.fid_score import calculate_fid_given_paths
        except ImportError as exc:
            raise RuntimeError("Install evaluation extras to compute actual Inception FID") from exc
        # This library may fetch Inception weights on its first invocation.
        value=float(calculate_fid_given_paths([str(real),str(synthetic)],batch_size=min(16,len(a),len(b)),device="cpu",dims=dims,num_workers=0))
        label=f"FID-{dims}"
    elif metric=="color-js":
        def histogram(files):
            total=np.zeros(24,dtype=float)
            for path in files:
                with Image.open(path) as im: pixels=np.asarray(im.convert("RGB").resize((64,64)))
                total+=np.concatenate([np.histogram(pixels[:,:,channel],bins=8,range=(0,256))[0] for channel in range(3)])
            return (total+1e-12)/(total.sum()+24e-12)
        p,q=histogram(a),histogram(b); m=(p+q)/2
        value=float((np.sum(p*np.log2(p/m))+np.sum(q*np.log2(q/m)))/2)
        label="RGB histogram Jensen-Shannon divergence; NOT FID"
    else: raise ValueError("Unknown distribution metric")
    if not math.isfinite(value): raise ValueError("Metric is not finite")
    return {"metric":label,"value":value,"lower_is_closer":True,"real_count":len(a),"synthetic_count":len(b),"real_files":{str(p.relative_to(real)):sha256(p) for p in a},"synthetic_files":{str(p.relative_to(synthetic)):sha256(p) for p in b},"note":"Small-sample distribution diagnostics do not establish physical validity or detection gains."}


def physical_error(reference: dict, prediction: dict) -> dict:
    if reference["quantity"]!=prediction["quantity"] or reference["unit"]!=prediction["unit"]:
        raise ValueError("Physical quantity and units must agree")
    def arrays(data):
        t=np.asarray(data["time_s"],dtype=float); v=np.asarray(data["values"],dtype=float)
        if t.ndim!=1 or v.shape!=t.shape or len(t)<2 or not np.isfinite(t).all() or not np.isfinite(v).all() or np.any(np.diff(t)<=0):
            raise ValueError("Physical time series must be finite and strictly ordered")
        return t,v
    rt,rv=arrays(reference); pt,pv=arrays(prediction)
    if pt[0]>rt[0] or pt[-1]<rt[-1]: raise ValueError("Prediction must cover the complete reference interval")
    denominator=float(np.abs(rv).sum())
    if denominator==0: raise ValueError("All-zero reference has undefined normalized error")
    value=float(np.abs(np.interp(rt,pt,pv)-rv).sum()/denominator)
    return {"quantity":reference["quantity"],"unit":reference["unit"],"normalized_absolute_error":value,"samples":len(rt),"time_window_s":[float(rt[0]),float(rt[-1])],"note":"Requires measured or independently validated reference data; a solver compared with itself is not physical validation."}


def detection_metrics(truth: dict, predictions: list[dict], threshold=.25) -> dict:
    images=truth["images"]; gt={i["id"]:[] for i in images}; dimensions={i["id"]:(i["width"],i["height"]) for i in images}
    if len(gt)!=len(images): raise ValueError("Duplicate evaluation image IDs")
    for a in truth["annotations"]:
        if a.get("category_id")!=1: raise ValueError("Only COCO category_id=1 fire is supported")
        if a["image_id"] not in gt: raise ValueError("Unknown ground-truth image")
        x,y,w,h=a["bbox"]; box=[x,y,x+w,y+h]; validate_boxes([box],*dimensions[a["image_id"]]); gt[a["image_id"]].append(box)
    parsed=[]
    for p in predictions:
        if p["image_id"] not in gt or p.get("category_id",1)!=1: raise ValueError("Prediction has unknown image/category")
        score=float(p["score"])
        if not math.isfinite(score) or not 0<=score<=1: raise ValueError("Invalid prediction confidence")
        x,y,w,h=p["bbox"]; box=[x,y,x+w,y+h]; validate_boxes([box],*dimensions[p["image_id"]])
        parsed.append({"image_id":p["image_id"],"box":box,"score":score})
    parsed.sort(key=lambda p:p["score"],reverse=True)
    n_gt=sum(map(len,gt.values())); aps=[]; at_threshold=None
    for iou_threshold in np.arange(.5,.951,.05):
        matched={k:set() for k in gt}; tp=[]
        for p in parsed:
            options=[(box_iou(p["box"],box),i) for i,box in enumerate(gt[p["image_id"]]) if i not in matched[p["image_id"]]]
            overlap,index=max(options,default=(0,-1))
            hit=index>=0 and overlap>=iou_threshold-1e-9
            if hit: matched[p["image_id"]].add(index)
            tp.append(int(hit))
        cumulative=np.cumsum(tp); precision=cumulative/np.arange(1,len(tp)+1); recall=cumulative/max(n_gt,1)
        ap=float(np.mean([precision[recall>=r].max(initial=0) for r in np.linspace(0,1,101)])) if n_gt else None
        aps.append(ap)
        if abs(iou_threshold-.5)<1e-9:
            selected=[i for i,p in enumerate(parsed) if p["score"]>=threshold]
            true=sum(tp[i] for i in selected)
            at_threshold={"precision":true/len(selected) if selected else 0.0,"recall":true/n_gt if n_gt else None,"tp":true,"fp":len(selected)-true,"fn":n_gt-true}
    negatives={i for i,boxes in gt.items() if not boxes}
    false_images={p["image_id"] for p in parsed if p["image_id"] in negatives and p["score"]>=threshold}
    return {"AP50":aps[0],"AP50_95":float(np.mean(aps)) if n_gt else None,**at_threshold,"negative_image_false_positive_rate":len(false_images)/len(negatives) if negatives else None,"confidence_threshold":threshold,"images":len(images),"ground_truth_boxes":n_gt,"implementation":"single-class 101-point interpolated AP, without COCO area/maxDet/crowd conventions"}


def pixel_features(image: Image.Image) -> np.ndarray:
    rgb=np.asarray(image.convert("RGB"),dtype=float)/255; r,g,b=np.moveaxis(rgb,-1,0)
    return np.stack([r,g,b,r-g,r-b,g-b,r*g,r*b,g*b],axis=-1)


def train_color_detector(dataset_root: Path, *, seed=42, steps=120, pixels=4096) -> dict:
    """Weak box-supervised logistic pixel model. This is NOT YOLO or a deep detector."""
    version=read_json(dataset_root/"version.json"); train=[s for s in version["samples"] if s["split"]=="train"]
    if not train: raise ValueError("No training images")
    rng=np.random.default_rng(seed); x=[]; y=[]
    per=max(1,math.ceil(pixels/len(train)))
    for sample in train:
        with Image.open(resolve_artifact(dataset_root,sample["image"])) as im: features=pixel_features(im)
        labels=np.zeros(features.shape[:2],dtype=float)
        for x0,y0,x1,y1 in sample["boxes"]: labels[int(y0):math.ceil(y1),int(x0):math.ceil(x1)]=1
        index=rng.integers(0,labels.size,per)
        x.append(features.reshape(-1,9)[index]); y.append(labels.ravel()[index])
    x=np.concatenate(x)[:pixels]; y=np.concatenate(y)[:pixels]
    if not 0<y.sum()<len(y): raise ValueError("Training must include foreground and background pixels")
    mean=x.mean(0); scale=np.maximum(x.std(0),.05); x=(x-mean)/scale
    weights=np.zeros(9); bias=0.0
    balancing=np.where(y>0,.5/(y.mean()),.5/(1-y.mean())); loss=[]
    for _ in range(steps):
        probability=1/(1+np.exp(-np.clip(x@weights+bias,-30,30)))
        gradient=(probability-y)*balancing
        weights-=.1*((x.T@gradient)/len(y)+.001*weights); bias-=.1*float(gradient.mean())
        loss.append(float(-np.mean(balancing*(y*np.log(probability+1e-9)+(1-y)*np.log(1-probability+1e-9)))))
    return {"algorithm":"weak_box_supervised_logistic_color_baseline_not_YOLO","seed":seed,"steps":steps,"pixels":len(y),"mean":mean.tolist(),"scale":scale.tolist(),"weights":weights.tolist(),"bias":bias,"loss":loss,"dataset_version_sha256":sha256(dataset_root/"version.json")}


def predict_color_detector(model: dict, root: Path, truth: dict, probability_threshold=.6) -> list[dict]:
    result=[]
    for item in truth["images"]:
        with Image.open(resolve_artifact(root,item["file_name"])) as im: x=pixel_features(im)
        logits=((x-np.array(model["mean"]))/np.array(model["scale"]))@np.array(model["weights"])+model["bias"]
        probability=1/(1+np.exp(-np.clip(logits,-30,30)))
        for a,b,c,d in boxes_from_mask(probability>=probability_threshold,min_area=16):
            result.append({"image_id":item["id"],"category_id":1,"bbox":[a,b,c-a,d-b],"score":float(probability[b:d,a:c].max())})
    return result


def paired_yolo_experiment(spec_path: Path, output: Path) -> dict:
    """Two real YOLO trainings with equal image-list sizes and shared held-out data."""
    try:
        import yaml
        from ultralytics import YOLO
    except ImportError as exc:
        raise RuntimeError("Install evaluation extras for YOLO experiments") from exc
    from .io import new_directory
    spec=read_json(spec_path); weights=Path(spec["weights"]).resolve()
    if not weights.is_file(): raise ValueError("A local pretrained checkpoint is required; no automatic model download")
    output=new_directory(output)

    def read_dataset(path):
        path=Path(path).resolve(); data=yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(data,dict) or data.get("names") not in (["fire"],{0:"fire"}): raise ValueError("Dataset must be single-class fire")
        if "download" in data: raise ValueError("Automatic dataset download scripts are not accepted")
        root=Path(data.get("path",path.parent)); root=root if root.is_absolute() else path.parent/root
        resolved={}
        for split in ("train","val","test"):
            entry=data.get(split)
            if not isinstance(entry,str): raise ValueError("Each split must be one directory or text list")
            candidate=Path(entry); candidate=candidate if candidate.is_absolute() else root/candidate
            if candidate.is_dir(): files=sorted(p.resolve() for p in candidate.rglob("*") if p.suffix.lower() in {".png",".jpg",".jpeg"})
            else:
                files=[]
                for row in candidate.read_text(encoding="utf-8").splitlines():
                    if not row.strip(): continue
                    p=Path(row.strip()); files.append((candidate.parent/p).resolve() if not p.is_absolute() else p.resolve())
            if not files or any(not p.is_file() for p in files): raise ValueError(f"Missing or empty {split} split")
            resolved[split]=files
        return resolved

    baseline=read_dataset(spec["baseline_yaml"]); augmented=read_dataset(spec["augmented_yaml"])
    digest=lambda files:{sha256(p) for p in files}
    for split in ("val","test"):
        if digest(baseline[split])!=digest(augmented[split]): raise ValueError("Held-out validation/test images must be identical")
        def labels_for(files):
            result={}
            for path in files:
                parts=list(path.parts)
                if "images" not in parts: raise ValueError("YOLO image directories must have an images/ segment")
                parts[len(parts)-1-parts[::-1].index("images")]="labels"
                label_path=Path(*parts).with_suffix(".txt")
                if not label_path.is_file(): raise ValueError("Every held-out image needs a label file, including empty negatives")
                result[sha256(path)]=sha256(label_path)
            return result
        if labels_for(baseline[split])!=labels_for(augmented[split]): raise ValueError("Held-out labels must be identical across experiments")
    if digest(baseline["val"]) & digest(baseline["test"]): raise ValueError("Validation and test overlap")
    held=digest(baseline["val"]+baseline["test"])
    if any(digest(group["train"]) & held for group in (baseline,augmented)): raise ValueError("Training/test image leakage detected")
    size=max(len(baseline["train"]),len(augmented["train"]))
    reports={}; seed=int(spec.get("seed",42)); epochs=int(spec.get("epochs",5)); batch=int(spec.get("batch",4))
    for name,group in (("baseline",baseline),("augmented",augmented)):
        for split in ("train","val","test"):
            files=group[split]
            if split=="train": files=[files[i%len(files)] for i in range(size)]
            (output/f"{name}_{split}.txt").write_text("\n".join(p.as_posix() for p in files)+"\n",encoding="utf-8")
        dataset={"path":output.as_posix(),"train":f"{name}_train.txt","val":f"{name}_val.txt","test":f"{name}_test.txt","names":{0:"fire"}}
        yaml_path=output/f"{name}.yaml"; yaml_path.write_text(yaml.safe_dump(dataset),encoding="utf-8")
        model=YOLO(str(weights)); model.train(data=str(yaml_path),epochs=epochs,batch=batch,imgsz=int(spec.get("imgsz",384)),seed=seed,deterministic=True,pretrained=False,workers=0,device=spec.get("device","cpu"),project=str(output),name=name,exist_ok=False,patience=epochs+1,amp=False,plots=False)
        iterations=len(model.trainer.train_loader)*epochs
        checkpoint=Path(model.trainer.best).resolve()
        metrics=YOLO(str(checkpoint)).val(data=str(yaml_path),split="test",workers=0,device=spec.get("device","cpu"),project=str(output),name=name+"_test",plots=False)
        reports[name]={"mAP50":float(metrics.box.map50),"mAP50_95":float(metrics.box.map),"precision":float(metrics.box.mp),"recall":float(metrics.box.mr),"train_iterations":iterations,"best_checkpoint":str(checkpoint)}
        write_json(output/"partial_results.json",reports)
    comparable=reports["baseline"]["train_iterations"]==reports["augmented"]["train_iterations"]
    delta=reports["augmented"]["mAP50"]-reports["baseline"]["mAP50"]
    report={"groups":reports,"comparable_training_iterations":comparable,"mAP50_delta_pp":100*delta,"relative_gain":delta/reports["baseline"]["mAP50"] if reports["baseline"]["mAP50"] else None,"weights_sha256":sha256(weights),"seed":seed,"spec":spec,"note":"Confirm event/parent grouping independently; hash checks detect exact file leakage only. No effect claim is valid if training budgets differ."}
    write_json(output/"comparison.json",report)
    return report
