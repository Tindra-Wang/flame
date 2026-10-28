"""Page-native review bridge. Service credentials stay in the existing LS adapter."""
import copy,uuid
from . import integrations as ls
from .db import Link
from .services import sample_views,root_for
from fire_modeling.io import sha256,resolve_artifact
from fire_modeling.synthesis_contracts import fingerprint


def status(db,run):
    link=db.get(Link,run.id);value=link.value if link else {};pushed=value.get('pushed_reviews',{})
    reviewed=[s for s in sample_views(run) if s.get('review')]
    pending=[s for s in reviewed if pushed.get(s['sample_id'],{}).get('revision')!=s['review']['revision']]
    return {'connected':bool(link),'project_id':value.get('project_id'),'url':value.get('url'),
            'reviewed':len(reviewed),'pending_sync':len(pending),'mode':'platform_review_backend_sync'}


def push(db,run):
    """Explicit repair also retries a saved review after LS was unavailable."""
    with ls.review_lock:
        ls.label_sync(db,run);db.commit();link=db.get(Link,run.id)
        value=copy.deepcopy(link.value);done=value.setdefault('pushed_reviews',{})
        config=ls.label_config(db)
        tasks=ls.label_request(config,'GET',f'projects/{value["project_id"]}/export?exportType=JSON&download_all_tasks=true')
        by_id={t['data'].get('sample_id'):t for t in tasks};count=0
        for sample in sample_views(run):
            review=sample.get('review')
            if not review or done.get(sample['sample_id'],{}).get('revision')==review['revision']:continue
            if review['image_sha256']!=sha256(resolve_artifact(root_for(run),sample['image'])):raise ValueError('审核图像已改变，不能同步')
            task=by_id.get(sample['sample_id'])
            if not task:raise ValueError('Label Studio缺少对应任务，请检查批次同步')
            unique=str(uuid.uuid5(uuid.NAMESPACE_URL,'ai07:'+run.id+':'+sample['sample_id']))
            previous=done.get(sample['sample_id'],{})
            annotation=next((a for a in task.get('annotations',[]) if a.get('unique_id')==unique or a.get('id')==previous.get('annotation_id')),None)
            if annotation and previous.get('remote_hash') and fingerprint(annotation['result'])!=previous['remote_hash']:
                raise ValueError('Label Studio标签已修改，请先回导并在平台确认后同步')
            if not annotation and task.get('annotations'):raise ValueError('Label Studio存在其他人工标签，请先回导并确认')
            boxes=review['boxes'];w=sample['width'];h=sample['height']
            result=[{'id':f'box{i}','from_name':'fire_box','to_name':'image','type':'rectanglelabels','original_width':w,'original_height':h,'image_rotation':0,
                     'value':{'x':x0/w*100,'y':y0/h*100,'width':(x1-x0)/w*100,'height':(y1-y0)/h*100,'rotation':0,'rectanglelabels':['fire']}} for i,(x0,y0,x1,y1) in enumerate(boxes)]
            body={'result':result if review['decision']=='approved' else [],'was_cancelled':review['decision']=='rejected','ground_truth':False,'unique_id':unique}
            saved=ls.label_request(config,'PATCH',f'annotations/{annotation["id"]}/',json=body) if annotation else ls.label_request(config,'POST',f'tasks/{task["id"]}/annotations/',json=body)
            done[sample['sample_id']]={'revision':review['revision'],'annotation_id':saved['id'],'remote_hash':fingerprint(saved['result']),'reviewer':review['reviewer'],'decision':review['decision']}
            link.value=copy.deepcopy(value);db.commit();count+=1
        return {**status(db,run),'synced':count}


def acknowledge_pull(db,run):
    """A deliberate pull accepts the remote revision as the synchronization base."""
    link=db.get(Link,run.id)
    if not link:return
    value=copy.deepcopy(link.value);tasks=ls.label_request(ls.label_config(db),'GET',f'projects/{value["project_id"]}/export?exportType=JSON&download_all_tasks=true')
    reviews={s['sample_id']:s['review'] for s in sample_views(run) if s.get('review')}
    for t in tasks:
        sid=t['data'].get('sample_id');annotations=[a for a in t.get('annotations',[]) if not a.get('was_cancelled')]
        if sid in reviews and len(annotations)==1:
            a=annotations[0];r=reviews[sid]
            value.setdefault('pushed_reviews',{})[sid]={'revision':r['revision'],'annotation_id':a['id'],'remote_hash':fingerprint(a['result']),'reviewer':r['reviewer'],'decision':r['decision']}
    link.value=value
