"""Compose stage entrypoints. Files are the only cross-service contract."""
import argparse
import copy
from pathlib import Path
import shutil

from PIL import Image

from .config import SceneConfig
from .enhancement import DiffusionEnhancer,SafetyRejected
from .io import new_directory, read_json, sha256, write_json
from .physics import run_fds
from .pipeline import run_pipeline
from .quality import inspect_run


def simulate(config, output):
    root=new_directory(output)
    csv=run_fds(config,root,"fds")
    editor_manifest={}
    if config.editor_scene:
        from .editor_contract import resolved_scene,upstream,solver_boxes
        scene,spec=resolved_scene(config.editor_scene)
        models=upstream().normalize_placements(spec,scene['placements'],scene['origin_fuel'])
        editor_manifest={'schema':'ai07.editor-handoff.v1','scene_revision':scene['revision'],'scenario':scene['scenario'],
          'solver_boxes':solver_boxes(config),'origin_input_m':scene['origin'],
          'cameras':scene['cameras'],'models':[{'asset_id':m['asset_id'],'sha256':sha256(Path(m['asset_path'])) if m['asset_path'] else None} for m in models],
          'limitation':'FDS网格吸附及旋转AABB近似；等效燃料，无真实热解/自动蔓延标定。'}
        write_json(root/'editor-scene.json',editor_manifest)
    from .volume import export_volume
    from .simulation import export_simulation
    export_volume(root,config.output_frames)
    export_simulation(root)
    write_json(root/"handoff.json",{"status":"success","config":config.to_dict(),"hrr_csv":csv.name,"sha256":sha256(csv),
                                  "volume_manifest":"volume/volume.json","volume_sha256":sha256(root/'volume/volume.json'),
                                  **({'editor_manifest':'editor-scene.json','editor_sha256':sha256(root/'editor-scene.json')} if editor_manifest else {})})


def enhance(source, output, model, device):
    manifest=read_json(source/"manifest.json")
    if manifest["status"]!="success_candidates_only": raise ValueError("Source render did not complete")
    for sample in manifest["samples"]:
        if sha256(source/sample["image"])!=sample["sha256"]: raise ValueError("Source image checksum mismatch")
    new_directory(output)
    # Reuse image lineage without duplicating large Blender bake caches/scenes.
    for name in ('images','masks'):
        shutil.copytree(source/name,output/name)
    for name in ('config.json','reviews.json'):
        if (source/name).is_file(): shutil.copy2(source/name,output/name)
    manifest=copy.deepcopy(manifest)
    write_json(output/"manifest.json",{**manifest,"status":"enhancing"})
    try:
        engine=DiffusionEnhancer(str(model),device=device)
        for sample in list(manifest["samples"]):
            if not sample["expected_fire"]: continue
            prompt=('a sharp photograph of a warehouse interior, concrete floor, natural lighting' if manifest['config']['scene_type']=='indoor' else 'a sharp photograph of an industrial outdoor yard, detailed pavement, natural lighting')
            if sample.get('weather')=='fog': prompt+=', overcast misty surroundings'
            try:
                with Image.open(source/sample["image"]) as original, Image.open(source/sample['mask']) as mask:
                    image,params=engine.run(original.convert("RGB"),sample["seed"]+10000,prompt=prompt,mask=mask)
            except SafetyRejected as exc:
                manifest.setdefault('rejected_enhancements',[]).append({'sample_id':sample['sample_id'],'reason':str(exc)})
                print(f"SD候选被模型拒绝，已排除：{sample['sample_id']}",flush=True)
                continue
            sid=sample["sample_id"]+"_diffusion"
            image_path=output/"images"/(sid+".png"); image.save(image_path)
            manifest["samples"].append({**sample,"sample_id":sid,"image":"images/"+image_path.name,"sha256":sha256(image_path),"parent_id":sample["sample_id"],"source":"diffusion","enhancement":params,"annotation_status":"pending_review","label_source":"inherited_candidate_only_requires_review"})
        if not any(s.get('source')=='diffusion' for s in manifest['samples']):raise RuntimeError('SD候选均被排除；未产生可用增强图，原始渲染保留')
        manifest["status"]="success_candidates_only"
        manifest["stages"].append({"name":"diffusion","status":"partial" if manifest.get('rejected_enhancements') else 'success'})
        write_json(output/"quality.json",inspect_run(output,manifest))
    except Exception as exc:
        manifest["status"]="failed"; manifest["error"]=str(exc)
        raise
    finally:
        write_json(output/"manifest.json",manifest)


def main():
    p=argparse.ArgumentParser(); p.add_argument("stage",choices=["simulate","simulate-web","render","video","original","enhance","synthesis-render","synthesis-enhance"])
    p.add_argument('--source-root')
    p.add_argument("--config",default="/app/configs/room.json")
    p.add_argument("--root",default="/app/artifacts/compose-run")
    p.add_argument("--count",type=int,default=2)
    p.add_argument("--model",default="/app/models/sd15")
    p.add_argument("--device",default="cuda")
    a=p.parse_args(); root=Path(a.root)
    config=SceneConfig.from_dict(read_json(Path(a.config)))
    if a.source_root:
        source=Path(a.source_root).resolve()
        if not source.is_relative_to(Path('/app/artifacts/platform/jobs')):raise ValueError('求解来源越界')
        saved=SceneConfig.from_dict(read_json(source/'physics/handoff.json')['config'])
        if saved!=config:raise ValueError('复用求解必须使用同一份场景配置')
        shutil.copytree(source/'physics',root/'physics')
        if a.stage=='video' and (source/'video').is_dir():
            for entry in (source/'video').rglob('*'):
                if entry.is_file() and entry.suffix in {'.png','.json','.mp4'}:
                    dest=root/'video'/entry.relative_to(source/'video');dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(entry,dest)
    if a.stage in {'synthesis-render','synthesis-enhance'}:
        from .synthesis_pipeline import render_plan,augment_plan
        plan=read_json(root/'synthesis-plan.json')
        (render_plan if a.stage=='synthesis-render' else augment_plan)(root,plan)
    elif a.stage in {"simulate","simulate-web"}:
        simulate(config,root/"physics")
    elif a.stage=='original':
        from .original_editor import run_original
        run_original(config,root,read_json(root/'generation.json'))
    elif a.stage=='video':
        from .video import render_video
        render_video(config,root)
    elif a.stage=="render":
        run_pipeline(config,root/"render",count=a.count,renderer="blender",enhancer="none",external_fds=root/"physics")
    else: enhance(root/"render",root/"enhanced",Path(a.model),a.device)
    print(f"Stage {a.stage} completed: {root}",flush=True)


if __name__=="__main__": main()
