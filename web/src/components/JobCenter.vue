<script setup lang="ts">
import {computed,ref,watch} from 'vue'
import {api,time,statusNames as sn} from '../api'
const props=defineProps<{jobs:any[],selected:any,busy:boolean,project:string}>()
const emit=defineEmits(['select','cancel','retry','samples'])
const query=ref(''),status=ref('all'),page=ref(1),videos=ref<any[]>([]),videoError=ref(''),showVideo=ref(false),videoIndex=ref(0)
const matching=computed(()=>props.jobs.filter(j=>(status.value==='all'||j.status===status.value)&&(!query.value||`${j.payload.name||''} ${j.id}`.toLowerCase().includes(query.value.toLowerCase()))))
const pages=computed(()=>Math.max(1,Math.ceil(matching.value.length/8)))
const visible=computed(()=>matching.value.slice((page.value-1)*8,page.value*8))
const active=computed(()=>props.jobs.find(j=>j.id===props.selected?.id)||props.jobs[0])
watch([query,status],()=>{page.value=1})
watch(pages,n=>{page.value=Math.min(page.value,n)})
watch(()=>active.value?.id,()=>{videos.value=[];showVideo.value=false;videoError.value='';videoIndex.value=0})
function stages(j:any){
 const ids=j.kind==='detector-pair'?['detector-pair']:j.kind==='fid'?['fid']:j.kind==='synthesis'?['synthesis-render',...(j.payload.enhance?['synthesis-enhance']:[])]:j.kind==='editor'?['original']:j.kind==='video'?['physics','video']:j.payload.route==='physics'?['physics','blender',...(j.payload.enhance?['enhance']:[])]:[j.payload.route==='preview'?'preview':j.kind]
 const names:Record<string,string>={'detector-pair':'检测A/B训练与真实集评价',fid:'审核快照分布评价','synthesis-render':'组合渲染（复用FDS）','synthesis-enhance':'受控inpainting',original:'火焰烘焙与渲染',physics:'FDS求解',video:'Blender渲染与视频',blender:'Blender渲染',enhance:'AI增强',preview:'预览生成',evaluation:'效果评价'}
 const started=ids.filter(id=>String(j.log||'').includes(`[${id}]`)); const current=ids.includes(j.stage)?j.stage:started.at(-1)
 return ids.map((id,i)=>({id,name:names[id]||id,state:j.status==='succeeded'?'完成':id===current?({failed:'失败',interrupted:'中断',cancelled:'已取消'}[j.status as string]||'执行中'):current&&i<ids.indexOf(current)?'完成':'等待'}))
}
function editorUrl(j:any){return `/scene-editor/index.html?project=${encodeURIComponent(props.project)}&scene=${encodeURIComponent(j.payload.scene_id)}&job=${j.id}`}
async function openVideo(){const id=active.value.id;showVideo.value=true;videoError.value='';try{const report=await api(`/simulation-videos/${id}`);if(active.value?.id===id)videos.value=report.videos}catch(e){if(active.value?.id===id)videoError.value=(e as Error).message}}
</script>

