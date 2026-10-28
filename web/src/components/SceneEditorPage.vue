<script setup lang="ts">
import {computed} from 'vue'
const props=defineProps<{project:string}>()
const scene=new URLSearchParams(location.search).get('scene')||'room'
const source=computed(()=>`/scene-editor/index.html?project=${encodeURIComponent(props.project)}&scene=${encodeURIComponent(scene)}`)
</script>
<template><section class="scene-editor-host"><iframe :src="source" title="完整三维场景编辑器" allow="fullscreen"></iframe><p>场景与主平台共用账户；保存后返回仿真与合成。</p></section></template>
<style scoped>.scene-editor-host{margin:-10px -16px 0}.scene-editor-host iframe{display:block;border:0;width:100%;height:max(780px,calc(100vh - 210px));background:#1d1d1d}.scene-editor-host p{font-size:12px;color:var(--muted);margin:8px 0}@media(max-width:760px){.scene-editor-host{margin:0 -10px}.scene-editor-host iframe{height:1900px}}</style>
