"""Fixed-destination service discovery; do not share accounts, cookies or task writes."""
import os
import httpx

PUBLIC_URL='http://localhost:8765/'

def service_status():
    target=os.getenv('AI07_FIREPHANTOM_URL','http://127.0.0.1:8765').rstrip('/')
    # Destinations are deployment configuration, never a caller-supplied proxy URL.
    try:
        with httpx.Client(timeout=3,trust_env=False,follow_redirects=False) as client:
            response=client.get(target+'/health')
            available=response.status_code==200
    except httpx.HTTPError:
        available=False
    return {'available':available,'url':PUBLIC_URL,'open_url':'/api/integrations/firephantom/open',
            'integration':'独立服务入口；账户、作业、样本与版本暂不合并',
            'renderer':'Blender Mantaflow；参数化物理场，非FDS三维耦合',
            'sd':'仅保护火焰的背景重绘；需单独配置并验证SD服务'}
