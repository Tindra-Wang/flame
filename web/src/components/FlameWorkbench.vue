<script setup lang="ts">
import {computed,onMounted,onUnmounted,ref,watch} from 'vue'
import {ArrowRight,RefreshCw} from 'lucide-vue-next'
import {api,statusNames as sn,time} from '../api'
const props=defineProps<{project:string;config:any;scenes:any[];submit:(payload:any)=>Promise<any>;simulate:(payload:any)=>Promise<any>}>()
const emit=defineEmits<{navigate:[page:string,run?:string]}>()
const sceneId=ref(new URLSearchParams(location.search).get('scene')||'room'),sourceId=ref(''),jobs=ref<any[]>([]),error=ref('')
const scene=computed(()=>props.scenes.find(s=>s.id===sceneId.value))
const videos=computed(()=>jobs.value.filter(j=>j.kind==='video'&&j.status==='succeeded'&&j.payload.scene_id===sceneId.value&&j.payload.scene_revision===scene.value?.config.editor_scene?.revision))
const source=computed(()=>videos.value.find(j=>j.id===sourceId.value))
const batches=computed(()=>jobs.value.filter(j=>['generate','editor','synthesis'].includes(j.kind)&&(j.payload.scene_id===sceneId.value||j.payload.scene_ids?.includes(sceneId.value))))
const editorLink=computed(()=>`/scene-editor/index.html?project=${encodeURIComponent(props.project)}&scene=${encodeURIComponent(sceneId.value)}`)
watch(videos,rows=>{if(!rows.some(j=>j.id===sourceId.value))sourceId.value=rows[0]?.id||''})
async function refresh(){try{jobs.value=await api(`/projects/${props.project}/jobs`)}catch(e){error.value=(e as Error).message}}

let timer:ReturnType<typeof setInterval>|undefined
onMounted(()=>{refresh();timer=setInterval(refresh,4000)});onUnmounted(()=>clearInterval(timer))
</script>
<template>
 <div class="dataset-workflow">
  <nav class="workflow-path" aria-label="数据制作链路"><a :href="editorLink">3D布景与仿真MP4</a><ArrowRight :size="15"/><strong>生成数据</strong><ArrowRight :size="15"/><button @click="emit('navigate','samples')">标注与质检</button><ArrowRight :size="15"/><button @click="emit('navigate','versions')">版本与导出</button></nav>
  <section class="scene-overview"><div><h2>从已完成的仿真生成数据</h2><label>选择场景<select v-model="sceneId"><option v-for="s in scenes" :key="s.id" :value="s.id">{{s.name}}{{s.config.editor_scene?' · 第'+s.config.editor_scene.revision+'版':' · 尚未保存3D场景'}}</option></select></label><p class="context-note">布景、FDS求解、作业日志和仿真MP4统一在3D编辑页操作。这里复用求解结果，管理合成批次和后续处理。</p></div><a class="primary" :href="editorLink">打开3D编辑与仿真 <ArrowRight :size="16"/></a></section>
  <div class="workflow-columns">
   <section class="form-panel"><h2>合成训练数据</h2><p v-if="!videos.length" class="message">先在3D编辑页完成当前场景的FDS仿真。</p><label>来源仿真<select v-model="sourceId" :disabled="!videos.length"><option v-if="!videos.length" value="">等待仿真完成</option><option v-for="j in videos" :key="j.id" :value="j.id">{{time(j.created)}} · {{j.id.slice(0,8)}}</option></select></label><p>在编辑页选择场景工况、视觉天气、机位、时刻及背景/火焰增强，先预览组合数量，再提交。共用原始仿真结果，不重新求解FDS。</p><a v-if="source" class="primary" :href="editorLink+'&tab=synthesis&job='+sourceId">进入数据合成 <ArrowRight :size="16"/></a><a v-else class="secondary" :href="editorLink">打开3D编辑器</a></section>
   <section class="batch-list"><div class="section-heading"><h2>当前场景的数据批次</h2><button class="icon-button" aria-label="刷新作业" @click="refresh"><RefreshCw :size="16"/></button></div><p v-if="!batches.length" class="context-note">尚未生成数据。仿真完成后提交第一批样本。</p><article v-for="job in batches" :key="job.id" class="batch-row"><div><strong>{{job.payload.name}}</strong><span class="badge" :class="job.status">{{sn[job.status]||job.status}}</span></div><p v-if="job.kind==='synthesis'">复用 {{job.payload.plan?.sources?.length||1}} 个FDS工况 → 组合渲染{{job.payload.enhance?' → 掩膜扩散增强':''}} → 候选标注与质检</p><p v-else>仿真 {{job.payload.source_simulation_id?.slice(0,8)||'独立求解'}} → {{job.payload.enhance?'Blender + SD':'Blender'}} → 候选标注与质检</p><p v-if="job.result.error" class="message error">{{job.result.error}}</p><div class="button-row"><button v-if="job.result.run_id" class="secondary small" @click="emit('navigate','samples',job.result.run_id)">查看样本与质检 <ArrowRight :size="14"/></button><button v-if="job.result.run_id" class="text-button" @click="emit('navigate','versions',job.result.run_id)">版本与导出</button><button class="text-button" @click="emit('navigate','jobs')">阶段日志</button></div></article></section>
  </div>
 </div>
</template>
<style scoped>
.workflow-path{display:flex;gap:12px;align-items:center;flex-wrap:wrap;font-size:13px;color:var(--muted);margin-bottom:28px}.workflow-path a,.workflow-path button{text-decoration:underline;text-underline-offset:4px}.workflow-path strong{color:var(--ink)}.scene-overview{display:flex;gap:24px;align-items:center;justify-content:space-between;border-bottom:1px solid var(--line);padding-bottom:24px;margin-bottom:28px}.scene-overview>div{max-width:720px}.scene-overview h2,.form-panel h2{margin:0 0 20px}.scene-overview label,.form-panel>label{display:block;font-size:14px}.scene-overview select,.form-panel select,.form-panel input[type=number]{display:block;width:100%;margin:8px 0 18px}.scene-overview .primary{white-space:nowrap}.workflow-columns{display:grid;grid-template-columns:minmax(280px,.8fr) minmax(0,1.2fr);gap:32px}.form-panel>.primary{margin-top:14px;width:100%}.batch-row{padding:20px 0;border-bottom:1px solid var(--line);font-size:14px}.batch-row>div:first-child{display:flex;justify-content:space-between;gap:10px}.batch-row p{font-size:13px;color:var(--muted);line-height:1.7}.batch-list{min-width:0}@media(max-width:900px){.workflow-columns{grid-template-columns:1fr}.scene-overview{align-items:stretch;flex-direction:column}.scene-overview .primary{white-space:normal}}
</style>


