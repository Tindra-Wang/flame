"""Fixed-camera FDS videos and the same source frames as dataset candidates."""
from pathlib import Path
import subprocess
import time,json,hashlib
from .adapters import RenderRequest,create_renderer
from .io import read_json,write_json,sha256,new_directory,resolve_artifact
from .volume import select_frame
from .config import SceneConfig
from .synthesis_contracts import RenderProfile


def playback_metadata(item,fps=12):
    """Mirror video_encode's frame boundaries; keep solver time independent."""
    rows=item['timeline'];start=rows[0]['time_s']
    end=max(2,round((rows[-1]['time_s']-start)*fps)+1)
    timeline=[]
    for i,row in enumerate(rows):
        first=round((row['time_s']-start)*fps)
        last=round((rows[i+1]['time_s']-start)*fps) if i+1<len(rows) else end
        timeline.append({**row,'playback_start_s':first/fps,'encoded':last>first})
    return {**item,'fps':fps,'playback_duration_s':end/fps,'timeline':timeline}


def render_video(config,root,blender='blender',renderer=None):
    physics=root/'physics';handoff=read_json(physics/'handoff.json')
    if SceneConfig.from_dict(handoff['config'])!=config:raise ValueError('视频与求解配置不一致')
    volume=physics/'volume';report=read_json(volume/'volume.json')
    if sha256(volume/'volume.json')!=handoff['volume_sha256']:raise ValueError('视频三维场清单校验失败')
    frames=report['frames']
    if len(frames)<2 or any(b['time_s']<=a['time_s'] for a,b in zip(frames,frames[1:])):
        raise ValueError('视频需要至少两个递增求解时间帧')
    out=root/'video';out.mkdir(exist_ok=True);engine=renderer or create_renderer('blender',blender)
    views=config.editor_scene['viewpoints'] if config.editor_scene else ['侧视']
    videos=[];started=time.monotonic();completed=0;total=len(views)*len(frames)
    profile=RenderProfile().to_dict()
    fingerprint=hashlib.sha256(json.dumps({'config':config.to_dict(),'profile':profile},sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    def progress(phase,view):write_json(out/'progress.json',{'phase':phase,'viewpoint':view,'completed':completed,'total':total,'elapsed_s':time.monotonic()-started})
    for v,view in enumerate(views):
        timeline=[]
        for i,entry in enumerate(frames):
            path,actual=select_frame(volume,entry['time_s'])
            work=out/f'camera-{v}'/f'{i:04d}'
            image=work/'frame.png';checkpoint=work/'frame-state.json';reusable=False
            if checkpoint.is_file() and image.is_file():
                previous=read_json(checkpoint);reusable=previous=={'config':fingerprint,'volume':actual['sha256'],'viewpoint':view,'image':sha256(image)}
            elif image.is_file() and (work/'job.json').is_file() and (work/'render.json').is_file():
                old=read_json(work/'job.json');record=read_json(work/'render.json')
                reusable=SceneConfig.from_dict(old['config'])==config and old.get('viewpoint')==view and record.get('route')=='fds_openvdb_volume' and record.get('volume_file')==path.name and record.get('optical_transfer')==profile
            progress('固定机位渲染',view)
            if not reusable:
                result=engine.render(RenderRequest(config,work,config.seed,config.camera_angles_deg[v],
                    'clear',1,True,path,view,profile))
                if result.source!='fds_openvdb_volume':raise ValueError('视频禁止非FDS渲染回退')
                image.parent.mkdir(parents=True,exist_ok=True);result.image.save(image);result.mask.save(work/'mask.png')
            else:print(f'video {view}: 复用完成帧 {i+1}',flush=True)
            write_json(checkpoint,{'config':fingerprint,'volume':actual['sha256'],'viewpoint':view,'image':sha256(image)})
            timeline.append({'time_s':entry['time_s'],'file':str(image.relative_to(out)),
                'sha256':sha256(image),'volume_sha256':actual['sha256']})
            print(f'video {view}: {i+1}/{len(frames)}',flush=True)
            completed+=1;progress('固定机位渲染',view)
        output=out/f'camera-{v}.mp4'
        spec={'width':config.width,'height':config.height,'fps':12,'frames':timeline,
              'root':str(out.resolve()),'output':str(output.resolve())}
        write_json(out/f'encode-{v}.json',spec)
        progress('MP4编码',view)
        with (out/f'encode-{v}.log').open('w',encoding='utf-8') as log:
            subprocess.run([blender,'--background','--factory-startup','--python',
                str(Path(__file__).with_name('video_encode.py')),'--',str(out/f'encode-{v}.json')],
                stdout=log,stderr=subprocess.STDOUT,check=True,timeout=300)
        if not output.is_file() or output.stat().st_size<100:raise ValueError('MP4编码结果不存在')
        videos.append({'viewpoint':view,'file':output.name,'sha256':sha256(output),
            'weather':config.physical_weather,'source_frames':len(timeline),'start_s':timeline[0]['time_s'],'end_s':timeline[-1]['time_s'],
            'timeline':timeline})
    from .fds_weather import condition
    result={'physical_conditions':condition(config),'schema':'ai07.simulation-video.v1','status':'success','config':config.to_dict(),
        'scene_revision':(config.editor_scene or {}).get('revision'),'videos':videos,'render_profile':profile,
        'sampling':'固定相机；真实求解时刻逐帧渲染；时间间隔内保持最近帧，无AI补帧；12fps编码不代表求解帧率'}
    write_json(out/'video.json',result)
    # The very same frames/masks enter review; no second rendering is necessary.
    from PIL import Image
    import numpy as np
    from .annotations import boxes_from_mask
    from .quality import inspect_run
    samples=[]
    for vi,item in enumerate(videos):
        for f,entry in enumerate(item['timeline']):
            mask_file=str(Path(entry['file']).parent/'mask.png')
            with Image.open(out/mask_file) as mask:
                boxes=boxes_from_mask(np.asarray(mask.convert('L'))>32)
            field=next(e for e in frames if e['sha256']==entry['volume_sha256'])
            samples.append({'sample_id':f'{config.scene_id}_v{vi}_f{f:03d}','image':entry['file'],'mask':mask_file,'sha256':entry['sha256'],'width':config.width,'height':config.height,'boxes':boxes,'source':'fds_openvdb_volume','seed':config.seed,'group_id':root.name,'parent_id':None,'expected_fire':field.get('max_hrrpuv_kw_m3',0)>1,'physical_volume':{**field,'backend':'FDS'},'scene_editor':{'revision':(config.editor_scene or {}).get('revision'),'viewpoint':item['viewpoint']},'combo_index':vi,'frame_index':f,'weather':config.physical_weather,'annotation_status':'pending_review'})
    manifest={'status':'success_candidates_only','config':config.to_dict(),'samples':samples,'stages':[{'name':'fds_video_frames','status':'success'}]}
    write_json(out/'manifest.json',manifest);write_json(out/'quality.json',inspect_run(out,manifest));progress('完成','')
    return result


def validate_video(root,config):
    video=read_json(root/'video/video.json')
    if video.get('status')!='success' or SceneConfig.from_dict(video.get('config',{}))!=SceneConfig.from_dict(config):raise ValueError('视频未完成或场景不一致')
    if not video.get('videos'):raise ValueError('缺少视频')
    for item in video['videos']:
        path=resolve_artifact(root/'video',item['file'])
        if path.suffix!='.mp4' or sha256(path)!=item['sha256']:raise ValueError('视频校验失败')
        if len(item['timeline'])<2:raise ValueError('视频缺少时间序列')
        for entry in item['timeline']:
            if sha256(resolve_artifact(root/'video',entry['file']))!=entry['sha256']:raise ValueError('视频帧校验失败')
    return video