<template>
 <div v-if="!jobs.length" class="empty-state"><h2>还没有任务</h2><p>在3D场景编辑器中配置并开始作业。</p></div>
 <div v-else class="task-center">
  <section class="task-index" aria-label="任务列表">
   <div class="task-filters"><input v-model="query" aria-label="搜索任务" placeholder="搜索任务"><select v-model="status" aria-label="任务状态"><option value="all">全部状态</option><option value="running">运行中</option><option value="queued">排队中</option><option value="succeeded">已完成</option><option value="failed">失败</option><option value="interrupted">已中断</option><option value="cancelled">已取消</option></select></div>
   <div class="task-rows"><button v-for="j in visible" :key="j.id" class="task-row" :class="{active:active?.id===j.id}" :aria-pressed="active?.id===j.id" @click="emit('select',j)"><strong>{{j.payload.name||'任务'}}</strong><span class="badge" :class="j.status">{{sn[j.status]||j.status}}</span><time>{{time(j.created)}}</time></button><p v-if="!visible.length" class="empty-inline">没有符合条件的任务。</p></div>
   <div class="task-pagination"><span>{{matching.length}} 项 · {{page}} / {{pages}} 页</span><button class="secondary small" :disabled="page<=1" @click="page--">上一页</button><button class="secondary small" :disabled="page>=pages" @click="page++">下一页</button></div>
  </section>
  <section v-if="active" class="task-result" aria-label="任务详情">
   <header><h2>{{active.payload.name||'任务详情'}}</h2><span class="badge" :class="active.status">{{sn[active.status]||active.status}}</span></header>
   <ol class="task-stages" aria-label="执行阶段"><li v-for="step in stages(active)" :key="step.id" :class="{live:step.state==='执行中',done:step.state==='完成',bad:['失败','中断','已取消'].includes(step.state)}"><strong>{{step.name}}</strong><span>{{step.state}}</span></li></ol>
   <p v-if="active.result.error" class="message error">{{active.result.error}}</p>
   <div class="task-actions">
    <button v-if="['queued','running'].includes(active.status)" class="secondary" :disabled="busy" @click="emit('cancel',active)">取消任务</button>
    <button v-if="['failed','interrupted','cancelled'].includes(active.status)" class="primary" :disabled="busy" @click="emit('retry',active)">重试任务</button>
    <button v-if="active.status==='succeeded'&&['editor','video'].includes(active.kind)" class="primary" @click="openVideo">查看MP4</button>
    <button v-if="active.result.run_id" class="secondary" @click="emit('samples',active.result.run_id)">查看样本 / 审核</button>
    <a v-if="active.payload.scene_id" class="secondary" :href="editorUrl(active)">回到3D场景</a>
   </div>
   <div v-if="showVideo" class="task-video"><p v-if="videoError" role="alert">{{videoError}}</p><p v-else-if="!videos.length" role="status">正在读取视频…</p><template v-else><select v-model="videoIndex" aria-label="视频机位"><option v-for="(v,i) in videos" :key="i" :value="i">{{v.viewpoint||v.camera||'视频 '+(i+1)}}</option></select><video :key="videos[videoIndex]?.url" :src="videos[videoIndex]?.url" controls preload="metadata" aria-label="仿真视频"/></template></div>
   <details :key="active.id" class="task-log"><summary>详细日志</summary><pre>{{active.log||'等待工作进程领取。'}}</pre><small>任务 {{active.id}}<template v-if="active.result.elapsed_s"> · 耗时 {{active.result.elapsed_s}} 秒</template></small></details>
  </section>
 </div>
</template>

<style scoped>
.task-center{display:grid;grid-template-columns:minmax(280px,.85fr) minmax(0,1.6fr);gap:24px;align-items:start}
.task-index,.task-result{min-width:0}.task-filters{display:flex;gap:8px;margin-bottom:12px}.task-filters input{width:100%;min-width:0}.task-filters select{max-width:120px}
.task-rows{border-top:1px solid var(--line)}.task-row{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:8px 12px;align-items:center;width:100%;text-align:left;padding:14px 12px;background:transparent;color:var(--ink);border-bottom:1px solid var(--line);transition:background var(--t-fast) var(--ease)}.task-row:hover{background:var(--surface-2)}.task-row.active{background:var(--soft);box-shadow:inset 3px 0 0 var(--orange)}.task-row strong{font-size:13.5px;font-weight:500;overflow-wrap:anywhere}.task-row time{grid-column:1/-1;font-size:12px}
.task-pagination{display:flex;align-items:center;justify-content:flex-end;gap:8px;margin-top:12px}.task-pagination>span{margin-right:auto;font-size:12.5px;color:var(--muted)}
.task-result{background:var(--surface);border-radius:12px;padding:24px;box-shadow:var(--card-shadow)}.task-result header{display:flex;gap:16px;align-items:start;justify-content:space-between}.task-result h2{overflow-wrap:anywhere}
.task-stages{list-style:none;margin:24px 0;padding:0;display:flex;flex-wrap:wrap;gap:12px 24px}.task-stages li{display:flex;flex-direction:column;gap:6px;font-size:12px;padding:6px 10px;border-radius:8px;transition:background var(--t-fast) var(--ease)}.task-stages li.live{background:var(--soft)}.task-stages li.live strong{color:var(--orange)}.task-stages li.live span{color:var(--orange);font-weight:600;animation:stagePulse 2s var(--ease) infinite}.task-stages li.done span{color:var(--green)}.task-stages li.bad span{color:#b03311}.task-stages strong{font-weight:600;font-size:13px}.task-stages span{color:var(--muted);font-size:12px}.task-actions{display:flex;flex-wrap:wrap;gap:8px}.task-log{border-top:1px solid var(--line);margin-top:24px;padding-top:16px}.task-log summary{cursor:pointer;font-size:13px;color:var(--muted)}.task-log pre{max-height:320px;overflow:auto;white-space:pre-wrap;overflow-wrap:anywhere;background:var(--sidebar);color:#ecdfc9;padding:16px;font-size:12px;line-height:1.8}.task-log small{overflow-wrap:anywhere;color:var(--muted)}
.task-video{margin-top:20px}.task-video select{max-width:100%;margin-bottom:10px}.task-video video{display:block;width:100%;max-height:420px;background:var(--sidebar)}
@media(max-width:1000px){.task-center{grid-template-columns:1fr}.task-result{padding:18px}}
@keyframes stagePulse{0%,100%{opacity:1}50%{opacity:.45}}
</style>
