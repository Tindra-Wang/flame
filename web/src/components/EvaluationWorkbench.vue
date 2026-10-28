<script setup lang="ts">
import {computed,onMounted,ref} from 'vue'
import {ArrowRight} from 'lucide-vue-next'
import {api,time,statusNames} from '../api'
const props=defineProps<{project:string;runs:any[];versions:any[];experiments:any[];jobs:any[];busy:boolean;execute:(path:string,data:any)=>Promise<any>}>()
const emit=defineEmits<{import:[];review:[];job:[id:string]}>()
const tab=ref('distribution'),real=ref(''),synthetic=ref(''),selection=ref('enhanced'),dims=ref(64),metric=ref('fid')
const realVersion=ref(''),syntheticVersion=ref(''),epochs=ref(5),weights=ref('yolo11n.pt'),caps=ref<any>({weights:[]}),physical=ref<any>({}),fileError=ref(''),timing=ref<any>(null)
const realRuns=computed(()=>props.runs.filter(r=>r.route==='real'))
const syntheticRuns=computed(()=>props.runs.filter(r=>r.route==='physics'))
const published=computed(()=>props.versions.filter(v=>v.status==='published'))
const realVersions=computed(()=>published.value.filter(v=>props.runs.find(r=>r.id===v.run_id)?.route==='real'))
const syntheticVersions=computed(()=>published.value.filter(v=>props.runs.find(r=>r.id===v.run_id)?.route==='physics'))
const results=computed(()=>props.experiments.filter(e=>tab.value==='distribution'?e.kind==='fid':tab.value==='detector'?e.kind==='detector-pair':e.kind==='physical'))
const relevant=computed(()=>props.jobs.filter(j=>j.kind===(tab.value==='detector'?'detector-pair':'fid')).slice(0,3))
const metrics=[{key:'mAP50',name:'mAP50',hint:'框住火且重叠过半才算对——最常用的检出精度'},{key:'mAP50_95',name:'mAP50–95',hint:'定位更严：框要贴得更准才算对'},{key:'precision',name:'Precision 查准',hint:'模型喊"有火"时真是火的比例（误报越少越高）'},{key:'recall',name:'Recall 查全',hint:'真实的火被发现的比例（漏检越少越高）'}]
const tabs=[{id:'distribution',q:'① 长得像吗 · 分布对比',s:'合成图像与真实火焰照片的分布距离（FID，越低越像）'},{id:'detector',q:'② 变强了吗 · 检测对照',s:'加入合成数据前后，火焰检测模型的成绩差（A/B 同预算训练）'},{id:'physical',q:'③ 准不准 · 物理误差',s:'仿真结果与独立物理参照的偏差'}]
onMounted(async()=>{try{caps.value=await api(`/projects/${props.project}/evaluations/capabilities`)}catch(e){fileError.value=(e as Error).message}try{timing.value=await api(`/projects/${props.project}/timing`)}catch{timing.value=null}})
async function submit(){if(tab.value==='distribution')await props.execute(`/projects/${props.project}/evaluations/distribution`,{real_run:real.value,synthetic_run:synthetic.value,selection:selection.value,dims:dims.value,metric:metric.value});else if(tab.value==='detector')await props.execute(`/projects/${props.project}/evaluations/detector-comparisons`,{real_version:realVersion.value,synthetic_version:syntheticVersion.value,weights:weights.value,epochs:epochs.value,batch:4,imgsz:384,seed:42});else await props.execute(`/projects/${props.project}/experiments`,{kind:'physical',...physical.value})}
async function read(event:Event,key:string){try{const f=(event.target as HTMLInputElement).files?.[0];if(f)physical.value[key]=JSON.parse(await f.text());fileError.value=''}catch{fileError.value='JSON文件格式不正确'}}
async function singleEvaluation(){await props.execute(`/projects/${props.project}/experiments`,{kind:'detection',truth:physical.value.truth,predictions:physical.value.predictions})}
const percent=(x:number)=>`${(x*100).toFixed(2)}%`
const delta=(x:number)=>`${x>0?'+':''}${x.toFixed(2)} 个百分点`
const latestDetector=computed(()=>[...props.experiments].reverse().find(e=>e.kind==='detector-pair'))
const detectorVerdict=computed(()=>{const e=latestDetector.value;if(!e||!e.result?.delta_pp)return null;const d=e.result.delta_pp.mAP50;return{up:d>=0,pp:Math.abs(d).toFixed(2),syn:e.result.groups?.augmented&&e.result.groups?.baseline,sentence:`加入合成数据后，mAP50 ${d>=0?'提升':'下降'} ${Math.abs(d).toFixed(2)} 个百分点`}})
const latestFid=computed(()=>[...props.experiments].reverse().find(e=>e.kind==='fid'&&e.result?.value!=null))
const selectionNames:Record<string,string>={raw:'基础渲染图',enhanced:'扩散增强图',all:'原图＋增强图'}
const distBlocked=computed(()=>!realRuns.value.length?'还没有真实参照数据——先在样本页导入并人工审核':!syntheticRuns.value.length?'还没有审核通过的合成批次——先在3D编辑页生成并送审':'')
const detBlocked=computed(()=>!realVersions.value.length?'真实数据还没有发布版本——在版本页冻结一个真实数据快照':!syntheticVersions.value.length?'合成数据还没有发布版本——审核合成批次后冻结快照':!caps.value.weights.length?'检测初始权重未安装':'')
</script>
<template>
 <section class="eval-intro" aria-label="本页说明">
  <h2>合成的数据到底有没有用？</h2>
  <p>这页用三个实验回答同一件事的三面：合成图像<b>长得像不像</b>真实照片、加进训练后模型<b>变强了多少</b>、仿真结果<b>准不准</b>。全部证据只来自人工审核通过的数据；没有结果时会明确告诉你缺什么、下一步做什么。</p>
  <div class="eval-intro-chips"><span class="stat-chip">真实批次 <b>{{realRuns.length}}</b></span><span class="stat-chip">合成批次（已审核）<b>{{syntheticRuns.reduce((a,r)=>a+r.approved,0)}} 张</b></span><span class="stat-chip">已发布版本 <b>{{published.length}}</b></span></div>
  <div class="button-row"><button class="text-button" @click="emit('review')">去页内审核</button><button class="text-button" @click="emit('import')">导入真实数据</button><a href="/docs" target="_blank" rel="noreferrer" class="text-button">接口文档</a></div>
 </section>
 <section v-if="timing&&(timing.scratch||timing.candidate)" class="timing-card" aria-label="标注成本对照">
  <div class="section-heading"><h2>标注省事了吗 · 人工工时对照</h2><span class="quiet-label">样本页框选审核时自动计时</span></div>
  <div class="timing-rows">
   <div v-if="timing.scratch" class="timing-row"><span class="timing-mode">从零手画</span><strong>{{timing.scratch.mean_active_s_per_sample}} 秒/张</strong><small>{{timing.scratch.count}} 张 · 合计 {{Math.round(timing.scratch.total_active_s/60)}} 分钟</small></div>
   <div v-if="timing.candidate" class="timing-row"><span class="timing-mode">修订自动候选框</span><strong>{{timing.candidate.mean_active_s_per_sample}} 秒/张</strong><small>{{timing.candidate.count}} 张 · 合计 {{Math.round(timing.candidate.total_active_s/60)}} 分钟</small></div>
  </div>
  <p class="context-note">两组需同样细心地核对；秒数来自真实操作记录（超15秒不动自动暂停），改不了。</p>
 </section>
 <div class="tabs" role="tablist" aria-label="评价类型"><button v-for="t in tabs" :key="t.id" role="tab" :aria-selected="tab===t.id" :class="{active:tab===t.id}" @click="tab=t.id"><span class="tab-q">{{t.q}}</span><span class="tab-s">{{t.s}}</span></button></div>
 <div class="evaluation-layout">
  <section class="form-panel">
   <template v-if="tab==='distribution'">
    <h2>实验①：合成图长得像真实照片吗？</h2>
    <p class="plain-note">各选一个<b>人工审核通过</b>的真实批次和合成批次，计算两组图像的分布距离 FID——<b>数字越小，合成图越像真实照片</b>。</p>
    <form class="stacked-form" @submit.prevent="submit">
     <label>真实照片批次（参照）<select v-model="real" required><option disabled value="">{{realRuns.length?'请选择真实批次':'还没有真实批次'}}</option><option v-for="r in realRuns" :key="r.id" :value="r.id">{{r.name}} · 已审核 {{r.approved}} 张</option></select></label>
     <div v-if="!realRuns.length" class="blocked-hint">缺真实数据。<button type="button" class="text-button" @click="emit('import')">第一步：去样本页导入真实数据 <ArrowRight :size="14"/></button>然后人工审核通过若干张即可。</div>
     <label>合成图像批次<select v-model="synthetic" required><option disabled value="">选择合成批次</option><option v-for="r in syntheticRuns" :key="r.id" :value="r.id">{{r.name}} · 已审核 {{r.approved}} 张</option></select></label>
     <details class="adv"><summary>高级参数（一般不用改）</summary>
      <label>参与对比的合成图<select v-model="selection"><option value="raw">仅基础渲染图</option><option value="enhanced">仅扩散增强图</option><option value="all">原图＋增强图</option></select></label>
      <label>计算方法<select v-model="metric"><option value="fid">FID（标准，需要足够样本）</option><option value="color-js">颜色分布快查（小样本可先用）</option></select></label>
      <label v-if="metric==='fid'">特征维度<select v-model.number="dims"><option :value="64">64 · 小样本流程验证</option><option :value="2048">2048 · 标准特征</option></select></label>
     </details>
     <p class="context-note">只取人工审核通过的图片并冻结清单；小样本的 FID 只能验证流程，不能证明"像"。</p>
     <p v-if="fileError" role="alert" class="message error">{{fileError}}</p>
     <button class="primary" :disabled="busy||!realRuns.length||!syntheticRuns.length">{{busy?'正在提交…':'开始对比'}}</button>
     <p v-if="distBlocked" class="blocked-hint">现在还不能跑：{{distBlocked}}</p>
    </form>
   </template>
   <template v-else-if="tab==='detector'">
    <h2>实验②：加入合成数据，检测模型变强了多少？</h2>
    <p class="plain-note">同样的真实数据训练两次：<b>A组只用真实图，B组额外加合成图</b>；同一份真实测试集上比成绩。差值为正＝合成数据有效。</p>
    <form class="stacked-form" @submit.prevent="submit">
     <label>真实数据版本<select v-model="realVersion" required><option disabled value="">{{realVersions.length?'选择真实数据版本':'还没有真实数据版本'}}</option><option v-for="v in realVersions" :key="v.id" :value="v.id">{{v.name}} · {{v.result.count}}张</option></select></label>
     <div v-if="!realVersions.length" class="blocked-hint">缺真实版本：先在样本页审核真实批次，再到<b>版本与导出</b>页冻结快照（含独立 训练/验证/测试 划分）。</div>
     <label>合成数据版本<select v-model="syntheticVersion" required><option disabled value="">选择合成数据版本</option><option v-for="v in syntheticVersions" :key="v.id" :value="v.id">{{v.name}} · {{v.result.count}}张</option></select></label>
     <details class="adv"><summary>高级参数（一般不用改）</summary>
      <label>初始权重<select v-model="weights" required><option v-for="w in caps.weights" :key="w" :value="w">{{w}}</option></select></label>
      <label>训练轮数<input v-model.number="epochs" type="number" min="1" max="50" required></label>
      <p class="context-note">两组固定同预算（相同轮数/批量/随机种子），输入384px、batch 4；显存不足可经API降批量。</p>
     </details>
     <p v-if="fileError" role="alert" class="message error">{{fileError}}</p>
     <button class="primary" :disabled="busy||!!detBlocked">{{busy?'正在提交…':'开始 A/B 对照训练'}}</button>
     <p v-if="detBlocked" class="blocked-hint">现在还不能跑：{{detBlocked}}</p>
    </form>
    <details v-if="tab==='detector'" class="adv"><summary>已有预测文件？单次检测评分（不测提升）</summary>
     <form class="stacked-form" @submit.prevent="singleEvaluation"><label>人工真值 JSON<input type="file" accept=".json" required @change="read($event,'truth')"></label><label>预测结果 JSON<input type="file" accept=".json" required @change="read($event,'predictions')"></label><button class="secondary" :disabled="busy||!physical.truth||!physical.predictions">计算单次指标</button></form>
    </details>
   </template>
   <template v-else>
    <h2>实验③：仿真与独立参照差多少？</h2>
    <p class="plain-note">上传两份 JSON（独立参照 + 仿真预测，含 quantity/unit/time_s/values），逐项给出误差。<b>不能用同一份仿真结果充当参照。</b></p>
    <form class="stacked-form" @submit.prevent="submit">
     <label>独立参照 JSON<input type="file" accept=".json" required @change="read($event,'reference')"></label>
     <label>仿真预测 JSON<input type="file" accept=".json" required @change="read($event,'prediction')"></label>
     <p v-if="fileError" role="alert" class="message error">{{fileError}}</p>
     <button class="primary" :disabled="busy||!physical.reference||!physical.prediction">计算物理误差</button>
    </form>
   </template>
  </section>
  <section class="result-side">
   <h2>结果与结论</h2>
   <template v-if="tab==='detector'">
    <p v-if="!results.length" class="empty-inline">还没有 A/B 结果。需要：① 导入并审核真实数据 → ② 冻结真实版本 → ③ 审核合成批次并冻结版本 → ④ 左侧提交。完成后这里会用一句话告诉你合成数据是否有效。</p>
    <button v-for="j in relevant" :key="j.id" class="evaluation-job" @click="emit('job',j.id)">{{j.payload.name}} · {{statusNames[j.status]||j.status}}<span v-if="j.result.error">{{j.result.error}}</span></button>
    <article v-for="e in results" :key="e.id" class="experiment-record">
     <div v-if="detectorVerdict" class="verdict" :class="detectorVerdict.up?'up':'down'"><span class="verdict-word">{{detectorVerdict.up?'有效':'下降'}}</span><span class="verdict-sentence">{{detectorVerdict.sentence}}</span></div>
     <p class="quiet-label">{{time(e.created)}} · A组=仅真实 {{e.result.groups.baseline?(e.result.counts?.train??'')+'张':''}} ／ B组=真实＋合成</p>
     <div v-for="m in metrics" :key="m.key" class="comparison-metric">
      <div class="metric-title"><strong>{{m.name}}</strong><span class="delta-chip" :class="e.result.delta_pp[m.key]>0?'up':e.result.delta_pp[m.key]<0?'down':''">{{delta(e.result.delta_pp[m.key])}}</span></div>
      <div class="bar-row"><span class="bar-tag">A 仅真实</span><meter min="0" max="1" :value="e.result.groups.baseline[m.key]" :aria-label="'仅真实 '+m.name"/><b>{{percent(e.result.groups.baseline[m.key])}}</b></div>
      <div class="bar-row augmented"><span class="bar-tag">B ＋合成</span><meter min="0" max="1" :value="e.result.groups.augmented[m.key]" :aria-label="'真实加合成 '+m.name"/><b>{{percent(e.result.groups.augmented[m.key])}}</b></div>
      <p class="metric-hint">{{m.hint}}</p>
     </div>
     <p class="context-note">同一真实测试集；两组各 {{e.result.groups.baseline.train_iterations}} 次训练更新。单次运行不构成稳定结论——小增益需多种子重复验证；负值代表加入后变差。</p>
    </article>
    <details v-if="experiments.some(e=>e.kind==='detection')"><summary>历史单次检测评分（非A/B提升）</summary><article v-for="e in experiments.filter(e=>e.kind==='detection')" :key="e.id" class="experiment-record"><p>{{time(e.created)}} · 单次预测，非A/B提升</p><p>AP50：{{e.result.AP50==null?'—':percent(e.result.AP50)}}；AP50–95：{{e.result.AP50_95==null?'—':percent(e.result.AP50_95)}}</p></article></details>
   </template>
   <template v-else-if="tab==='distribution'">
    <p v-if="!results.length" class="empty-inline">还没有分布对比结果。需要：① 样本页导入并审核真实照片 → ② 审核合成批次 → ③ 左侧选择两个批次并提交。完成后这里会给出 FID 数值与判读。</p>
    <button v-for="j in relevant" :key="j.id" class="evaluation-job" @click="emit('job',j.id)">{{j.payload.name}} · {{statusNames[j.status]||j.status}}<span v-if="j.result.error">{{j.result.error}}</span></button>
    <article v-for="e in results" :key="e.id" class="experiment-record">
     <div class="verdict neutral"><span class="verdict-word">FID {{e.result.value?.toFixed(2)??'—'}}</span><span class="verdict-sentence">{{e.result.metric==='fid'?'越低越像；小样本只能验证流程':'颜色分布快查，非FID'}}</span></div>
     <p>真实 {{e.result.real_count}} 张 ↔ 合成 {{e.result.synthetic_count}} 张（{{selectionNames[e.result.evaluation_snapshot?.selection]||'历史记录'}}）</p>
     <p class="context-note">FID 与颜色JS不可混比；该值不等于标签准确率，也不等于检测收益。</p>
    </article>
   </template>
   <template v-else>
    <p v-if="!results.length" class="empty-inline">还没有物理误差结果。准备好独立参照 JSON 后在左侧提交。</p>
    <article v-for="e in results" :key="e.id" class="experiment-record"><p class="quiet-label">{{time(e.created)}}</p><p v-for="(v,k) in e.result" :key="k">{{k}}：{{v}}</p></article>
   </template>
  </section>
 </div>
