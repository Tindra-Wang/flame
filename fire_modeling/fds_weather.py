"""Physical atmosphere inputs, separate from render weather and image augmentation."""
import math


def validate_weather(config):
    for key,lo,hi in [('ambient_relative_humidity_pct',0,100),('rain_mm_h',0,50),('rain_diameter_um',100,3000)]:
        value=getattr(config,key)
        if isinstance(value,bool) or not isinstance(value,(float,int)) or not math.isfinite(value) or not lo<=value<=hi:
            raise ValueError('FDS气象参数越界：'+key)
    if config.physical_weather not in {'晴','雨'}:raise ValueError('尚未接入雪粒融化/积雪模型，不能将视觉降雪当作FDS物理工况')
    if (config.physical_weather=='雨')!=(config.rain_mm_h>0):raise ValueError('雨工况必须给出正降雨强度，晴天不能携带降雨量')
    if config.rain_mm_h and config.ambient_temperature_c<=0:raise ValueError('当前液态雨滴模型要求环境温度大于0℃；冰雪相变未接入')


def rain_input(config):
    validate_weather(config)
    if not config.rain_mm_h:return []
    x,y,z=config.room_size_m;dx=config.cell_size_m
    # 1 mm/h = 1 kg/(m2 h). Numerical parcels carry the physical mass flux.
    mass=config.rain_mm_h*x*y/3600
    return ["&SPEC ID='WATER VAPOR' /",
        f"&PART ID='AMBIENT_RAIN', SPEC_ID='WATER VAPOR', DIAMETER={config.rain_diameter_um:g}, SAMPLING_FACTOR=10 /",
        f"&INIT ID='RAIN_TOP', PART_ID='AMBIENT_RAIN', XB=0,{x:g},0,{y:g},{z-dx:g},{z-dx/2:g}, N_PARTICLES=200, DT_INSERT=0.2, MASS_PER_TIME={mass:.10g}, UVW=0,0,-4 /",
        f"! RAIN: {config.rain_mm_h:g} mm/h; mass flux {mass:.10g} kg/s; top injection, monodisperse liquid approximation"]


def condition(config):
    return {'weather':config.physical_weather,'temperature_c':config.ambient_temperature_c,
        'relative_humidity_pct':config.ambient_relative_humidity_pct,'wind_m_s':config.wind_m_s,
        'rain_mm_h':config.rain_mm_h,'rain_diameter_um':config.rain_diameter_um,
        'source':'FDS_boundary_and_liquid_particles',
        'limitation':'规定HRR等效火源；未标定降雨抑制/燃料含水率/雪相变。Blender目前不导入FDS雨滴轨迹。'}
