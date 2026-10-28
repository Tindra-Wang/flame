from dataclasses import replace
import copy
import pytest
from fire_modeling.config import SceneConfig
from fire_modeling.editor_contract import upstream,normalize_scene,bind_config,solver_boxes
from fire_modeling.physics import fds_input


def scene():
    p=upstream();return {'scenario':'房间火灾','origin_fuel':'木材','placements':p.catalog_extras()['defaults']['房间火灾'],'viewpoints':['侧视','俯视']}


def test_editor_shapes_cameras_and_fuel_enter_one_fds_contract():
    raw=scene();raw['origin_fuel']='汽油';raw['cameras']={'侧视':{'location':[4,1.2,1],'target':[1.2,1.2,.7],'focal_mm':40}}
    c=bind_config(SceneConfig().to_dict(),raw);text=fds_input(c)
    assert c.room_size_m==(8,6,3) and len(solver_boxes(c))==10
    assert 'object_0' in text and 'structure_' in text and 'SOOT_YIELD=0.11' in text
    assert '1.2,1.2,0,0' not in text
    assert c.editor_scene['cameras']['侧视']['location']==[4.,1.2,1.]
    assert normalize_scene(c.editor_scene)==c.editor_scene


def test_editor_rejects_outside_unknown_nonfinite_and_private_paths():
    raw=scene();raw['placements'][0]['asset_path']='C:/private.glb'
    assert 'asset_path' not in normalize_scene(raw)['placements'][0]
    raw['placements'][0]['x']=100
    with pytest.raises(ValueError):normalize_scene(raw)
    with pytest.raises(ValueError):normalize_scene({**scene(),'surprise':'ignored?'})
    with pytest.raises(ValueError):normalize_scene({**scene(),'origin':[float('nan'),1,0]})


def test_editor_grid_mapping_and_ignition_budget():
    raw=scene();raw['placements'][0]['ignition']=True
    c=bind_config(SceneConfig().to_dict(),raw);text=fds_input(c)
    assert 'IGNITION_' in text and "SURF_IDS='IGNITION_" in text
    assert c.editor_scene['placements'][0]['ignition'] is True
    coarse=bind_config(replace(SceneConfig(),cell_size_m=.5).to_dict(),raw)
    assert all(abs(n/.5-round(n/.5))<1e-8 for n in coarse.room_size_m)


def test_mesh_recommendation_balances_fire_detail_and_domain_budget():
    from fire_modeling.mesh_recommendation import recommend_mesh
    base=SceneConfig().to_dict()
    indoor=recommend_mesh(base,scene())
    outdoor=recommend_mesh(base,{'scenario':'林区火灾','placements':[],'viewpoints':['侧视']})
    assert indoor['recommended']['cell_size_m']<outdoor['recommended']['cell_size_m']
    assert indoor['recommended']['within_budget'] and outdoor['recommended']['within_budget']
    assert not outdoor['recommended']['detail_starting_target_met'] and outdoor['warnings']
    stronger=recommend_mesh({**base,'peak_hrr_kw':1000},scene())
    assert stronger['characteristic_fire_diameter_m']>indoor['characteristic_fire_diameter_m']
    multiple=scene();multiple['placements'][0]['ignition']=True
    split=recommend_mesh(base,multiple)
    assert split['burner_count']==2 and split['per_burner_peak_hrr_kw']==50
    assert split['characteristic_fire_diameter_m']<indoor['characteristic_fire_diameter_m']
    assert base==SceneConfig().to_dict()
    with pytest.raises(ValueError):recommend_mesh({**base,'peak_hrr_kw':float('nan')},scene())


def test_business_templates_have_distinct_geometry_and_feasible_fds_meshes():
    from fire_modeling.scene_templates import TEMPLATES,build_template
    signatures=set()
    for key in TEMPLATES:
        config,recommendation=build_template(key)
        config.validate()
        assert recommendation['recommended']['cells']<=120000
        assert recommendation['recommended']['volume_nodes']<=160000
        assert recommendation['recommended']['domain_exact']
        text=fds_input(config)
        assert '&MESH' in text and 'origin_support' in text
        signatures.add(str((config.editor_scene['domain'],config.editor_scene['placements'],config.editor_scene['structures'])))
        camera=config.editor_scene['cameras']['侧视']['location']
        for box in solver_boxes(config):
            xb=box['bounds']
            assert not all(xb[2*i]<camera[i]<xb[2*i+1] for i in range(3)),key
    assert len(signatures)==6
