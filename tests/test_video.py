from pathlib import Path
import pytest
from PIL import Image
from fire_modeling import video
from fire_modeling.adapters import RenderResult
from fire_modeling.config import SceneConfig
from fire_modeling.io import write_json,sha256,read_json


def test_encoded_boundaries_are_separate_from_physical_time():
    item=video.playback_metadata({'timeline':[{'time_s':0},{'time_s':20/11},{'time_s':20}]})
    assert item['timeline'][1]['playback_start_s']==22/12
    assert item['timeline'][1]['time_s']==20/11
    assert item['playback_duration_s']==241/12
    dense=video.playback_metadata({'timeline':[{'time_s':0},{'time_s':.01},{'time_s':1}]})
    assert not dense['timeline'][0]['encoded'] and dense['timeline'][1]['encoded']


def test_video_uses_fixed_camera_chronological_real_fields(tmp_path,monkeypatch):
    c=SceneConfig(width=64,height=64);volume=tmp_path/'physics/volume';volume.mkdir(parents=True)
    frames=[]
    for i in range(3):
        path=volume/f'{i}.npz';path.write_bytes(bytes([i]))
        frames.append({'time_s':float(i),'file':path.name,'sha256':sha256(path)})
    write_json(volume/'volume.json',{'schema':'ai07.fds-volume.v1','status':'success','frames':frames})
    write_json(tmp_path/'physics/handoff.json',{'config':c.to_dict(),'volume_sha256':sha256(volume/'volume.json')})
    requests=[]
    class Engine:
        def render(self,request):
            requests.append(request)
            return RenderResult(Image.new('RGB',(64,64)),Image.new('L',(64,64)),'fds_openvdb_volume')
    def encode(args,**kw):
        spec=read_json(Path(args[-1]));Path(spec['output']).write_bytes(b'fake-test-mp4'*20)
    monkeypatch.setattr(video.subprocess,'run',encode)
    result=video.render_video(c,tmp_path,renderer=Engine())
    assert [r.volume.name for r in requests]==['0.npz','1.npz','2.npz']
    assert {r.viewpoint for r in requests}=={'侧视'}
    assert all(r.positive and r.weather=='clear' and r.seed==c.seed for r in requests)
    assert result['videos'][0]['source_frames']==3
    video.render_video(c,tmp_path,renderer=Engine())
    assert len(requests)==3
    assert read_json(tmp_path/'video/progress.json')['completed']==3
    video.validate_video(tmp_path,read_json(tmp_path/'physics/handoff.json')['config'])
    (tmp_path/'video/camera-0.mp4').write_bytes(b'tampered')
    with pytest.raises(ValueError,match='视频校验'):video.validate_video(tmp_path,read_json(tmp_path/'physics/handoff.json')['config'])


def test_video_worker_and_reused_generation_have_separate_plans(tmp_path,monkeypatch):
    from platform_api import worker
    monkeypatch.setattr(worker,'ROOT',tmp_path)
    p={'config':SceneConfig().to_dict(),'route':'physics','count':2,'enhance':True}
    plan=worker.command_plan({'id':'a'*24,'kind':'video','payload':p})
    assert [v[0] for v in plan]==['physics','video'] and 'video' in plan[-1][1]
    p['source_simulation_id']='b'*24
    plan=worker.command_plan({'id':'c'*24,'kind':'generate','payload':p})
    assert [v[0] for v in plan]==['blender','enhance'] and '--source-root' in plan[0][1]
    p['source_simulation_id']='../../escape'
    with pytest.raises(ValueError):worker.command_plan({'id':'d'*24,'kind':'generate','payload':p})
