export async function api(path:string,method='GET',data?:unknown) {
  const response=await fetch('/api'+path,{method,headers:data instanceof FormData?{}:{'Content-Type':'application/json'},credentials:'same-origin',body:data===undefined?undefined:data instanceof FormData?data:JSON.stringify(data)})
  if(!response.ok){const e=await response.json().catch(()=>({detail:'服务暂时不可用'}));throw new Error(typeof e.detail==='string'?e.detail:JSON.stringify(e.detail))}
  return response.json()
}
export const time=(t:number)=>new Date(t*1000).toLocaleString('zh-CN',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'})
export const statusNames:Record<string,string>={pending:'待审核',approved:'已通过',rejected:'已剔除',queued:'排队中',running:'执行中',succeeded:'已完成',failed:'失败',interrupted:'已中断',cancelled:'已取消',published:'已发布',staging:'发布中',physics:'物理生成',preview:'程序预览',real:'真实导入'}