</template>
<style scoped>
.eval-intro{background:var(--surface);border-radius:12px;padding:24px 26px;margin-bottom:22px;box-shadow:var(--card-shadow)}
.eval-intro h2{font-size:21px;margin-bottom:8px}
.eval-intro p{max-width:88ch;font-size:13.5px}
.eval-intro b{color:var(--ink)}
.eval-intro-chips{display:flex;gap:10px;flex-wrap:wrap;margin:14px 0 4px}
.stat-chip{display:inline-flex;align-items:center;gap:7px;background:var(--soft);border-radius:99px;padding:7px 14px;font-size:12.5px;color:var(--muted)}
.stat-chip b{font-size:14px;color:var(--ink);font-weight:700;font-variant-numeric:tabular-nums}
.tabs{display:flex;gap:12px;border-bottom:1px solid var(--line);margin:0 0 24px}
.tabs>button{display:flex;flex-direction:column;gap:3px;align-items:flex-start;background:transparent;color:var(--muted);padding:12px 18px 12px 2px;border-bottom:2px solid transparent}
.tab-q{font-size:14px;font-weight:600}
.tab-s{font-size:12px}
.tabs>button.active{color:var(--orange);border-bottom-color:var(--orange)}
.plain-note{font-size:13.5px;line-height:1.8;margin-bottom:18px}
.plain-note b{color:var(--ink)}
.adv{border-top:1px dashed var(--line);padding-top:12px;margin:6px 0}
.adv summary{cursor:pointer;font-size:12.5px;color:var(--muted);padding:4px 0 10px}
.adv .stacked-form{margin-top:10px}
.blocked-hint{background:var(--soft);border-radius:8px;padding:12px 14px;font-size:12.5px;color:#8a6a45;line-height:1.7;display:flex;flex-wrap:wrap;gap:6px;align-items:center}
.result-side h2{margin-bottom:14px}
.verdict{display:flex;align-items:center;gap:14px;border-radius:10px;padding:14px 16px;margin:12px 0}
.verdict.up{background:#e2f0e4;color:#2f7d4d}
.verdict.down{background:#fbe3dc;color:#b03311}
.verdict.neutral{background:var(--soft);color:#7a4a1e}
.verdict-word{font-size:22px;font-weight:750;flex-shrink:0}
.verdict-sentence{font-size:14px;font-weight:600;line-height:1.5}
.metric-title{display:flex;justify-content:space-between;align-items:center;gap:16px;font-size:13.5px;margin-bottom:10px}
.delta-chip{font-size:12.5px;font-weight:700;padding:3px 10px;border-radius:99px;background:var(--surface-2);color:var(--muted)}
.delta-chip.up{background:#e2f0e4;color:#2f7d4d}
.delta-chip.down{background:#fbe3dc;color:#b03311}
.metric-hint{font-size:12px;color:var(--muted);margin:2px 0 4px}
.bar-tag{width:70px;flex-shrink:0;font-size:12px;color:var(--muted)}
.timing-card{background:var(--soft);border-radius:12px;padding:20px 24px;margin-bottom:22px}
.timing-rows{display:flex;gap:32px;flex-wrap:wrap;margin:6px 0 4px}
.timing-row{display:flex;flex-direction:column;gap:6px}
.timing-row strong{font-size:26px;font-weight:650;font-variant-numeric:tabular-nums}
.timing-mode{font-size:12.5px;color:var(--muted);font-weight:600}
.timing-row small{font-size:12.5px;color:var(--muted)}
.evaluation-empty{color:var(--muted);line-height:1.8;padding:24px 0}
.evaluation-job{display:block;width:100%;text-align:left;padding:14px 0;border-bottom:1px solid var(--line);font-size:13.5px;background:transparent}
.evaluation-job span{display:block;color:var(--orange);margin-top:8px;overflow-wrap:anywhere}
.distribution-score{font-size:32px;margin:20px 0}
.experiment-record{border-top:1px solid var(--line);padding:18px 0;overflow-wrap:anywhere}
.comparison-metric{padding:16px 0;border-bottom:1px solid var(--line)}
.bar-row{display:flex;align-items:center;gap:10px;margin:8px 0;font-size:12.5px}
.bar-row meter{flex:1;min-width:50px;height:16px;accent-color:var(--muted)}
.bar-row.augmented meter{accent-color:var(--green)}
.bar-row b{width:62px;text-align:right;font-weight:500}
.evaluation-layout{display:grid;grid-template-columns:1fr 1.1fr;gap:30px}
@media(max-width:950px){.evaluation-layout{grid-template-columns:1fr}.tabs{flex-wrap:wrap}}
</style>
