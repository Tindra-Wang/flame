import React,{useEffect,useState} from 'react'

async function request(url,method='GET',body){const r=await fetch(url,{method,credentials:'same-origin',headers:{'Content-Type':'application/json'},body:body?JSON.stringify(body):undefined});const d=await r.json();if(r.status===401)window.dispatchEvent(new Event('editor-login-required'));if(!r.ok)throw new Error(typeof d.detail==='string'?d.detail:'请求失败');return d}
const statusNames={queued:'排队中',running:'运行中',succeeded:'已完成',failed:'失败',interrupted:'已中断',cancelled:'已取消'}
const names={clear:'晴',fog:'雾',rain:'雨（视觉）',snow:'雪（视觉）'}
export function SynthesisPanel({project,sceneId,selectedJob,onSubmitted}){
 const prefix=`/api/projects/${encodeURIComponent(project)}`
 const [jobs,setJobs]=useState([]),[caps,setCaps]=useState({}),[sources,setSources]=useState([]),[weather,setWeather]=useState(['clear']),[views,setViews]=useState(['侧视']),[timeCount,setTimeCount]=useState(2),[mode,setMode]=useState('both'),[variants,setVariants]=useState(1),[controlnet,setControlnet]=useState(false),[profile,setProfile]=useState('visible'),[exposure,setExposure]=useState(.5)
 const [preview,setPreview]=useState(null),[result,setResult]=useState(null),[error,setError]=useState(''),[busy,setBusy]=useState(false),[filter,setFilter]=useState('all')
 const options={weathers:weather,viewpoints:views,time_count:timeCount,modes:mode==='none'?[]:mode==='both'?['background','flame']:[mode],variants,controlnet,profile:profile==='visible'?{exposure}:{name:'baseline-v1',soot_density_gain:3000,hrrpuv_cutoff_kw_m3:40,hrrpuv_emission_gain:.0015,exposure:0,color_mode:'blackbody'}}
 const key=JSON.stringify({source_ids:sources,options})
 useEffect(()=>{setPreview(null)},[key])
 useEffect(()=>{let live=true;const load=async()=>{try{const [j,c]=await Promise.all([request(prefix+'/jobs'),request(prefix+'/synthesis/capabilities')]);if(!live)return;setJobs(j);setCaps(c);setSources(old=>old.length?old:[j.find(x=>x.id===(selectedJob||new URLSearchParams(location.search).get('job'))&&x.kind==='video'&&x.status==='succeeded')?.id||j.find(x=>x.kind==='video'&&x.status==='succeeded'&&x.payload.scene_id===sceneId)?.id].filter(Boolean))}catch(e){if(live)setError(e.message)}};load();const timer=setInterval(load,4000);return()=>{live=false;clearInterval(timer)}},[project,sceneId])
 useEffect(()=>{setResult(null);if(!selectedJob||!jobs.some(j=>j.id===selectedJob&&j.kind==='synthesis'))return;let live=true;const load=async()=>{try{const r=await request(prefix+'/synthesis/jobs/'+selectedJob+'/result');if(live)setResult(r)}catch(e){if(live)setError(e.message)}};load();const timer=setInterval(load,4000);return()=>{live=false;clearInterval(timer)}},[selectedJob,jobs.some(j=>j.id===selectedJob&&j.kind==='synthesis')])
 const ready=jobs.filter(j=>j.kind==='video'&&j.status==='succeeded')
 const toggle=(values,set,value)=>set(values.includes(value)?values.filter(v=>v!==value):[...values,value])
 async function inspect(){setBusy(true);setError('');try{setPreview(await request(prefix+'/synthesis/preview','POST',JSON.parse(key)))}catch(e){setError(e.message)}finally{setBusy(false)}}
 async function start(){if(!preview)return;setBusy(true);setError('');try{const job=await request(prefix+'/synthesis','POST',{...JSON.parse(key),plan_hash:preview.plan_hash,idempotency_key:crypto.randomUUID(),name:'多条件受控合成'});setResult(null);onSubmitted(job)}catch(e){setError(e.message)}finally{setBusy(false)}}
 const rows=(result?.samples||[]).filter(s=>filter==='all'||(filter==='raw'?s.source!=='diffusion':s.source==='diffusion'))
 return <section className="synthesis-panel"><h3>合成训练数据</h3><p>复用FDS场 → 多条件渲染 → 掩膜增强 → 候选标签与质检。原始MP4不修改。</p>
  {error&&<p role="alert" className="editor-error">{error}</p>}
  <details open={!result}><summary>合成配置</summary>
   <fieldset><legend>来源工况（可跨场景选择）</legend>{ready.map(j=><label key={j.id}><input type="checkbox" checked={sources.includes(j.id)} onChange={()=>toggle(sources,setSources,j.id)}/>{j.payload.name} · {j.id.slice(0,6)}</label>)}{!ready.length&&<p>先完成至少一个FDS仿真。</p>}</fieldset>
   <fieldset><legend>视觉天气</legend>{Object.entries(names).map(([id,name])=><label key={id}><input type="checkbox" checked={weather.includes(id)} onChange={()=>toggle(weather,setWeather,id)}/>{name}</label>)}</fieldset>
   <fieldset><legend>机位（保存机位或场景默认机位）</legend>{['侧视','俯视','第一人称'].map(v=><label key={v}><input type="checkbox" checked={views.includes(v)} onChange={()=>toggle(views,setViews,v)}/>{v}</label>)}</fieldset>
   <label>每工况采样时刻数<input type="number" min="1" max="12" value={timeCount} onChange={e=>setTimeCount(Number(e.target.value))}/></label>
   <label>基础渲染<select value={profile} onChange={e=>setProfile(e.target.value)}><option value="visible">清晰可视化映射（未标定）</option><option value="baseline">原始黑体映射对照</option></select></label>
   {profile==='visible'&&<label>曝光补偿<input type="number" min="-3" max="3" step=".25" value={exposure} onChange={e=>setExposure(Number(e.target.value))}/></label>}
   <label>增强模式<select value={mode} onChange={e=>setMode(e.target.value)}><option value="both">背景＋火焰外观</option><option value="background">背景增强</option><option value="flame">火焰外观增强</option><option value="none">仅原图与深度</option></select></label>
   <label>每种模式派生数<input type="number" min="1" max="3" value={variants} onChange={e=>setVariants(Number(e.target.value))}/></label>
   <label><input type="checkbox" checked={controlnet} disabled={!caps.controlnet_depth} onChange={e=>setControlnet(e.target.checked)}/>ControlNet深度约束</label>
   {!caps.controlnet_depth&&<p>深度权重未安装，当前可使用掩膜inpainting；不会标作ControlNet。</p>}
   <p>雨雪是视觉条件；火焰外观增强重新产生候选标签，仍需人工审核。逐帧增强未验证时间一致性。</p>
   <button className="be-btn" disabled={busy||!sources.length} onClick={inspect}>预览组合数量</button>
   {preview&&<><p>复用{preview.counts.reused_fds_cases}个工况 · 原图{preview.counts.raw}张 · 请求增强{preview.counts.requested_augmented}张 · 不重新求解FDS</p><button className="be-btn primary" disabled={busy||(!caps.inpainting&&mode!=='none')} onClick={start}>{busy?'正在提交…':'开始合成'}</button></>}
  </details>
  {result&&<><h3>当前合成作业</h3><p>{statusNames[result.status]||result.status}{!['succeeded','failed','cancelled','interrupted'].includes(result.status)&&' · '+({'synthesis-render':'组合渲染','synthesis-enhance':'受控增强',queued:'等待执行'})[result.stage]}</p>{result.error&&<p role="alert" className="editor-error">{result.error}</p>}
   {result.counts&&<p>原图{result.counts.raw} · 增强{result.counts.augmented} · 拒绝{result.counts.rejected} · 自动筛选通过{result.counts.quality_pass}</p>}
   {result.comparisons?.map(c=><details key={c.sample_id}><summary>同物理帧基础渲染对照</summary><figure><img src={c.baseline} alt="原始渲染映射"/><figcaption>原始映射</figcaption><img src={c.current} alt="当前渲染映射"/><figcaption>当前映射，未改变FDS源场</figcaption></figure></details>)}
   <select aria-label="结果类型" value={filter} onChange={e=>setFilter(e.target.value)}><option value="all">全部</option><option value="raw">原始渲染</option><option value="aug">生成增强</option></select>
   {rows.map(s=><details key={s.id}><summary>{s.scene||''} · {s.source==='diffusion'?(s.mode==='flame'?'火焰增强':'背景增强'):'原图'} · {names[s.weather]} · {s.viewpoint} · {s.time_s.toFixed(2)}s</summary><img loading="lazy" src={s.image} alt="合成结果"/>{s.parent_image&&<><p>增强前</p><img loading="lazy" src={s.parent_image} alt="增强父图"/></>}<p>{s.quality?.auto_screen_pass?'候选通过，待人工审核':'需检查/筛除'}</p><a href={s.mask} target="_blank" rel="noreferrer">候选掩码</a> · <a href={s.depth} target="_blank" rel="noreferrer">深度图</a></details>)}
   {!!result.rejected?.length&&<details><summary>拒绝原因（{result.rejected.length}）</summary>{result.rejected.map(r=><p key={r.sample_id}>{r.reason}</p>)}</details>}
   {result.run_id&&<p><a href={`/?project=${project}&run=${result.run_id}#samples`}>标注与审核</a> · <a href={`/?project=${project}&run=${result.run_id}#versions`}>版本与导出</a></p>}
  </>}
 </section>
}
