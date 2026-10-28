import React,{useEffect,useRef,useState} from 'react'
import {originalApi} from './original-api.js'

export function PhysicalPlayback({job,project}){
 const [report,setReport]=useState(null),[videos,setVideos]=useState([]),[error,setError]=useState(''),[index,setIndex]=useState(0),[view,setView]=useState(0),[opened,setOpened]=useState(false)
 const player=useRef(null)
 useEffect(()=>{setReport(null);setVideos([]);setIndex(0);setView(0);setOpened(false);setError('');if(!job)return;let alive=true
  const load=async()=>{try{const r=await originalApi(`/api/v1/jobs/${job}/trajectory`);if(alive){setReport(r);setError('')}const response=await originalApi(`/api/v1/jobs/${job}`);if(response.state==='succeeded'&&['editor','video'].includes(response.kind)){const v=await fetch(`/api/simulation-videos/${job}`,{credentials:'same-origin'});if(!v.ok)throw new Error('视频未就绪');const data=await v.json();if(alive)setVideos(data.videos)}}catch(e){if(alive)setError(e.message)}}
  load();const timer=setInterval(load,5000);return()=>{alive=false;clearInterval(timer)}
 },[job])
 if(!job)return null
 const frames=report?.frames||[],row=frames[index],video=videos[view],prediction=row?.fds_next
 const fmt=v=>v===undefined||v===null?'—':Number(v).toFixed(2),xyz=v=>v?v.map(fmt).join(', ')+' m':'未检测到燃烧区域'
 function seek(i){
  if(player.current&&video){const encoded=video.timeline.filter(f=>f.encoded);const selected=encoded.reduce((a,b)=>Math.abs(b.time_s-frames[i].time_s)<Math.abs(a.time_s-frames[i].time_s)?b:a);player.current.currentTime=selected.playback_start_s+.001;setIndex(frames.findIndex(f=>Math.abs(f.time_s-selected.time_s)<.0001))}else setIndex(i)
 }
 function sync(){if(!frames.length||!video)return;const t=player.current?.currentTime||0;const encoded=video.timeline.filter(f=>f.encoded);let i=0;while(i+1<encoded.length&&encoded[i+1].playback_start_s<=t+.00001)i++;const n=frames.findIndex(f=>Math.abs(f.time_s-encoded[i].time_s)<.0001);if(n>=0)setIndex(n)}
 const bounds=report?.bounds_m
 const point=p=>bounds?`${20+(p[0]-bounds[0][0])/Math.max(.01,bounds[0][1]-bounds[0][0])*240},${160-(p[1]-bounds[1][0])/Math.max(.01,bounds[1][1]-bounds[1][0])*140}`:''
 const history=frames.slice(0,index+1).filter(f=>f.centroid_m).map(f=>point(f.centroid_m)).join(' ')
 return <section className="physical-playback" aria-label="作业视频与物理时序"><h3>视频与时序</h3>
  {error&&<p role="alert">{error}</p>}
  {!!videos.length&&<><button className="be-btn primary" onClick={()=>setOpened(v=>!v)}>{opened?'收起MP4':'观看MP4'}</button>{opened&&<><select aria-label="播放机位" value={view} onChange={e=>{setView(Number(e.target.value));setIndex(0)}}>{videos.map((v,i)=><option key={i} value={i}>{v.weather?v.weather+' · ':''}{v.viewpoint||'机位'+(i+1)}</option>)}</select><video key={video?.url} ref={player} src={video?.url} controls preload="metadata" onTimeUpdate={sync} onSeeked={sync} aria-label="作业MP4"/><p>物理时段 {fmt(video?.start_s)}–{fmt(video?.end_s)} s · {video?.source_frames}个源帧</p></>}</>}
  {report&&!report.available&&<p>{report.reason}</p>}
  {row&&<><label className="physical-time">求解时刻 {fmt(row.time_s)} s<input aria-label="物理时间轴" type="range" min="0" max={frames.length-1} value={index} onChange={e=>seek(Number(e.target.value))}/></label>
   <dl><dt>燃烧重心 XYZ</dt><dd>{xyz(row.centroid_m)}</dd><dt>最高温度</dt><dd>{fmt(row.max_temperature_c)} °C</dd><dt>反应区域体积</dt><dd>{fmt(row.reaction_volume_m3)} m³</dd><dt>峰值热释放率密度</dt><dd>{fmt(row.max_hrrpuv_kw_m3)} kW/m³</dd></dl>
   <svg viewBox="0 0 280 180" role="img" aria-label="燃烧重心俯视轨迹，实线为历史，虚线为下一FDS时刻"><rect x="20" y="20" width="240" height="140" fill="none" stroke="#858585"/><polyline points={history} fill="none" stroke="#e5a05b" strokeWidth="2"/>{row.centroid_m&&<circle cx={point(row.centroid_m).split(',')[0]} cy={point(row.centroid_m).split(',')[1]} r="4" fill="#ffd6a0"/>}{prediction?.available&&row.centroid_m&&prediction.centroid_m&&<polyline points={point(row.centroid_m)+' '+point(prediction.centroid_m)} fill="none" stroke="#9ecff4" strokeWidth="2" strokeDasharray="5 3"/>}<text x="22" y="175" fill="#ddd" fontSize="10">X / Y · 米 · 实线历史 / 虚线FDS下一时刻</text></svg>
   <p>{prediction?.available?`FDS下一时刻 ${fmt(prediction.target_time_s)} s：${xyz(prediction.centroid_m)}`:'已到达本次FDS推演终点；可延长求解时长后重新运行。'}</p><p>按已设定场景与气象条件完成的FDS下一求解帧，非观测驱动预测。火源采用规定HRR，不代表已预测材料蔓延或雨淋熄灭。</p>
   <a href={`/api/projects/${encodeURIComponent(project)}/scene-editor/compat/jobs/${job}/trajectory?download=true`}>导出时序训练数据</a><details><summary>参数说明</summary><p>位置是HRRPUV加权燃烧重心，非最外层火焰前沿；Z向上。反应区阈值1 kW/m³。参数来自FDS，不从增强图片反推。FDS完成导出后可读，当前不是求解中实时遥测。</p></details>
  </>}
 </section>
}
