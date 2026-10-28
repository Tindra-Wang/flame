"""Pure synthesis contracts/planning. No HTTP, database, Blender or ML imports."""
from dataclasses import dataclass,asdict
from itertools import product
import hashlib,json,math


def fingerprint(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,allow_nan=False).encode()).hexdigest()


@dataclass(frozen=True)
class RenderProfile:
    name:str='visible-v1'
    soot_density_gain:float=800
    hrrpuv_cutoff_kw_m3:float=1
    hrrpuv_emission_gain:float=.012
    exposure:float=.5
    color_mode:str='reaction_ramp'

    def to_dict(self):return asdict(self)

    @classmethod
    def parse(cls,value=None):
        value=value or {}
        if not isinstance(value,dict):raise ValueError('渲染配置必须为对象')
        if set(value)-set(cls.__dataclass_fields__):raise ValueError('未知渲染配置')
        p=cls(**value)
        for key,lo,hi in [('soot_density_gain',0,10000),('hrrpuv_cutoff_kw_m3',0,1000),('hrrpuv_emission_gain',.00001,1),('exposure',-3,3)]:
            n=getattr(p,key)
            if not isinstance(n,(int,float)) or not math.isfinite(n) or not lo<=n<=hi:raise ValueError('渲染参数越界：'+key)
        if not isinstance(p.name,str) or not 1<=len(p.name)<=80:raise ValueError('渲染配置名称不合法')
        if not isinstance(p.color_mode,str) or p.color_mode not in {'blackbody','reaction_ramp'}:raise ValueError('未知火焰颜色映射')
        return p


BASELINE=RenderProfile('baseline-v1',3000,40,.0015,0,'blackbody').to_dict()


def build_plan(sources,options):
    """Sources are already authorized and hash-verified by the application layer."""
    allowed={'weathers','viewpoints','time_count','modes','variants','profile','controlnet','strength','steps'}
    if not isinstance(options,dict):raise ValueError('合成选项必须为对象')
    if set(options)-allowed:raise ValueError('未知合成选项')
    if not 1<=len(sources)<=8 or len({s['id'] for s in sources})!=len(sources):raise ValueError('选择1至8个不同的已完成FDS工况')
    defaults={'weathers':['clear'],'viewpoints':['侧视'],'time_count':2,'modes':['background'],'variants':1,'controlnet':False,'strength':.45,'steps':24}
    o={**defaults,**options};o['profile']=RenderProfile.parse(o.get('profile')).to_dict()
    for key,choices in [('weathers',{'clear','fog','rain','snow'}),('viewpoints',{'侧视','俯视','第一人称'}),('modes',{'background','flame'})]:
        v=o[key]
        if not isinstance(v,list) or any(not isinstance(x,str) for x in v) or len(set(v))!=len(v) or set(v)-choices or (key!='modes' and not v):raise ValueError('合成选项不合法：'+key)
    for key,lo,hi in [('time_count',1,12),('variants',1,3),('steps',10,50)]:
        if type(o[key])!=int or not lo<=o[key]<=hi:raise ValueError('数量越界：'+key)
    if type(o['controlnet'])!=bool or not isinstance(o['strength'],(int,float)) or not math.isfinite(o['strength']) or not .1<=o['strength']<=.85:raise ValueError('增强强度需为0.1至0.85')
    items=[]
    for source in sources:
        frames=[f for f in source['frames'] if f['time_s']>0 and f.get('max_hrrpuv_kw_m3',0)>1]
        if len(frames)<o['time_count']:raise ValueError('工况'+source['id'][:8]+'含火时间帧不足，请减少时刻数或增加求解采样')
        n=o['time_count'];indices=[round(i*(len(frames)-1)/(n-1)) for i in range(n)] if n>1 else [len(frames)-1]
        for frame,weather,view in product([frames[i] for i in indices],o['weathers'],o['viewpoints']):
            key={'source':source['id'],'field':frame['sha256'],'profile':o['profile'],'weather':weather,'viewpoint':view}
            items.append({'sample_id':'raw_'+fingerprint(key)[:20],'source_id':source['id'],'field':frame,'weather':weather,'viewpoint':view,'cache_key':fingerprint(key)})
    augmented=len(items)*len(o['modes'])*o['variants']
    if len(items)>64 or augmented>128:raise ValueError('本机每批限64张原图和128张增强图，请缩减组合')
    return {'schema':'ai07.synthesis-plan.v1','options':o,'sources':sources,'items':items,
            'counts':{'reused_fds_cases':len(sources),'new_fds_solves':0,'raw':len(items),'requested_augmented':augmented,'requested_total':len(items)+augmented},
            'weather_role':'visual_only_not_fds_weather','camera_policy':'saved_when_present_else_scene_default','time_selection':'在已有含火时刻中均匀选取；不插值新物理帧'}
