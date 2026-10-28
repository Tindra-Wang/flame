param([switch]$Monitoring)
$ErrorActionPreference='Stop'
$projectRoot=Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
& "$projectRoot/.venv/Scripts/python.exe" scripts/init-platform.py
$composeArgs=@('compose','--env-file','.cache/platform/compose.env','-f','compose.yaml','-f','compose.platform.yaml')
& ./scripts/build-scene-editor.ps1
if($LASTEXITCODE -ne 0){throw 'Scene editor build failed'}
& docker @composeArgs up -d --build platform-web platform-api annotation-platform
if($LASTEXITCODE -ne 0) { throw 'Compose startup failed. Check Docker Desktop and service logs.' }
if($Monitoring) { & docker @composeArgs --profile monitoring up -d prometheus grafana }
$workerArgs=@('-u','-m','platform_api.worker','--api','http://127.0.0.1:8092')
$workerPidFile="$projectRoot/.cache/platform/worker-compose.pid"
$existingWorker=$null
if(Test-Path -LiteralPath $workerPidFile){
    $recordedWorkerId=0
    if([int]::TryParse((Get-Content -LiteralPath $workerPidFile -Raw).Trim(),[ref]$recordedWorkerId)){
        $candidateWorker=Get-CimInstance Win32_Process -Filter "ProcessId=$recordedWorkerId" -ErrorAction SilentlyContinue
        if($candidateWorker -and $candidateWorker.ExecutablePath -eq "$projectRoot\.venv\Scripts\python.exe" -and $candidateWorker.CommandLine -like '*platform_api.worker*8092*'){$existingWorker=$candidateWorker}
    }
}
if(-not $existingWorker){
    $workerProcess=Start-Process -FilePath "$projectRoot/.venv/Scripts/python.exe" -ArgumentList $workerArgs -WorkingDirectory $projectRoot -WindowStyle Hidden -RedirectStandardOutput "$projectRoot/.cache/platform/worker-compose.stdout.log" -RedirectStandardError "$projectRoot/.cache/platform/worker-compose.stderr.log" -PassThru
    Set-Content -LiteralPath $workerPidFile -Value $workerProcess.Id
}
Write-Output 'Workbench: http://localhost:3000   OpenAPI: http://localhost:8092/docs'
Write-Output 'First visit: create your own workbench account. No shared password is embedded in the webpage.'
