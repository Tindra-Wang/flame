$ErrorActionPreference='Stop'
$projectRoot=Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$toolsDirectory=Join-Path $projectRoot 'tools'
& docker compose run --rm --no-deps -v "${toolsDirectory}:/app/tools:ro" --entrypoint /usr/local/bin/blender blender --background --factory-startup --python /app/tools/create-scene-models.py
if($LASTEXITCODE -ne 0){throw 'Scene model generation failed; install the Blender engine image first.'}
