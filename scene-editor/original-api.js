const project=new URLSearchParams(location.search).get('project')||'ai07'
export const bridgeProject=encodeURIComponent(project)
export const compatibilityPrefix=`/api/projects/${bridgeProject}/scene-editor/compat`
export async function originalApi(path,options={}){
 const route=path.replace('/api/v1',`/api/projects/${encodeURIComponent(project)}/scene-editor/compat`)
 const response=await fetch(route,{credentials:'same-origin',...options,headers:{'Content-Type':'application/json',...options.headers}})
 const data=await response.json().catch(()=>({}));if(response.status===401)window.dispatchEvent(new Event('editor-login-required'));if(!response.ok)throw new Error(data.detail||'请求失败，请查看作业日志');return data
}
