$ErrorActionPreference='Stop'
$taskRoot=Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $taskRoot
$sourceWeb=Join-Path $taskRoot 'integrations/firephantom/web'
if(-not (Test-Path -LiteralPath "$sourceWeb/node_modules/vite/bin/vite.js")){
 & npm --prefix $sourceWeb ci --no-audit --no-fund
 if($LASTEXITCODE -ne 0){throw 'Scene editor dependencies failed'}
}
& node "$sourceWeb/node_modules/vite/bin/vite.js" build --config scene-editor/vite.config.mjs
if($LASTEXITCODE -ne 0){throw 'Scene editor build failed'}
