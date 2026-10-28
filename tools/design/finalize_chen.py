"""Apply exact Chen styles from canonical specs, unsupported by stock renderer.

Native XML finishing only: no raster manipulation, external upload, or skill edits.
Run after cli.js conversion and before draw.io Desktop PNG export.
"""
import json
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[2]


def main():
    for name in ['06_ER核心数据','07_ER治理评价','10_ER全局联系']:
        spec=json.loads((ROOT/f'docs/design/specs/{name}.spec.yaml').read_text(encoding='utf-8'))
        path=ROOT/f'docs/design/{name}.drawio'
        tree=ET.parse(path); cells=tree.findall('.//mxCell')
        vertices=[c for c in cells if c.get('vertex')=='1' and c.get('parent')=='1']
        connectors=[c for c in cells if c.get('edge')=='1']
        assert len(vertices)==len(spec['nodes']) and len(connectors)==len(spec['edges'])
        for cell,node in zip(vertices,spec['nodes']):
            style=cell.get('style','')
            if node['type']=='text': continue
            # Stock renderer ignores raw shape/rounded/dashed node overrides.
            shape=node['style'].get('shape','rectangle')
            style+=';shape='+shape+';rounded=0;'
            if shape=='ellipse': style+='perimeter=ellipsePerimeter;'
            if shape=='rhombus': style+='perimeter=rhombusPerimeter;'
            if node['style'].get('dashed'): style+='dashed=1;dashPattern=6 4;'
            cell.set('style',style)
        for cell,edge in zip(connectors,spec['edges']):
            if edge['style'].get('edgeStyle')=='none':
                cell.set('style',cell.get('style','')+';edgeStyle=none;')
        tree.write(path,encoding='utf-8',xml_declaration=True)
        print(f'Chen native shapes and straight attribute links: {name}')


if __name__=='__main__': main()
