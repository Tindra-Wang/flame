param(
    [ValidateSet('Assets','Build','Generate','Simulate','Render','Enhance','Review','Finish','Test','Doctor')][string]$Stage='Doctor',
    [ValidatePattern('^[A-Za-z][A-Za-z0-9_-]*$')][string]$Run='compose-run',
    [ValidatePattern('^[A-Za-z][A-Za-z0-9_.-]*\.json$')][string]$Config='room.json',
    [ValidateRange(2,10000)][int]$Count=2,
    [string]$Tasks='',
    [string]$Reviewer='',
    [switch]$Mirror
)
$ErrorActionPreference='Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
function Invoke-Compose {
    & docker compose @args
    if ($LASTEXITCODE -ne 0) { throw "Compose failed ($LASTEXITCODE)" }
}
$root="/app/artifacts/$Run"
switch ($Stage) {
    Assets { Invoke-Compose run --rm assets }
    Build {
        $pythonOptions=@(); $renderOptions=@()
        if ($Mirror) {
            $pythonOptions=@('--build-arg','PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/')
            $renderOptions=@('--build-arg','DEBIAN_MIRROR=mirrors.aliyun.com')
        }
        Invoke-Compose build @pythonOptions modeling
        Invoke-Compose run --rm assets --only fds
        Invoke-Compose run --rm assets --only blender
        Invoke-Compose --profile pipeline build physics
        Invoke-Compose --profile pipeline build @renderOptions blender
        Invoke-Compose --profile pipeline build @pythonOptions gpu
        Invoke-Compose run --rm assets --only yolo
        Invoke-Compose run --rm assets --only fid
        Invoke-Compose run --rm assets --only sd15
    }
    Simulate { Invoke-Compose run --rm physics simulate --config "/app/configs/$Config" --root $root }
    Render { Invoke-Compose run --rm blender render --config "/app/configs/$Config" --root $root --count $Count }
    Enhance { Invoke-Compose run --rm enhance enhance --config "/app/configs/$Config" --root $root }
    Generate {
        Invoke-Compose run --rm physics simulate --config "/app/configs/$Config" --root $root
        Invoke-Compose run --rm blender render --config "/app/configs/$Config" --root $root --count $Count
        Invoke-Compose run --rm enhance enhance --config "/app/configs/$Config" --root $root
        Invoke-Compose run --rm modeling label-studio --run "$root/enhanced" --image-base-url "/data/local-files/?d=$Run/enhanced" --output "$root/review-tasks.json"
        Write-Host "Candidates ready: artifacts/$Run/enhanced. Human review required."
    }
    Review {
        & docker desktop start
        if ($LASTEXITCODE -ne 0) { throw 'Docker Desktop could not start; check its WSL2/Linux engine status' }
        $ready=$false
        for ($attempt=0; $attempt -lt 30; $attempt++) {
            & docker info --format '{{.ServerVersion}}' 2>$null | Out-Null
            if ($LASTEXITCODE -eq 0) { $ready=$true; break }
            Start-Sleep -Seconds 2
        }
        if (!$ready) { throw 'Docker Linux engine is not ready; check Docker Desktop' }
        Invoke-Compose --profile annotation up -d annotation
        for ($attempt=0; $attempt -lt 40; $attempt++) {
            try {
                $health=Invoke-RestMethod 'http://127.0.0.1:8080/health' -TimeoutSec 3
                if ($health.status -eq 'UP') {
                    Write-Host 'Label Studio ready: http://127.0.0.1:8080'
                    return
                }
            } catch { }
            Start-Sleep -Seconds 2
        }
        throw 'Label Studio did not become ready; run docker compose logs annotation'
    }
    Finish {
        if (!$Tasks -or !$Reviewer) { throw 'Supply -Tasks (JSON path inside /app/artifacts/) and -Reviewer' }
        if (!$Tasks.StartsWith('/app/artifacts/')) { throw 'Tasks must be under mounted /app/artifacts/' }
        Invoke-Compose run --rm modeling import-label-studio --run "$root/enhanced" --tasks $Tasks --reviewer $Reviewer
        Invoke-Compose run --rm modeling publish --run "$root/enhanced" --output "$root/version" --version $Run
        Invoke-Compose run --rm modeling export --version-dir "$root/version" --output "$root/export"
    }
    Test { Invoke-Compose run --rm --entrypoint python modeling -m pytest -q }
    Doctor {
        Invoke-Compose version
        Invoke-Compose run --rm modeling doctor
        Invoke-Compose run --rm --entrypoint fds physics -v
        Invoke-Compose run --rm --entrypoint blender blender --version
        Invoke-Compose run --rm --entrypoint python gpu -c 'import torch; print(torch.__version__, torch.cuda.is_available()); print(torch.cuda.get_device_name(0)); print((torch.ones(8,device="cuda")*2).sum().item())'
    }
}
