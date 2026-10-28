"""Validate numeric/diagram contracts and package native editable diagram pages."""
import hashlib
import json
import re
import struct
from pathlib import Path
import xml.etree.ElementTree as ET
import zlib

from PIL import Image,ImageChops

ROOT=Path(__file__).resolve().parents[2]; OUT=ROOT/'docs/design'


def png_dpi(path):
    # Change physical-resolution metadata only, preserve pixels and embedded diagram.
    data=path.read_bytes(); assert data[:8]==b'\x89PNG\r\n\x1a\n'
    result=data[:8]; offset=8
    while offset<len(data):
        size=struct.unpack('>I',data[offset:offset+4])[0]
        type=data[offset+4:offset+8]; chunk=data[offset:offset+12+size]
        assert zlib.crc32(chunk[4:-4])&0xffffffff==struct.unpack('>I',chunk[-4:])[0]
        if type!=b'pHYs': result+=chunk
        if type==b'IHDR':
            payload=struct.pack('>IIB',11811,11811,1); body=b'pHYs'+payload
            result+=struct.pack('>I',len(payload))+body+struct.pack('>I',zlib.crc32(body)&0xffffffff)
        offset+=12+size
    assert offset==len(data)
    path.write_bytes(result)


def main():
    from estimate import calculate
    estimate=json.loads((OUT/'estimate.json').read_text(encoding='utf-8'))
    assert calculate()==estimate
    assert (estimate['logical_finish'],estimate['resource_finish'],estimate['project_buffer'],estimate['planned_commitment'])==(44,56,9,65)
    assert estimate['cash_ceiling'] is None and estimate['labor_hours']==381
    assert estimate['assumptions']['team']==5
    assert set(estimate['role_hours'])=={'PM','AR','DEV','QA','OPS'}
    assert all(t['total_cost'] is None and t['labor_cost'] is None for t in estimate['tasks'])
    assert all(r['unit_price'] is None for r in estimate['resource_plan'])
    relations=json.loads((OUT/'er-global-relations.json').read_text(encoding='utf-8'))
    adjacency={n['id']:set() for n in relations['entities']}
    for a,b,*_ in relations['relations']:
        adjacency[a].add(b); adjacency[b].add(a)
    visited=set(); todo=['project']
    while todo:
        n=todo.pop()
        if n in visited: continue
        visited.add(n); todo.extend(adjacency[n]-visited)
    assert len(visited)==len(adjacency)==24, 'Global ER must connect all entities'
    pages=sorted(p for p in OUT.glob('*.drawio') if re.match(r'\d\d_',p.name))
    assert len(pages)==10
    bundle=ET.Element('mxfile',{'host':'app.diagrams.net','type':'device','version':'31.4.5'})
    evidence=[]
    for index,path in enumerate(pages,1):
        root=ET.parse(path).getroot(); page=root.find('diagram'); assert page is not None
        graph=page.find('mxGraphModel'); assert graph is not None
        ids={x.get('id') for x in graph.findall('.//mxCell')}
        for e in graph.findall('.//mxCell'):
            if e.get('edge')=='1': assert e.get('source') in ids and e.get('target') in ids
        if path.stem.startswith('09_'):
            all_labels=' '.join(c.get('value','') for c in graph.findall('.//mxCell'))
            assert '¥' not in all_labels and '￥' not in all_labels
            assert '待定' in all_labels
        if path.stem.startswith('10_'):
            vertices=[c for c in graph.findall('.//mxCell') if c.get('vertex')=='1' and c.get('parent')=='1']
            styles=[c.get('style','') for c in vertices]
            assert sum('shape=ellipse;' in s for s in styles)==24
            assert sum('shape=rhombus;' in s for s in styles)==30
            assert sum('fontStyle=4' in s for s in styles)==24
            # The actual editable graph must also be a single connected component.
            native={c.get('id'):set() for c in vertices if 'text;' not in c.get('style','')}
            for c in graph.findall('.//mxCell'):
                if c.get('edge')=='1':
                    a,b=c.get('source'),c.get('target'); native[a].add(b); native[b].add(a)
            seen=set(); queue=[next(iter(native))]
            while queue:
                a=queue.pop()
                if a in seen: continue
                seen.add(a); queue.extend(native[a]-seen)
            assert len(seen)==len(native)
        if path.stem.startswith(('06_','07_')):
            vertices=[c for c in graph.findall('.//mxCell') if c.get('vertex')=='1' and c.get('parent')=='1']
            styles=[c.get('style','') for c in vertices]
            assert sum('shape=ellipse;' in s for s in styles)>=36
            assert sum('shape=rhombus;' in s for s in styles)>=6
            assert sum('fontStyle=4' in s for s in styles)>=12
            for e in graph.findall('.//mxCell'):
                if e.get('edge')=='1': assert 'endArrow=none' in e.get('style','')
        page.set('name',path.stem); page.set('id',f'AI07-page-{index:02d}'); bundle.append(page)
        png=path.with_suffix('.png'); png_dpi(png)
        with Image.open(png) as image:
            image.load(); assert image.width>2000 and image.height>2000
            assert abs(image.info['dpi'][0]-300)<.01
            gray=image.convert('RGB'); white=Image.new('RGB',gray.size,'white'); difference=ImageChops.difference(gray,white)
            # The cropped wide first export had a white lower half: guard the footnotes.
            assert difference.crop((0,int(gray.height*.8),gray.width,gray.height)).getbbox() is not None
            evidence.append(dict(page=path.stem,png_size=list(image.size),dpi=image.info['dpi'],editable_cells=len(ids)))
    ET.ElementTree(bundle).write(OUT/'AI07_完整设计图集.drawio',encoding='utf-8',xml_declaration=True)
    api=json.loads((OUT/'openapi.design.yaml').read_text(encoding='utf-8'))
    for path,methods in api['paths'].items():
        required=set(re.findall(r'{(.*?)}',path))
        for method,op in methods.items():
            provided={p['name'] for p in op.get('parameters',[]) if p['in']=='path'}
            assert required==provided
    ddl=(OUT/'schema.design.sql').read_text(encoding='utf-8'); assert ddl.count('CREATE TABLE ')==24
    doc=(OUT/'软件设计与低成本实施方案.md').read_text(encoding='utf-8')
    for word in ['Blender','FDS','Stable Diffusion','Label Studio','DVC','Web','SonarQube','PPT','PIA','ES','ED','LS','LE','70%','云端可运行Demo']:
        assert word in doc,word
    assert hashlib.sha256((ROOT/'SRS.md').read_bytes()).hexdigest()=='ac5d169a268e0ef63b1209cb3e4366eee1923c5bab38af8553190be202b574d2'
    report=dict(date='2026-10-18',kind='design_artifact_validation_not_software_acceptance',pages=evidence,team=5,roles=estimate['assumptions']['roles'],logical_workdays=44,resource_workdays=56,project_buffer=9,commitment_workdays=65,remaining_labor_hours=381,pricing_status="unpriced",cash_budget_assumption=None,economic_budget_assumption=None,global_er_entities=24,global_er_relationships=30,global_er_connected=True,ddl_tables=24,openapi_paths=len(api['paths']),notes=['XML graph references and PNG structure verified','Chen rectangles/ellipses/diamonds/underlined keys and arrowless relationships verified','All 17 task costs use symbolic formulas; rates and currency amounts are unset','Ten exported pages visually inspected; global ER export scale reduced to correct clipping','Some bound-edge/waypoint routing heuristics remain warnings; intentional forks and ordinary crossings are not dependency nodes','DDL is a proposed schema; not applied to PostgreSQL','OpenAPI is a proposed contract; HTTP endpoints not implemented','SRS unchanged; this does not certify algorithm metrics or full product acceptance'])
    (OUT/'design-validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    scratch=ROOT/'.drawio-tmp/design'; scratch.mkdir(parents=True,exist_ok=True)
    (scratch/'visual-review.json').write_text(json.dumps({'round':7,'artifact':'docs/design/*.png','resolved':['wide-pert-export-clipping','ER-edge-through-object','PERT-edge-through-object','architecture-edge-through-LabelStudio','class-edge-through-LabelPort','UML-interface-realization-style','UML-include-precondition-ambiguity','ER-label-overlap','schedule-cost-document-drift','five-fixed-role-resourcing','Chen-standard-native-symbols','PERT-task-cost-accounting','global-ER-24-entity-connectivity','unpriced-cost-formulas','compact-ER-layout-and-domain-colors'],'remaining_blockers':[],'nonblocking':'Intentional fork corridors and waypoint-bound-edge heuristic warnings remain; exported PNGs are canonical visual evidence.'},ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='pages'},ensure_ascii=False,indent=2))


if __name__=='__main__': main()
