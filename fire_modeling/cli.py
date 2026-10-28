"""Command-line application layer; adapters remain independently replaceable."""
from __future__ import annotations

import argparse
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys

from .config import SceneConfig
from .io import new_directory, read_json, write_json


def doctor() -> dict:
    packages={}
    for name,distribution in (("numpy","numpy"),("PIL","Pillow"),("scipy","scipy"),("torch","torch"),("diffusers","diffusers"),("pytorch_fid","pytorch-fid"),("ultralytics","ultralytics")):
        available=importlib.util.find_spec(name) is not None
        try: version=importlib.metadata.version(distribution) if available else None
        except importlib.metadata.PackageNotFoundError: version="unknown"
        packages[name]={"available":available,"version":version}
    engines={}
    for name,key in (("fds","FDS_EXE"),("blender","BLENDER_EXE")):
        candidate=os.getenv(key,name); found=shutil.which(candidate) or (str(Path(candidate).resolve()) if Path(candidate).is_file() else None)
        engines[name]=found
    return {"python":sys.executable,"isolated_venv":sys.prefix!=sys.base_prefix,"packages":packages,"engines":engines,"note":"Availability is not proof of engine/model integration. Missing requested adapters fail explicitly."}


def contact_sheet(root: Path, samples: list[dict]) -> Path:
    from PIL import Image,ImageDraw,ImageOps
    columns=4; cell=224; selected=samples[:16]; rows=(len(selected)+columns-1)//columns
    sheet=Image.new("RGB",(columns*cell,max(rows,1)*(cell+40)),"#f3f4f5"); draw=ImageDraw.Draw(sheet)
    for i,s in enumerate(selected):
        image=Image.open(root/s["image"]).convert("RGB"); overlay=ImageDraw.Draw(image)
        for box in s["boxes"]: overlay.rectangle(tuple(box),outline=(0,255,160),width=2)
        image=ImageOps.contain(image,(cell-8,cell-8))
        x=(i%columns)*cell+4; y=(i//columns)*(cell+40)+4; sheet.paste(image,(x,y))
        draw.text((x,y+cell),s["sample_id"][:30],fill="black")
        draw.text((x,y+cell+14),"CANDIDATE - NOT REVIEWED",fill="black")
    target=root/"contact_sheet.png"; sheet.save(target); return target


def parser():
    p=argparse.ArgumentParser(description="AI-07 local modeling pipeline; external algorithms use separate optional adapters")
    sub=p.add_subparsers(dest="command",required=True)
    sub.add_parser("doctor",help="Show this interpreter's dependencies and external engines")
    for name in ("prepare","generate"):
        q=sub.add_parser(name); q.add_argument("--config",type=Path,required=True); q.add_argument("--output",type=Path,required=True)
        if name=="generate":
            q.add_argument("--count",type=int,default=12); q.add_argument("--renderer",choices=["preview","blender"],default="preview")
            q.add_argument("--physics",choices=["none","fds"],default="none"); q.add_argument("--enhancer",choices=["none","photometric","diffusion"],default="photometric")
            q.add_argument("--fds-exe",default=os.getenv("FDS_EXE","fds")); q.add_argument("--blender-exe",default=os.getenv("BLENDER_EXE","blender"))
            q.add_argument("--model-dir"); q.add_argument("--device",choices=["cpu","cuda"],default="cpu")
    q=sub.add_parser("demo",help="Run the explicitly procedural CPU preview for two scenes")
    q.add_argument("--output",type=Path,required=True); q.add_argument("--count",type=int,default=8)
    q.add_argument("--configs-dir",type=Path,default=Path("configs"))
    q=sub.add_parser("review"); q.add_argument("--run",type=Path,required=True); q.add_argument("--sample",required=True); q.add_argument("--reviewer",required=True)
    q.add_argument("--decision",choices=["approved","rejected"],default="approved"); q.add_argument("--boxes-json",type=Path)
    q=sub.add_parser("publish"); q.add_argument("--run",type=Path,required=True); q.add_argument("--output",type=Path,required=True); q.add_argument("--version",required=True)
    q=sub.add_parser("export"); q.add_argument("--version-dir",type=Path,required=True); q.add_argument("--output",type=Path,required=True)
    q=sub.add_parser("quality"); q.add_argument("--run",type=Path,required=True)
    q=sub.add_parser("label-studio"); q.add_argument("--run",type=Path,required=True); q.add_argument("--image-base-url",required=True); q.add_argument("--output",type=Path,required=True)
    q=sub.add_parser("import-label-studio"); q.add_argument("--run",type=Path,required=True); q.add_argument("--tasks",type=Path,required=True); q.add_argument("--reviewer",required=True)
    q=sub.add_parser("import-coco"); q.add_argument("--images",type=Path,required=True); q.add_argument("--annotations",type=Path,required=True); q.add_argument("--output",type=Path,required=True); q.add_argument("--dataset-id",required=True); q.add_argument("--source-url",required=True); q.add_argument("--license-note",required=True)
    q=sub.add_parser("merge-runs"); q.add_argument("--runs",type=Path,nargs="+",required=True); q.add_argument("--output",type=Path,required=True)
    q=sub.add_parser("distribution"); q.add_argument("--real",type=Path,required=True); q.add_argument("--synthetic",type=Path,required=True); q.add_argument("--metric",choices=["color-js","fid"],default="color-js"); q.add_argument("--dims",type=int,default=64); q.add_argument("--output",type=Path,required=True)
    q=sub.add_parser("detection-metrics"); q.add_argument("--truth",type=Path,required=True); q.add_argument("--predictions",type=Path,required=True); q.add_argument("--output",type=Path,required=True)
    q=sub.add_parser("physical-error"); q.add_argument("--reference",type=Path,required=True); q.add_argument("--prediction",type=Path,required=True); q.add_argument("--output",type=Path,required=True)
    q=sub.add_parser("train-color"); q.add_argument("--version-dir",type=Path,required=True); q.add_argument("--output",type=Path,required=True)
    q=sub.add_parser("predict-color"); q.add_argument("--model",type=Path,required=True); q.add_argument("--dataset",type=Path,required=True); q.add_argument("--truth",type=Path,required=True); q.add_argument("--output",type=Path,required=True)
    q=sub.add_parser("train-yolo-pair"); q.add_argument("--spec",type=Path,required=True); q.add_argument("--output",type=Path,required=True)
    q=sub.add_parser("detector-pair"); q.add_argument("--root",type=Path,required=True)
    q=sub.add_parser("test",help="Run the local test suite")
    return p


def main(argv=None):
    args=parser().parse_args(argv)
    try:
        if args.command=="doctor": result=doctor()
        elif args.command=="test":
            import pytest
            return pytest.main(["tests","-q"])
        elif args.command in {"prepare","generate"}:
            from .pipeline import prepare,run_pipeline
            config=SceneConfig.from_dict(read_json(args.config))
            if args.command=="prepare": result=prepare(config,args.output)
            else:
                result=run_pipeline(config,args.output,count=args.count,renderer=args.renderer,physics=args.physics,fds_exe=args.fds_exe,blender_exe=args.blender_exe,enhancer=args.enhancer,model_dir=args.model_dir,device=args.device)
                contact_sheet(args.output,read_json(args.output/"manifest.json")["samples"])
        elif args.command=="demo":
            from .pipeline import run_pipeline
            from .quality import inspect_run
            root=new_directory(args.output); samples=[]; runs=[]
            for name in ("room","outdoor"):
                c=SceneConfig.from_dict(read_json(args.configs_dir/f"{name}.json"))
                child=root/c.scene_id; runs.append(run_pipeline(c,child,count=args.count))
                for s in read_json(child/"manifest.json")["samples"]:
                    samples.append({**s,"image":f"{c.scene_id}/{s['image']}","mask":f"{c.scene_id}/{s['mask']}"})
            manifest={"schema_version":1,"status":"success_candidates_only","route":"procedural_preview_not_cfd_or_diffusion","samples":samples,"runs":runs}
            write_json(root/"manifest.json",manifest); write_json(root/"quality.json",inspect_run(root,manifest)); sheet=contact_sheet(root,samples)
            result={"output":str(root),"samples":len(samples),"contact_sheet":str(sheet),"status":manifest["status"]}
        elif args.command=="review":
            from .dataset import review
            review(args.run,args.sample,args.reviewer,args.decision,read_json(args.boxes_json) if args.boxes_json else None); result={"sample":args.sample,"decision":args.decision}
        elif args.command=="publish":
            from .dataset import publish
            report=publish(args.run,args.output,args.version); result={"version":args.version,"counts":report["counts"]}
        elif args.command=="export":
            from .dataset import export_version
            result=export_version(args.version_dir,args.output)
        elif args.command=="quality":
            from .quality import inspect_run
            result=inspect_run(args.run,read_json(args.run/"manifest.json")); write_json(args.run/"quality.json",result)
        elif args.command=="label-studio":
            from .dataset import label_studio_tasks
            tasks=label_studio_tasks(args.run,args.image_base_url); write_json(args.output,tasks); result={"tasks":len(tasks),"output":str(args.output)}
        elif args.command=="import-label-studio":
            from .dataset import import_label_studio
            count=import_label_studio(args.run,read_json(args.tasks),args.reviewer); result={"imported_human_reviews":count}
        elif args.command=="import-coco":
            from .dataset import import_coco
            result=import_coco(args.images,args.annotations,args.output,args.dataset_id,args.source_url,args.license_note)
        elif args.command=="merge-runs":
            from .dataset import merge_runs
            result=merge_runs(args.runs,args.output)
        else:
            from . import evaluation as ev
            if args.command=="distribution": result=ev.distribution(args.real,args.synthetic,args.metric,args.dims)
            elif args.command=="detection-metrics": result=ev.detection_metrics(read_json(args.truth),read_json(args.predictions))
            elif args.command=="physical-error": result=ev.physical_error(read_json(args.reference),read_json(args.prediction))
            elif args.command=="train-color": result=ev.train_color_detector(args.version_dir)
            elif args.command=="predict-color": result=ev.predict_color_detector(read_json(args.model),args.dataset,read_json(args.truth))
            elif args.command=="train-yolo-pair": result=ev.paired_yolo_experiment(args.spec,args.output)
            elif args.command=="detector-pair":
                from .learning import run
                result=run(args.root)
            else: raise ValueError("Unknown operation")
            if args.command not in {"train-yolo-pair","detector-pair"}: write_json(args.output,result)
        print(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False))
        return 0
    except (ValueError,RuntimeError,OSError,ImportError,KeyError,TypeError) as exc:
        print(f"ERROR: {exc}",file=sys.stderr); return 2


if __name__=="__main__":
    raise SystemExit(main())
