from dataclasses import replace
import pytest
from fire_modeling.config import SceneConfig
from fire_modeling.physics import fds_input
from fire_modeling.editor_contract import upstream,bind_config


def test_humidity_and_rain_mass_flux_reach_fds_including_editor_scene():
    base=SceneConfig(scene_type='outdoor',ambient_relative_humidity_pct=85,physical_weather='雨',rain_mm_h=12,rain_diameter_um=900)
    for config in (base,bind_config(base.to_dict(),{'scenario':'林区火灾','domain':[4,4,3],'placements':[],'origin':[1,1,0],'structures':[],'viewpoints':['侧视']})):
        text=fds_input(config)
        assert 'HUMIDITY=85' in text and "PART_ID='AMBIENT_RAIN'" in text
        assert 'DIAMETER=900' in text
        assert f'MASS_PER_TIME={12*config.room_size_m[0]*config.room_size_m[1]/3600:.10g}' in text
        assert text.count("ID='RAIN_TOP'")==1
    dry=fds_input(replace(base,physical_weather='晴',rain_mm_h=0))
    assert 'AMBIENT_RAIN' not in dry


def test_invalid_and_unmodeled_weather_fails_explicitly():
    for changes in ({'physical_weather':'雪'},{'rain_mm_h':-1},{'physical_weather':'雨','rain_mm_h':5,'ambient_temperature_c':-5},{'ambient_relative_humidity_pct':float('nan')},{'physical_weather':'雨','rain_mm_h':0}):
        with pytest.raises(ValueError):replace(SceneConfig(),**changes).validate()
