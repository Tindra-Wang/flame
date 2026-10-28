import {fileURLToPath} from 'node:url'
import path from 'node:path'
import fs from 'node:fs'
import {transformWithEsbuild} from '../integrations/firephantom/web/node_modules/vite/dist/node/index.js'
const root=path.dirname(fileURLToPath(import.meta.url))
const deps=path.resolve(root,'../integrations/firephantom/web/node_modules')
export default {
 plugins:[{
  name:'original-editor-panels',
  resolveId(id){if(id==='original-editor-panels')return '\0original-editor-panels'},
  async load(id){
   if(id!=='\0original-editor-panels')return
   const upstream=path.resolve(root,'../integrations/firephantom/web/src')
   let code=fs.readFileSync(path.join(upstream,'main.jsx'),'utf8')
   code=code.replace('async function api(path, options = {}) {','async function unusedOriginalApi(path, options = {}) {')
    .replace(/createRoot\(document.getElementById\("root"\)\)\.render\(<Root \/>\);/,'')
    .replace('"./app.css"',JSON.stringify(path.join(upstream,'app.css')))
    .replace('"./scene-editor.jsx"',JSON.stringify(path.join(upstream,'scene-editor.jsx')))
    .replace('return `/api/v1/samples/','return `${compatibilityPrefix}/samples/')
    .replace('href={`#/jobs/${job.job_id}`}','href={`/?project=${bridgeProject}&job=${job.job_id}#jobs`}')
   code=code.replace('onSubmit, notify }) {','onSubmit, notify, physicalMode = false }) {').replace('const skyHint = environment ===',`const skyHint = physicalMode ? "FDS气象条件进入物理求解；当前雨滴为液态近似，不等于材料受潮或熄灭模型。图像增强在数据合成中单独运行。" : environment ===`)
   code=`import {originalApi as api,compatibilityPrefix,bridgeProject} from ${JSON.stringify(path.join(root,'original-api.js'))};\n`+code+'\nexport {GenerationSettings,SceneRuns,INITIAL_GENERATION};'
   return await transformWithEsbuild(code,path.join(upstream,'original-panels.jsx'),{loader:'jsx',jsx:'automatic'})
  }
 }],
 root,base:'/scene-editor/',
 resolve:{alias:{'three/addons':path.join(deps,'three/examples/jsm'),react:path.join(deps,'react'),'react-dom':path.join(deps,'react-dom'),three:path.join(deps,'three'),'lucide-react':path.join(deps,'lucide-react'),'@react-three/fiber':path.join(deps,'@react-three/fiber'),'@react-three/drei':path.join(deps,'@react-three/drei')}},
 build:{outDir:path.resolve(root,'../web/public/scene-editor'),emptyOutDir:true,chunkSizeWarningLimit:1800},
}
