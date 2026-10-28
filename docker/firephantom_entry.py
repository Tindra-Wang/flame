"""Deployment adapter; keep the imported source intact and enforce API sessions."""
from firephantom.api import create_app, _current_user
from fastapi.responses import JSONResponse

app=create_app()
PUBLIC={'/api/v1/auth/me','/api/v1/auth/bootstrap','/api/v1/auth/login',
        '/api/v1/catalog','/api/v1/system/status'}

@app.middleware('http')
async def session_boundary(request,call_next):
    if request.method not in {'GET','HEAD','OPTIONS'}:
        origin=request.headers.get('origin')
        if origin and origin not in {'http://localhost:8765','http://127.0.0.1:8765'}:
            return JSONResponse({'detail':'请求来源不受信任'},status_code=403)
    protected=request.url.path.startswith(('/api/v1/','/assets/')) and request.url.path not in PUBLIC
    if protected and _current_user(request) is None:
        return JSONResponse({'detail':'请先登录FirePhantom工作台'},status_code=401)
    return await call_next(request)
