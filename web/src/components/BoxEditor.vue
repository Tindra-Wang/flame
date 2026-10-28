<script setup lang="ts">
import {nextTick,onUnmounted,ref,watch} from 'vue'
import {Trash2,RotateCcw,Check, X} from 'lucide-vue-next'
const props=defineProps<{sample:any;busy:boolean;parent?:any;continuous?:boolean}>()
const emit=defineEmits<{save:[boxes:number[][],decision:string,timing?:{active_s:number;mode:string}];close:[]}>()
const boxes=ref<number[][]>([]), drawing=ref<number[]|null>(null), svg=ref<SVGSVGElement|null>(null), active=ref(-1)
const activeSeconds=ref(0), startedEmpty=ref(true)
let lastActivity=Date.now()
watch(()=>props.sample,s=>{boxes.value=s?JSON.parse(JSON.stringify(s.boxes)):[];active.value=-1;activeSeconds.value=0;lastActivity=Date.now();startedEmpty.value=boxes.value.length===0},{immediate:true})
const timer=setInterval(()=>{if(document.visibilityState==='visible'&&Date.now()-lastActivity<15000)activeSeconds.value++},1000)
onUnmounted(()=>clearInterval(timer))
function noteActivity(){lastActivity=Date.now()}
function saveTiming(){return{active_s:activeSeconds.value,mode:startedEmpty.value&&boxes.value.length>0?'scratch':'candidate'}}
function point(event:PointerEvent){const r=svg.value!.getBoundingClientRect();return [Math.max(0,Math.min(props.sample.width,(event.clientX-r.left)/r.width*props.sample.width)),Math.max(0,Math.min(props.sample.height,(event.clientY-r.top)/r.height*props.sample.height))]}
function down(event:PointerEvent){if(event.button!==0)return; const p=point(event);drawing.value=[...p,...p];svg.value?.setPointerCapture(event.pointerId)}
function move(event:PointerEvent){if(drawing.value){const p=point(event);drawing.value=[drawing.value[0],drawing.value[1],...p]}}
function up(){if(drawing.value){let[x0,y0,x1,y1]=drawing.value;if(Math.abs(x1-x0)>2&&Math.abs(y1-y0)>2){boxes.value.push([Math.min(x0,x1),Math.min(y0,y1),Math.max(x0,x1),Math.max(y0,y1)]);active.value=boxes.value.length-1}drawing.value=null}}
async function addBox(){boxes.value.push([Math.round(props.sample.width*.2),Math.round(props.sample.height*.2),Math.round(props.sample.width*.6),Math.round(props.sample.height*.6)]);active.value=boxes.value.length-1;await nextTick();document.querySelector<HTMLInputElement>('.box-row:last-of-type input')?.focus()}
function rect(b:number[]){return{x:Math.min(b[0],b[2]),y:Math.min(b[1],b[3]),width:Math.abs(b[2]-b[0]),height:Math.abs(b[3]-b[1])}}
</script>
<template>
  <section class="review-editor" aria-label="样本标注编辑" @pointerdown="noteActivity" @pointermove="noteActivity" @keydown="noteActivity">
    <div class="section-heading"><div><h2>检查并修订火焰框</h2><p>拖动绘制新框；选择下方的框编辑坐标。空标签表示无火。</p></div><button class="icon-button" @click="emit('close')" aria-label="关闭编辑"><X :size="20"/></button></div>
    <div v-if="parent" class="comparison-strip"><figure><img :src="parent.url" alt="增强前的父图"><figcaption>原图 · {{parent.sample_id}}</figcaption></figure><figure><img :src="sample.url" alt="当前增强图"><figcaption>增强图 · {{sample.sample_id}}</figcaption></figure></div>
    <button type="button" class="secondary small add-box-button" @click="addBox">添加火焰框（可用坐标精确调整）</button>
    <div class="editor-grid"><div class="image-editor"><img :src="sample.url" :alt="sample.sample_id"><svg ref="svg" :viewBox="`0 0 ${sample.width} ${sample.height}`" @pointerdown="down" @pointermove="move" @pointerup="up" @pointercancel="up" aria-label="拖动绘制火焰框"><rect v-for="(b,i) in boxes" :key="i" v-bind="rect(b)" :class="{active:i===active}"/><rect v-if="drawing" v-bind="rect(drawing)" class="drawing"/></svg></div>
    <div class="editor-controls"><div class="badge" :class="sample.review_status">{{sample.source}}</div><h3>{{sample.sample_id}}</h3><p>{{sample.width}} × {{sample.height}} px · {{boxes.length}}个框</p><label v-for="(b,i) in boxes" :key="i" class="box-row" @click="active=i"><span>框 {{i+1}}</span><input v-for="(_,k) in b" :key="k" type="number" v-model.number="boxes[i][k]" :aria-label="`框${i+1}坐标${k+1}`" step="1"><button class="icon-button" @click.stop="boxes.splice(i,1)" aria-label="删除框"><Trash2 :size="16"/></button></label><button class="text-button" @click="boxes=JSON.parse(JSON.stringify(sample.boxes))"><RotateCcw :size="15"/>恢复候选框</button><p class="context-note">候选框不是人工真值。请确认框覆盖可见火焰；增强图需要重新检查位置。</p><p class="context-note timing-note">本次有效操作计时：{{activeSeconds}} 秒（{{startedEmpty&&boxes.length>0?'从零标注':'候选修订'}}模式，超过15秒无操作自动暂停）</p><div class="button-row"><button class="primary" :disabled="busy" @click="emit('save',boxes,'approved',saveTiming())"><Check :size="16"/>{{continuous?'通过并下一张':'通过审核'}}</button><button class="secondary danger" :disabled="busy" @click="emit('save',boxes,'rejected',saveTiming())">剔除样本</button></div></div></div>
  </section>
</template>
