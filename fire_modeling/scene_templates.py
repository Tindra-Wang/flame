"""Small editable cases with distinct geometry. No upstream source mutations."""
import copy
from .editor_contract import bind_config
from .mesh_recommendation import recommend_mesh


def wall(id,xb,name=None):
    return {'id':id,'name':name or id,'role':'inert','center':[(xb[i]+xb[i+1])/2 for i in (0,2,4)],'size':[xb[i+1]-xb[i] for i in (0,2,4)]}


def room_shell(x,y,z,door=True):
    t=.2
    result=[wall('west',(0,t,0,y,0,z),'西墙'),wall('south',(0,x,0,t,0,z),'南墙'),wall('north',(0,x,y-t,y,0,z),'北墙'),wall('ceiling',(0,x,0,y,z-t,z),'顶板')]
    if door:
        a=y/2-.6;b=y/2+.6
        result += [wall('east-a',(x-t,x,0,a,0,z),'门侧墙A'),wall('east-b',(x-t,x,b,y,0,z),'门侧墙B'),wall('lintel',(x-t,x,a,b,2.2,z),'门梁')]
    return result


def piece(asset,x,y,z,size=None,fuel='木材'):
    return {'asset_id':asset,'x':x,'y':y,'z':z,'yaw':0,'fuel_type':fuel,'ignition':False,**({'size':size} if size else {})}


TEMPLATES={
 'furnished-room':{'name':'家具房间 · 门口通风','scenario':'房间火灾','domain':[6,4,3],'origin':[1.2,1.2,.2],'hrr':180,'fire':[.6,.6],
    'description':'小型房间、门洞与家具遮挡，保留火源上方空间。','structures':room_shell(6,4,3),
    'placements':[piece('painted_wooden_sofa',3.8,2.8,.4),piece('WoodenTable_01',4.5,1.1,.375)]},
 'corridor':{'name':'走廊 · 端部开口','scenario':'房间火灾','domain':[10,2.4,3],'origin':[2,1.2,.2],'hrr':200,'fire':[.6,.6],
    'description':'狭长走廊与端部开口，观察受限空间的烟气输运。','structures':room_shell(10,2.4,3,False),
    'placements':[piece('wooden_crate_01',5,1.7,.4),piece('WoodenTable_01',7.5,.7,.375,size=[1.2,.6,.75])]},
 'warehouse':{'name':'仓储 · 两排堆物通道','scenario':'房间火灾','domain':[8,6,3],'origin':[2,3,.2],'hrr':300,'fire':[.8,.8],
    'description':'两排货架与中间通道，检查局部遮挡及烟气通道。','structures':room_shell(8,6,3)+[wall('rack-a',(3.5,7,1,1.6,0,2),'货架A'),wall('rack-b',(3.5,7,4.4,5,0,2),'货架B')],
    'placements':[piece('wooden_crate_01',4,2.1,.4),piece('wooden_crate_01',5.5,3.9,.4)]},
 'shrubland':{'name':'灌木场地 · 小尺度横风','scenario':'林区火灾','domain':[8,6,4],'origin':[2,3,.2],'hrr':300,'fire':[.8,.8],'wind':1,
    'description':'缩小室外计算域，布置疏密灌木；风作用进入FDS。','structures':[],
    'placements':[piece('potted_plant_04',4,1.2,.4,size=[.8,.8,.8],fuel='植被'),piece('potted_plant_04',5.2,4.5,.5,size=[1,1,1],fuel='植被'),piece('potted_plant_04',6.5,2.8,.4,size=[.8,.8,.8],fuel='植被')]},
 'wood-yard':{'name':'木堆场地 · 遮挡与横风','scenario':'林区火灾','domain':[6,6,3],'origin':[2,2,.2],'hrr':250,'fire':[.8,.8],'wind':.6,
    'description':'木箱/木堆形成障碍，留出直接观察火源的机位。','structures':[],
    'placements':[piece('wooden_crate_01',4,1.2,.4),piece('wooden_crate_01',4,3.4,.4),piece('wooden_crate_01',4,3.4,1.2)]},
 'industrial-yard':{'name':'工业场地 · 设备与油类火源','scenario':'工业区火灾','domain':[8,6,4],'origin':[2,2,.2],'hrr':350,'fire':[.8,.8],'wind':.5,'fuel':'汽油',
    'description':'小尺度设备障碍与规定HRR油类等效火源；不含储罐爆炸模型。','structures':[wall('equipment',(4,5.2,3.8,5,0,2),'设备障碍'),wall('rack',(5.5,7,1,1.5,0,1.6),'管架简化体')],
    'placements':[piece('wooden_crate_01',6,3,.4),piece('wooden_crate_01',6.8,4.8,.4)]},
}


def build_template(id):
    if id not in TEMPLATES:raise ValueError('未知场景模板')
    t=copy.deepcopy(TEMPLATES[id]);x,y,z=t['origin']
    raw={'scenario':t['scenario'],'revision':1,'domain':t['domain'],'origin':t['origin'],'origin_fuel':t.get('fuel','木材'),'structures':t['structures'],'placements':t['placements'],'viewpoints':['侧视'],
        'cameras':{'侧视':{'location':([5.5,3,1.6] if id=='warehouse' else [min(t['domain'][0]-.5,x+2.8),max(.5,y-1.7),1.6]),'target':[x,y,1.1],'focal_mm':32}}}
    base={'scene_id':'tpl_'+id.replace('-','_'),'cell_size_m':.1,'peak_hrr_kw':t['hrr'],'fire_size_m':t['fire'],'duration_s':12,'ramp_up_s':2,'width':512,'height':512,'render_samples':48,
          'wind_m_s':t.get('wind',0),'ambient_temperature_c':20}
    recommendation=recommend_mesh(base,raw)
    config=bind_config({**base,'cell_size_m':recommendation['recommended']['cell_size_m']},raw)
    return config,recommendation


def template_catalog():
    result=[]
    for id,t in TEMPLATES.items():
        c,r=build_template(id)
        result.append({'id':id,'name':t['name'],'base_scenario':t['scenario'],'description':t['description'],'domain_m':list(c.room_size_m),
            'cell_size_m':c.cell_size_m,'cells':r['recommended']['cells'],'warnings':r['warnings'],'geometry':'项目自建简化几何；规定HRR，非真实材料热解校准'})
    return result
