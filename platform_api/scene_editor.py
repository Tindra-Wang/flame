"""Main-platform scene editor adapters: same auth, same scenes, local assets."""
import hashlib
import re
from pathlib import Path
from fire_modeling.editor_contract import upstream,normalize_scene
from fire_modeling.io import read_json,write_json


def catalog(root,project):
    from fire_modeling.scene_templates import template_catalog
    p=upstream();data=p.catalog_extras();data['templates']=template_catalog()
    for row in data['assets']:
        file=root/'artifacts/scene-assets/library'/f"{row['asset_id']}.glb"
        row['url']=f"/api/projects/{project}/scene-assets/builtin/{row['asset_id']}.glb" if file.is_file() else None
        row['representation']='内置简模' if file.is_file() else '燃料盒（原模型未安装）'
        if file.is_file():
            row['label']+=' · 简模';row['source']='AI-07程序生成';row['license']='项目自建几何';row['note']='本项目内置简模，非原第三方资产文件'
        else:row['label']+=' · 燃料盒'
    data.update(scenarios=list(data['shells']),viewpoints=['侧视','俯视','第一人称'])
    return data


def uploads(root,project):
    file=root/'artifacts/scene-assets/projects'/project/'uploads.json'
    return read_json(file) if file.is_file() else []


def assert_assets(root,project,scene):
    if not scene:return
    permitted={a['asset_id'] for a in uploads(root,project)}
    for p in scene.get('placements',[]):
        if p.get('asset_id','').startswith('upload:') and p['asset_id'] not in permitted:
            raise ValueError('该上传模型不属于当前项目')


def store_asset(root,project,data,name):
    p=upstream()
    if len(data)>p.MAX_GLB_BYTES:raise ValueError('模型不能超过8MB')
    document=p._gltf_json(data)
    for item in document.get('buffers',[])+document.get('images',[]):
        if item.get('uri') and not item['uri'].startswith('data:'):raise ValueError('GLB不能引用外部文件或网络资源')
    stats=p.glb_stats(data);token=hashlib.sha256(data).hexdigest()[:16]
    file=root/'artifacts/scene-assets/uploads'/f'{token}.glb';file.parent.mkdir(parents=True,exist_ok=True)
    if not file.is_file():file.write_bytes(data)
    record={'asset_id':'upload:'+token,'label':Path(name).stem[:80],'size':list(p.placement_size(stats['size'])),'triangles':stats['triangles']}
    record['url']=f"/api/projects/{project}/scene-assets/upload/{record['asset_id'].split(':')[1]}.glb"
    record['fuel_type']='木材';record['group']='我的上传'
    rows=uploads(root,project);rows=[record]+[r for r in rows if r['asset_id']!=record['asset_id']]
    write_json(root/'artifacts/scene-assets/projects'/project/'uploads.json',rows)
    return record


def asset_file(root,project,kind,filename):
    if kind=='builtin':
        if not re.fullmatch(r'[A-Za-z0-9_-]+\.glb',filename):raise ValueError('模型路径不合法')
        if filename[:-4] not in upstream().PRESETS:raise ValueError('未知模型')
        return root/'artifacts/scene-assets/library'/filename
    if kind!='upload' or not re.fullmatch(r'[0-9a-f]{16}\.glb',filename):raise ValueError('上传模型路径不合法')
    if 'upload:'+filename[:-4] not in {a['asset_id'] for a in uploads(root,project)}:raise ValueError('该模型不属于项目')
    return root/'artifacts/scene-assets/uploads'/filename
