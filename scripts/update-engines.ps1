param([switch]$Full)
$ErrorActionPreference='Stop'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
if($Full){
    & docker compose build physics blender gpu
    if($LASTEXITCODE -ne 0){throw 'Engine build failed'}
}else{
    foreach($engineName in @('fds','blender','gpu')){
        $imageName="ai07-modeling:$engineName"
        & docker image inspect $imageName --format '{{.Id}}' | Out-Null
        if($LASTEXITCODE -ne 0){throw "Missing $imageName; run scripts/update-engines.ps1 -Full"}
        & docker build -f docker/Dockerfile.engine-update --build-arg "BASE_IMAGE=$imageName" -t $imageName .
        if($LASTEXITCODE -ne 0){throw "Update failed: $imageName"}
    }
}
