"""Immutable reviewed inputs shared by distribution and detector experiments."""
from pathlib import Path
import shutil,math
from .io import read_json,write_json,sha256,resolve_artifact,new_directory
from .quality import inspect_sample
from .annotations import yolo_lines
from .dataset import ready_manifest


def freeze_reviewed(root,output,selection='all'):
    if selection not in {'all','raw','enhanced'}:raise ValueError('未知评价样本类型')
    m=ready_manifest(root);reviews=read_json(root/'reviews.json').get('current',{}) if (root/'reviews.json').is_file() else {}
    chosen=[];seen=set()
    for s in m['samples']:
        if selection=='raw' and s.get('source')=='diffusion' or selection=='enhanced' and s.get('source')!='diffusion':continue
        r=reviews.get(s['sample_id'])
        if not r or r['decision']!='approved':continue
        if r['image_sha256']!=s['sha256']:raise ValueError('审核与图像来源不一致')
        # Allow a human-confirmed negative; retain duplicate/hash and box gates.
        if s['sha256'] in seen or not inspect_sample(root,{**s,'boxes':r['boxes']})['structural_pass']:raise ValueError('审核样本有结构/重复问题，请修复后评价')
        seen.add(s['sha256'])
        chosen.append({**s,'boxes':r['boxes'],'review':r})
    if len(chosen)<2:raise ValueError('每组至少需要2张人工审核通过的有效图；小样本仅作流程诊断')
    target=new_directory(output)
    for i,s in enumerate(chosen):
        dest=target/'images'/f'{i:06d}.png';dest.parent.mkdir(exist_ok=True)
        shutil.copy2(resolve_artifact(root,s['image']),dest);s['image']=str(dest.relative_to(target)).replace('\\','/')
    result={'schema':'ai07.evaluation-input.v1','source_manifest_sha256':sha256(root/'manifest.json'),'selection':selection,'samples':chosen}
    write_json(target/'snapshot.json',result);return result


def load_version(root):
    for p,h in read_json(root/'checksums.json').items():
        if sha256(resolve_artifact(root,p))!=h:raise ValueError('数据版本哈希校验失败')
    v=read_json(root/'version.json')
    for s in v['samples']:
        if s['annotation_status']!='approved' or sha256(resolve_artifact(root,s['image']))!=s['sha256']:raise ValueError('版本存在未审核或改变的图像')
    return v


def detector_inputs(real_root,synthetic_root):
    real=load_version(real_root);synthetic=load_version(synthetic_root)
    if any(s['source']!='real' for s in real['samples']):raise ValueError('真实版本不能包含合成数据')
    if not synthetic['samples'] or any(s['source']=='real' or s['source'] not in {'fds_openvdb_volume','diffusion','blender'} for s in synthetic['samples']):raise ValueError('增强版本需为真实FDS/Blender或扩散候选审核后的版本，程序预览不可用于收益实验')
    splits={k:[s for s in real['samples'] if s['split']==k] for k in ('train','val','test')}
    syn=[s for s in synthetic['samples'] if s['split']=='train']
    if not all(splits.values()) or not syn:raise ValueError('真实版本需有独立train/val/test，合成版本需有train；请补充独立来源组后重新发布')
    groups=[{s['group_id'] for s in splits[k]} for k in ('train','val','test')]
    if any(groups[i]&groups[j] for i,j in ((0,1),(0,2),(1,2))):raise ValueError('真实事件来源组跨集合泄漏')
    held_hashes={s['sha256'] for s in splits['val']+splits['test']};held_groups=groups[1]|groups[2]
    if any(s['sha256'] in held_hashes or s['group_id'] in held_groups for s in splits['train']+syn):raise ValueError('训练样本与真实留出集存在重复或来源组泄漏')
    if not any(s['boxes'] for s in splits['test']):raise ValueError('真实测试集需包含有火样本')
    return splits,syn,held_hashes


def prepare_detector_pair(real_root,synthetic_root,output,weights,parameters):
    """Inputs are immutable DVC versions. Paths are interpreted inside the engine."""
    splits,syn,held_hashes=detector_inputs(real_root,synthetic_root)
    target=new_directory(output);lists={k:[] for k in ('train','val','test')};syn_files=[]
    def copy(rows,root,prefix,split):
        paths=[]
        for i,s in enumerate(rows):
            name=f'{prefix}_{split}_{i:06d}';dest=target/'images'/split/(name+'.png');dest.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(resolve_artifact(root,s['image']),dest)
            label=target/'labels'/split/(name+'.txt');label.parent.mkdir(parents=True,exist_ok=True)
            label.write_text(yolo_lines(s['boxes'],s['width'],s['height']),encoding='utf-8');paths.append(dest.as_posix())
        return paths
    for k,rows in splits.items():lists[k]=copy(rows,real_root,'real',k)
    syn_files=copy(syn,synthetic_root,'synthetic','train')
    import yaml
    for name,train in (('baseline',lists['train']),('augmented',lists['train']+syn_files)):
        for split in lists:(target/f'{name}_{split}.txt').write_text('\n'.join(train if split=='train' else lists[split])+'\n',encoding='utf-8')
        (target/f'{name}.yaml').write_text(yaml.safe_dump({'path':target.as_posix(),'train':f'{name}_train.txt','val':f'{name}_val.txt','test':f'{name}_test.txt','names':{0:'fire'}}),encoding='utf-8')
    spec={**parameters,'weights':str(weights),'baseline_yaml':str(target/'baseline.yaml'),'augmented_yaml':str(target/'augmented.yaml')}
    write_json(target/'spec.json',spec)
    counts={**{k:len(v) for k,v in splits.items()},'synthetic_train':len(syn)}
    lineage={'real_version_sha256':sha256(real_root/'version.json'),'synthetic_version_sha256':sha256(synthetic_root/'version.json'),'counts':counts,'group_checked':True,'test_image_hashes':sorted(held_hashes)}
    write_json(target/'lineage.json',lineage);return spec,lineage


def validate_pair_report(report):
    groups=report['groups']
    for name in ('baseline','augmented'):
        for key in ('mAP50','mAP50_95','precision','recall'):
            x=groups[name][key]
            if not isinstance(x,(int,float)) or not math.isfinite(x) or not 0<=x<=1:raise ValueError('检测指标不合法')
    if not report.get('comparable_training_iterations') or groups['baseline']['train_iterations']!=groups['augmented']['train_iterations']:raise ValueError('训练预算不一致，不能标为可比较实验')
    return {k:100*(groups['augmented'][k]-groups['baseline'][k]) for k in ('mAP50','mAP50_95','precision','recall')}
