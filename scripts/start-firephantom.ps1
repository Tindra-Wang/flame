param([switch]$SkipBuild)
$ErrorActionPreference='Stop'
$taskRoot=Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $taskRoot
& "$taskRoot/.venv/Scripts/python.exe" scripts/init-platform.py
if(-not $SkipBuild){
    Push-Location -LiteralPath "$taskRoot/integrations/firephantom/web"
    try { & npm ci --no-audit --no-fund; if($LASTEXITCODE -ne 0){throw 'FirePhantom npm ci failed'}; & npm run build; if($LASTEXITCODE -ne 0){throw 'FirePhantom frontend build failed'} }
    finally { Pop-Location }
}
$composeArgs=@('compose','--env-file','.cache/platform/compose.env','-f','compose.yaml','-f','compose.platform.yaml','-f','compose.firephantom.yaml')
if(-not $SkipBuild){ & docker @composeArgs build firephantom platform-api; if($LASTEXITCODE -ne 0){throw 'FirePhantom Docker build failed'} }
& docker @composeArgs up -d --no-build firephantom platform-api platform-web annotation-platform
if($LASTEXITCODE -ne 0){throw 'FirePhantom service startup failed'}
Write-Output 'AI-07: http://localhost:3000/#simulation   FirePhantom: http://localhost:8765/'
Write-Output 'FirePhantom uses its own accounts and data; the existing FDS workflow remains separate.'
