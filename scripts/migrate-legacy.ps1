param(
    [ValidatePattern('^[a-z0-9][a-z0-9_-]*$')][string]$Project='ai07-portable',
    [ValidatePattern('^[a-z0-9][a-z0-9_-]*$')][string]$LegacyProject='ai07-modeling',
    [int]$LegacyApiPort=8092,
    [int]$Port=3000,[int]$ApiPort=8092,[int]$LabelPort=8082,
    [switch]$OverwriteTarget,[switch]$Gpu
)
# Explicit copy migration. Never deletes original files or original database volumes.
$ErrorActionPreference='Stop'
$projectRoot=Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$targetVolume=& docker volume ls --format '{{.Name}}' --filter "name=^${Project}_postgres$"
if($targetVolume -and -not $OverwriteTarget){throw 'Target database volume already exists. Choose a new -Project, or explicitly pass -OverwriteTarget after backing it up.'}
$request=[Net.HttpWebRequest]::Create("http://127.0.0.1:$LegacyApiPort/api/projects/ai07/jobs")
$request.Proxy=$null;$request.Timeout=10000
$response=$request.GetResponse()
try{
    $reader=[IO.StreamReader]::new($response.GetResponseStream())
    try{$jobs=$reader.ReadToEnd()|ConvertFrom-Json}finally{$reader.Dispose()}
}finally{$response.Dispose()}
if(@($jobs | Where-Object {$_.status -in @('running','queued')}).Count){throw 'Finish or cancel legacy queued/running jobs before migration.'}
$setupArgs=@{Action='Setup';Project=$Project;Port=$Port;ApiPort=$ApiPort;LabelPort=$LabelPort}
& "$projectRoot/start.ps1" @setupArgs
if($LASTEXITCODE -ne 0){throw 'Portable setup failed'}
function Invoke-Docker { & docker @args; if($LASTEXITCODE -ne 0){throw "Docker command failed (exit $LASTEXITCODE)"} }
$sourceEnv="$projectRoot/.cache/platform/compose.env"
$sourceValues=@{}
foreach($line in (Get-Content -LiteralPath $sourceEnv)){if($line -match '^([A-Z0-9_]+)=(.*)$'){$sourceValues[$Matches[1]]=$Matches[2]}}
if(-not $sourceValues['AI07_DB_PASSWORD']){throw 'Missing legacy database credentials'}
$oldCompose=@('compose','--project-name',$LegacyProject,'--env-file',$sourceEnv,'-f','compose.yaml','-f','compose.platform.yaml')
$backupName='legacy-'+(Get-Date -Format 'yyyyMMddTHHmmss')+'.tar'
$transferId=& docker create --mount "type=volume,source=${Project}_legacy-credentials,target=/state" "${Project}-api:local" python -c pass
if($LASTEXITCODE -ne 0){throw 'Cannot prepare legacy credential transfer'}
try{Invoke-Docker cp $sourceEnv "${transferId}:/state/compose.env"}finally{Invoke-Docker rm $transferId|Out-Null}
# Stop every matching legacy worker, including duplicates not recorded in the PID file.
# Otherwise a forgotten worker could reconnect to the restored API and write to old host folders.
$hostWorkers=Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object {
    $_.ExecutablePath -eq "$projectRoot\.venv\Scripts\python.exe" -and
    $_.CommandLine -like '*platform_api.worker*' -and $_.CommandLine -like "*:$LegacyApiPort*"
}
foreach($candidate in $hostWorkers){Stop-Process -Id $candidate.ProcessId}
Invoke-Docker @oldCompose stop platform-web platform-api annotation-platform
$env:AI07_DATABASE_URL="postgresql+psycopg://ai07:$($sourceValues['AI07_DB_PASSWORD'])@platform-db:5432/ai07"
$restored=$false
try{
    Invoke-Docker run --rm --network "${LegacyProject}_default" -e AI07_DATABASE_URL `
        --mount "type=bind,source=$projectRoot/artifacts,target=/app/artifacts,readonly" `
        --mount "type=bind,source=$projectRoot/.cache/platform,target=/app/.cache/platform,readonly" `
        --mount "type=bind,source=$projectRoot/models,target=/app/models,readonly" `
        --mount "type=volume,source=${Project}_legacy-credentials,target=/state,readonly" `
        --mount "type=volume,source=${LegacyProject}_platform-label-studio,target=/label-data,readonly" `
        --mount "type=volume,source=${Project}_backups,target=/backups" `
        "${Project}-api:local" python /app/scripts/portable-backup.py backup --name $backupName
    & "$projectRoot/start.ps1" -Project $Project -Port $Port -ApiPort $ApiPort -LabelPort $LabelPort
    if($LASTEXITCODE -ne 0){throw 'Portable startup failed'}
    & "$projectRoot/start.ps1" -Action Restore -Project $Project -Backup $backupName
    if($LASTEXITCODE -ne 0){throw 'Portable restore failed'}
    $restored=$true
    if($Gpu){
        # Restore existing weights before preparing GPU mode, avoiding duplicate network downloads.
        & "$projectRoot/start.ps1" -Project $Project -Gpu
        if($LASTEXITCODE -ne 0){throw 'Data restored, but GPU environment preparation failed'}
    }
    Write-Output "Migration complete. Original data retained. Backup: $backupName"
}catch{
    if($restored){Write-Warning 'Data has migrated. GPU preparation failed; retry start.ps1 -Gpu. Do not repeat migration/restore.'}
    else{Write-Warning 'Migration did not complete. Original files and database are intact. Restart the legacy stack with scripts/start-platform.ps1 -Legacy if needed.'}
    throw
}finally{Remove-Item Env:AI07_DATABASE_URL -ErrorAction SilentlyContinue}
