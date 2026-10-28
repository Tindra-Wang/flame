"""A file-contract pipeline independent of any Web/database framework."""
from datetime import datetime,timezone
from pathlib import Path

from PIL import Image
import numpy as np

from .annotations import boxes_from_mask
from .adapters import RenderRequest, Renderer, create_renderer
from .config import SceneConfig
from .enhancement import DiffusionEnhancer, photometric
from .io import new_directory, read_json, resolve_artifact, sha256, write_json
from .physics import fds_input, run_fds, visual_hrr
from .quality import inspect_run


def prepare(config: SceneConfig, output: Path) -> dict:
    root=new_directory(output)
    write_json(root/"config.json",config.to_dict())
    (root/f"{config.scene_id}.fds").write_text(fds_input(config),encoding="utf-8")
    report={"status":"prepared_not_simulated","configuration":config.to_dict(),"fds_input":f"{config.scene_id}.fds"}
    write_json(root/"prepared.json",report)
    return report


def run_pipeline(config: SceneConfig, output: Path, *, count=12, renderer="preview", physics="none", fds_exe="fds", blender_exe="blender", enhancer="photometric", model_dir=None,device="cpu",augment_every=3, renderer_adapter: Renderer | None=None, external_fds: Path | None=None) -> dict:
    config.validate()
    if not 1<=count<=10000 or augment_every<1: raise ValueError("Invalid sample count or enhancement interval")
    if renderer not in {"preview","blender"} or physics not in {"none","fds"} or enhancer not in {"none","photometric","diffusion"}: raise ValueError("Unsupported pipeline adapter")
    root=new_directory(output)
    manifest={"schema_version":1,"status":"running","created_at":datetime.now(timezone.utc).isoformat(),"config":config.to_dict(),"renderer":renderer,"physics":physics,"samples":[],"stages":[]}
    write_json(root/"config.json",config.to_dict()); write_json(root/"manifest.json",manifest)
    try:
        hrr_csv=None; volume_dir=None
        if external_fds:
            state=read_json(external_fds/"handoff.json")
            if SceneConfig.from_dict(state["config"])!=config or state["status"]!="success":
                raise ValueError("FDS handoff configuration/status mismatch")
            hrr_csv=resolve_artifact(external_fds,state["hrr_csv"])
            if sha256(hrr_csv)!=state["sha256"]: raise ValueError("FDS handoff checksum mismatch")
            if state.get('volume_manifest'):
                volume_manifest=resolve_artifact(external_fds,state['volume_manifest'])
                if sha256(volume_manifest)!=state['volume_sha256']: raise ValueError('FDS volume manifest checksum mismatch')
                volume_dir=volume_manifest.parent
            if config.editor_scene:
                editor_path=resolve_artifact(external_fds,state['editor_manifest'])
                if sha256(editor_path)!=state['editor_sha256']:raise ValueError('三维编辑场景交接校验失败')
                from .editor_contract import resolved_scene,upstream
                editor,spec=resolved_scene(config.editor_scene)
                models=upstream().normalize_placements(spec,editor['placements'],editor['origin_fuel'])
                expected=read_json(editor_path)['models']
                for model,entry in zip(models,expected,strict=True):
                    digest=sha256(Path(model['asset_path'])) if model['asset_path'] else None
                    if model['asset_id']!=entry['asset_id'] or digest!=entry['sha256']:raise ValueError('FDS求解后模型文件已改变，请重建任务')
            manifest["physics"]="fds_external"
            manifest["stages"].append({"name":"fds","status":"success","handoff":state})
        elif physics=="fds":
            fds_dir=root/"fds"; fds_dir.mkdir(); hrr_csv=run_fds(config,fds_dir,fds_exe)
            from .volume import export_volume
            export_volume(fds_dir); volume_dir=fds_dir/'volume'
            manifest["stages"].append({"name":"fds","status":"success","hrr_csv":str(hrr_csv.relative_to(root))})
        else:
            (root/f"{config.scene_id}.fds").write_text(fds_input(config),encoding="utf-8")
            manifest["stages"].append({"name":"fds","status":"not_run","reason":"physical solving was not requested"})
        diffusion=DiffusionEnhancer(model_dir or "",device=device) if enhancer=="diffusion" else None
        if volume_dir and renderer!='blender': raise ValueError('FDS三维场只能交给Blender体积渲染，禁止以程序预览替代')
        engine=renderer_adapter or create_renderer(renderer,blender_exe)
        config_hash=sha256(root/"config.json")[:12]

        def save_sample(sample_id,image,mask,metadata):
            (root/"images").mkdir(exist_ok=True); (root/"masks").mkdir(exist_ok=True)
            image_path=root/f"images/{sample_id}.png"; image.save(image_path)
            mask_path=root/f"masks/{sample_id}.png"; mask.save(mask_path)
            boxes=boxes_from_mask(np.asarray(mask)>32)
            sample={"sample_id":sample_id,"image":str(image_path.relative_to(root)).replace("\\","/"),"mask":str(mask_path.relative_to(root)).replace("\\","/"),"sha256":sha256(image_path),"width":image.width,"height":image.height,"boxes":boxes,"annotation_status":"pending_review",**metadata}
            manifest["samples"].append(sample); write_json(root/"manifest.json",manifest)
            return sample

        for index in range(count):
            group=index//(len(config.camera_angles_deg)*len(config.weather))
            seed=config.seed+group
            angle=config.camera_angles_deg[index%len(config.camera_angles_deg)]
            weather=config.weather[(index//len(config.camera_angles_deg))%len(config.weather)]
            positive=index%5!=4 if volume_dir else index%5!=0
            # Physical-route views belong to one FDS source case and cannot be split.
            group_id=f"{config.scene_id}_{config_hash}_fds" if hrr_csv else f"{config.scene_id}_{config_hash}_trajectory_{group}"
            groups=max(1,(count+len(config.camera_angles_deg)*len(config.weather)-1)//(len(config.camera_angles_deg)*len(config.weather)))
            time_s=config.duration_s*(.4+.5*group/max(groups-1,1)) if volume_dir and count>=8 else config.duration_s*.8
            mapping=visual_hrr(config,time_s,hrr_csv)
            volume=None; volume_entry=None
            if volume_dir:
                from .volume import select_frame
                volume,volume_entry=select_frame(volume_dir,time_s)
            views=(config.editor_scene or {}).get('viewpoints') or []
            viewpoint=views[index%len(views)] if views else None
            rendered=engine.render(RenderRequest(config,root/f"blender/{index:05d}",seed,angle,weather,mapping["relative_strength"],positive,volume,viewpoint))
            image,mask,source=rendered.image,rendered.mask,rendered.source
            if hrr_csv and source=="mantaflow_visual_simulation": source="fds_hrr_driven_mantaflow_proxy"
            sid=f"{config.scene_id}_{index:05d}"
            metadata={"source":source,"group_id":group_id,"parent_id":None,"seed":seed,"angle_deg":angle,"weather":weather,"expected_fire":positive,"hrr_mapping":mapping,"label_source":"candidate_mask_requires_review"}
            if config.editor_scene:
                views=config.editor_scene.get('viewpoints') or ['侧视']
                metadata['scene_editor']={'revision':config.editor_scene['revision'],'scenario':config.editor_scene['scenario'],
                    'viewpoint':views[index%len(views)],'fuel':config.editor_scene['origin_fuel'],
                    'geometry':'FDS snapped boxes; Blender saved meshes','fuel_model':'equivalent fuel; no calibrated material pyrolysis'}
            if volume_entry:
                metadata['physical_volume']={**volume_entry,'schema':'ai07.fds-volume.v1','backend':'FDS','weather_role':'visual_only','optical_transfer':'uncalibrated'}
                metadata['hrr_mapping']={**mapping,'applied_to_flame':False,'limitation':'Flame rendered from FDS 3D HRRPUV/temperature/soot; total HRR retained only for provenance.'}
            if hrr_csv and not positive:
                metadata["source"]="counterfactual_visual_negative_not_fds_no_fire_case"
                metadata["hrr_mapping"]={**mapping,"applied_to_flame":False}
            save_sample(sid,image,mask,metadata)
            if enhancer!="none" and index%augment_every==1:
                enhanced,params=diffusion.run(image,seed+10000,mask=mask) if diffusion else photometric(image,seed+10000)
                save_sample(sid+"_aug",enhanced,mask,{**metadata,"parent_id":sid,"source":"diffusion" if diffusion else "classical_photometric","enhancement":params,"label_source":"inherited_candidate_only_requires_review"})
        manifest["status"]="success_candidates_only"
        manifest["stages"].append({"name":"render_and_candidates","status":"success","count":len(manifest["samples"])})
        write_json(root/"quality.json",inspect_run(root,manifest))
        write_json(root/"manifest.json",manifest)
    except Exception as exc:
        manifest["status"]="failed"; manifest["error"]=str(exc); write_json(root/"manifest.json",manifest)
        raise
    return {"output":str(root),"status":manifest["status"],"samples":len(manifest["samples"]),"note":"All labels are candidates; human review is required before publishing."}
