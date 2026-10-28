param([string]$Python = "python")
$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location -LiteralPath $projectRoot
try {
    $env:UV_CACHE_DIR = Join-Path $projectRoot '.cache\uv'
    $env:PYTHONIOENCODING = 'utf-8'
    if (Get-Command uv -ErrorAction SilentlyContinue) {
        if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
            uv venv --python $Python .venv
            if ($LASTEXITCODE -ne 0) { throw '创建虚拟环境失败' }
        }
        uv pip install --python '.venv\Scripts\python.exe' -r requirements-dev.lock -e .
    } else {
        if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
            & $Python -m venv .venv
            if ($LASTEXITCODE -ne 0) { throw '创建虚拟环境失败' }
        }
        & '.\.venv\Scripts\python.exe' -m pip install -r requirements-dev.lock -e .
    }
    if ($LASTEXITCODE -ne 0) { throw '安装依赖失败' }
    & '.\.venv\Scripts\python.exe' -m fire_modeling doctor
    if ($LASTEXITCODE -ne 0) { throw '环境检查失败' }
} finally {
    Pop-Location
}
