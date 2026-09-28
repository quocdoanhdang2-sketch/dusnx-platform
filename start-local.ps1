$ErrorActionPreference = "Stop"

$ProjectRoot = $PSScriptRoot
Import-Module (Join-Path $ProjectRoot "scripts\LocalHealth.psm1") -Force
$PythonExe = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$LegacyPythonExe = Join-Path $ProjectRoot "python\.venv\Scripts\python.exe"
if (-not (Test-Path $PythonExe) -and (Test-Path $LegacyPythonExe)) { $PythonExe = $LegacyPythonExe }
if (-not (Test-Path $PythonExe)) {
    $sysPy = (Get-Command python -ErrorAction SilentlyContinue).Source
    if ($sysPy) { $PythonExe = $sysPy }
}
$DefaultCheckpoint = Join-Path $ProjectRoot "artifacts\dusnx_smoke_v2.pt"
$Checkpoint = if ($env:DUSNX_CHECKPOINT) { $env:DUSNX_CHECKPOINT } else { $DefaultCheckpoint }
$Device = if ($env:DUSNX_DEVICE) { $env:DUSNX_DEVICE } else { "auto" }

if (-not (Test-Path $PythonExe)) { throw "Python was not found: $PythonExe" }
if (-not (Test-Path $Checkpoint)) {
    throw "DUSN-X v2 checkpoint was not found: $Checkpoint. Generate the v2 dataset and run python\scripts\train.py with configs\smoke_v2.yaml."
}

Write-Host "Starting DUSN-X local services..." -ForegroundColor Cyan

if ($owner = Get-DusnxListeningProcess 8000) {
    Write-Host "[CHECK] Port 8000 is already listening (PID $($owner.ProcessId), $($owner.ProcessName)); validating it without stopping it." -ForegroundColor Yellow
} else {
    $command = "Set-Location '$ProjectRoot\python'; `$env:PYTHONPATH='$ProjectRoot\python;$ProjectRoot\python\src'; `$env:DUSNX_CHECKPOINT='$Checkpoint'; `$env:DUSNX_DEVICE='$Device'; & '$PythonExe' -m uvicorn apps.ai_api.main:app --host 127.0.0.1 --port 8000"
    Start-Process powershell.exe -WindowStyle Hidden -ArgumentList "-ExecutionPolicy", "Bypass", "-Command", $command
    Write-Host "[START] FastAPI -> http://127.0.0.1:8000 (device: $Device)" -ForegroundColor Green
}


if ($owner = Get-DusnxListeningProcess 8080) {
    Write-Host "[CHECK] Port 8080 is already listening (PID $($owner.ProcessId), $($owner.ProcessName)); validating it without stopping it." -ForegroundColor Yellow
} else {
    $GatewayData = Join-Path $ProjectRoot "runtime\gateway-data"
    New-Item -ItemType Directory -Force -Path $GatewayData | Out-Null
    $command = "Set-Location '$ProjectRoot\gateway-dotnet'; `$env:AI_API_URL='http://127.0.0.1:8000'; `$env:DUSNX_DATA_DIR='$GatewayData'; dotnet run --urls 'http://127.0.0.1:8080'"
    Start-Process powershell.exe -WindowStyle Hidden -ArgumentList "-ExecutionPolicy", "Bypass", "-Command", $command
    Write-Host "[START] Gateway -> http://127.0.0.1:8080" -ForegroundColor Green
}

Write-Host "Waiting for all required services..." -ForegroundColor Cyan
$ExpectedCheckpoint = [System.IO.Path]::GetFullPath($Checkpoint)
$AiHealth = Wait-DusnxHttpService -Name "FastAPI" -Uri "http://127.0.0.1:8000/health" -TimeoutSeconds 60 -Validate {
    param($health)
    if ($health.runtime_mode -ne "trained_dusnx") { throw "runtime_mode=$($health.runtime_mode); $($health.metadata.warning)" }
    if ($health.checkpoint_loaded -ne $ExpectedCheckpoint) { throw "checkpoint_loaded=$($health.checkpoint_loaded), expected=$ExpectedCheckpoint" }
    if ([string]::IsNullOrWhiteSpace($health.model_version)) { throw "model_version is empty" }
}
Write-Host "[OK] FastAPI v2: $($AiHealth.checkpoint_loaded) ($($AiHealth.model_version))" -ForegroundColor Green

$GatewayHealth = Wait-DusnxHttpService -Name "Gateway" -Uri "http://127.0.0.1:8080/health" -TimeoutSeconds 60 -Validate {
    param($health)
    if ($health.status -ne "ok" -or $health.service -ne "dusnx-gateway") { throw "unexpected Gateway health payload" }
}
Write-Host "[OK] Gateway: $($GatewayHealth.status)" -ForegroundColor Green

$WebResponse = Wait-DusnxHttpService -Name "Web UI (via Gateway)" -Uri "http://127.0.0.1:8080" -TimeoutSeconds 30 -Probe {
    param($uri)
    Invoke-WebRequest -Uri $uri -UseBasicParsing -TimeoutSec 3
} -Validate {
    param($response)
    if ($response.StatusCode -ne 200 -or $response.Content -notlike "*DUSN-X*") { throw "unexpected Web UI response from Gateway" }
}

Write-Host "[OK] Web UI: HTTP $($WebResponse.StatusCode)" -ForegroundColor Green
Write-Host "DUSN-X local startup finished: all required services are healthy." -ForegroundColor Green
Write-Host "Open Web UI: http://127.0.0.1:8080" -ForegroundColor Cyan
