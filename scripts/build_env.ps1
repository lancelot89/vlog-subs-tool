param(
    [string]$TargetDir = (Join-Path (Split-Path $PSScriptRoot -Parent) 'dist\AppRoot'),
    [string]$Python = $env:PYTHON_BIN
)

if (-not $Python) {
    $Python = 'python'
}

$EnvDir = Join-Path $TargetDir 'env'

if (Test-Path $EnvDir -and $env:FORCE_REBUILD -ne '1') {
    Write-Host "[INFO] Reusing existing environment at $EnvDir"
} else {
    Write-Host "[INFO] Creating virtual environment at $EnvDir"
    if (Test-Path $EnvDir) {
        Remove-Item -Recurse -Force $EnvDir
    }
    & $Python -m venv $EnvDir
}

$PythonExe = Join-Path $EnvDir 'Scripts\python.exe'

& $PythonExe -m pip install --upgrade pip wheel setuptools
& $PythonExe -m pip install -r (Join-Path (Split-Path $PSScriptRoot -Parent) 'requirements.txt')
& $PythonExe -m compileall (Join-Path (Split-Path $PSScriptRoot -Parent) 'app') | Out-Null

Write-Host "[INFO] Environment ready at $EnvDir"
