<script setup lang="ts">
import {computed} from 'vue'
const props=defineProps<{runs:any[];runId:string;scenes:any[];samples:any[]}>()
const emit=defineEmits<{navigate:[page:string];review:[]}>()
const run=computed(()=>props.runs.find(r=>r.id===props.runId))
const rows=computed(()=>props.samples.filter(s=>s.run_id===props.runId))
const valid=computed(()=>rows.value.filter(s=>s.quality?.auto_screen_pass).length)
const scenarios=computed(()=>new Set(props.scenes.map(s=>s.config.editor_scene?.scenario||s.config.scene_type)))
const steps=[
 {name:'生成式数据合成',hint:'3D编辑页提交',go:()=>emit('navigate','simulation')},
 {name:'自动标注与质检',hint:'候选框与结构质检',current:true,go:()=>emit('review')},
 {name:'页内人工审核',hint:'框选修订与通过',go:()=>emit('review')},
 {name:'版本冻结',hint:'DVC快照与导出',go:()=>emit('navigate','versions')},
 {name:'分布与检测对照',hint:'FID与A/B训练',go:()=>emit('navigate','evaluation')},
]
const seg=computed(()=>{const c=run.value?.count||0;const a=run.value?.approved||0,r=run.value?.rejected||0,p=Math.max(c-a-r,0);return {a,r,p,c}})
</script>
<template>
 <section class="batch-workflow" aria-label="数据处理链路">
  <div class="wf-top">
   <span class="stat-chip"><b>{{scenes.length}}</b>已保存场景</span>
   <span class="stat-chip"><b>{{scenarios.size}}</b>类基础场景</span>
   <span class="stat-chip muted" title="同一场景换天气、机位或视角不增加独立工况覆盖">场景数 ≠ 独立工况覆盖</span>
  </div>
  <ol class="wf-steps">
   <li v-for="(s,i) in steps" :key="s.name"><button type="button" :class="{current:s.current}" @click="s.go()"><span class="wf-dot">{{String(i+1).padStart(2,'0')}}</span><span class="wf-text"><span class="wf-name">{{s.name}}</span><span class="wf-hint">{{s.hint}}</span></span></button></li>
  </ol>
  <div v-if="run" class="batch-progress">
   <div class="seg-bar" role="img" :aria-label="`本批${seg.c}张：已通过${run.approved}，已剔除${run.rejected}，待审核${seg.p}`">
    <span class="seg approved" :style="{width:(seg.c?seg.a/seg.c*100:0)+'%'}"></span>
    <span class="seg rejected" :style="{width:(seg.c?seg.r/seg.c*100:0)+'%'}"></span>
    <span class="seg pending" :style="{width:(seg.c?seg.p/seg.c*100:0)+'%'}"></span>
   </div>
   <div class="seg-legend">
    <span><i class="seg-dot total"></i>本批 {{seg.c}} 张</span>
    <span><i class="seg-dot approved"></i>已通过 {{run.approved}}</span>
    <span><i class="seg-dot rejected"></i>已剔除 {{run.rejected}}</span>
    <span><i class="seg-dot pending"></i>待审核 {{seg.p}}</span>
    <span><i class="seg-dot pass"></i>自动质检通过 {{valid}}<em>·仍需人工确认</em></span>
   </div>
  </div>
  <p v-else class="context-note">选择一个批次，查看它从候选标注到审核发布的分段进度；自动筛选通过仍需人工确认。</p>
 </section>
</template>
<style scoped>
.batch-workflow{padding:0 0 24px;border-bottom:1px solid var(--line);margin-bottom:24px}
.wf-top{display:flex;gap:10px;align-items:center;flex-wrap:wrap}
.stat-chip{display:inline-flex;align-items:center;gap:7px;background:var(--soft);border-radius:99px;padding:7px 14px;font-size:12.5px;color:var(--muted)}
.stat-chip b{font-size:14px;color:var(--ink);font-weight:700;font-variant-numeric:tabular-nums}
.stat-chip.muted{background:transparent;border:1px dashed var(--line);color:var(--faint);cursor:help}
.wf-steps{display:flex;list-style:none;margin:22px 0 0;padding:0}
.wf-steps li{flex:1;position:relative;min-width:0}
.wf-steps li:not(:last-child)::after{content:'';position:absolute;top:14px;left:calc(28px + 12px);right:6px;height:1.5px;background:var(--line)}
.wf-steps button{position:relative;z-index:1;display:flex;align-items:flex-start;gap:11px;width:100%;background:transparent;text-align:left;padding:2px 0;border-radius:8px}
.wf-dot{width:28px;height:28px;border-radius:50%;border:1.5px solid var(--line);background:var(--surface);display:grid;place-items:center;font-size:11.5px;font-weight:700;color:var(--muted);flex-shrink:0;font-variant-numeric:tabular-nums;transition:all var(--t-fast) var(--ease)}
.wf-steps button:hover .wf-dot{border-color:var(--orange);color:var(--orange);transform:translateY(-1px)}
.wf-steps button.current .wf-dot{background:var(--grad);border-color:transparent;color:#fff;box-shadow:0 3px 10px rgba(217,72,15,.3)}
.wf-name{display:block;font-size:13.5px;font-weight:600;color:var(--ink);line-height:1.4}
.wf-steps button:hover .wf-name{color:var(--orange)}
.wf-hint{display:block;font-size:12px;color:var(--muted);margin-top:2px}
.batch-progress{margin-top:22px}
.seg-bar{display:flex;height:10px;border-radius:99px;overflow:hidden;background:var(--surface-2);max-width:560px}
.seg{transition:width var(--t-slow) var(--ease)}
.seg.approved{background:#5bb37f}
.seg.rejected{background:#e2694a}
.seg.pending{background:#eeb25c}
.seg-legend{display:flex;gap:18px;flex-wrap:wrap;margin-top:12px;font-size:12.5px;color:var(--muted)}
.seg-legend em{font-style:normal;color:var(--faint)}
.seg-dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:6px;vertical-align:1px}
.seg-dot.total{background:var(--faint)}
.seg-dot.approved{background:#5bb37f}
.seg-dot.rejected{background:#e2694a}
.seg-dot.pending{background:#eeb25c}
.seg-dot.pass{background:#c98a4b}
@media(max-width:950px){.wf-steps{flex-wrap:wrap;gap:14px}.wf-steps li{flex:1 1 40%}.wf-steps li:not(:last-child)::after{display:none}}
</style>
