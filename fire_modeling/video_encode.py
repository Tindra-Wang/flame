"""Run with Blender's bundled FFmpeg encoder, no extra system package."""
import json,sys
from pathlib import Path
import bpy

spec=json.loads(Path(sys.argv[sys.argv.index('--')+1]).read_text(encoding='utf-8'))
scene=bpy.context.scene;scene.sequence_editor_create();fps=spec['fps']
scene.render.resolution_x=spec['width'];scene.render.resolution_y=spec['height'];scene.render.resolution_percentage=100
scene.render.fps=fps;scene.render.image_settings.file_format='FFMPEG'
scene.render.ffmpeg.format='MPEG4';scene.render.ffmpeg.codec='H264';scene.render.ffmpeg.constant_rate_factor='MEDIUM'
scene.render.filepath=spec['output'];scene.view_settings.view_transform='Standard'
frames=spec['frames'];start=frames[0]['time_s'];end=max(2,round((frames[-1]['time_s']-start)*fps)+1)
for i,entry in enumerate(frames):
    first=1+round((entry['time_s']-start)*fps)
    last=1+round((frames[i+1]['time_s']-start)*fps) if i+1<len(frames) else end+1
    if last<=first:continue
    strip=scene.sequence_editor.strips.new_image(str(i),str(Path(spec['root'])/entry['file']),channel=1,frame_start=first)
    strip.frame_final_duration=last-first
scene.frame_start=1;scene.frame_end=end
bpy.ops.render.render(animation=True)
