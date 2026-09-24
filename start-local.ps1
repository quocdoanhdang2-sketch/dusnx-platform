$ErrorActionPreference = "Stop"

$ProjectRoot = $PSScriptRoot
$PythonExe = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$LegacyPythonExe = Join-Path $ProjectRoot "python\.venv\Scripts\python.exe"
if (-not (Test-Path $PythonExe) -and (Test-Path $LegacyPythonExe)) {
    $PythonExe = $LegacyPythonExe
}
$DefaultCheckpoint = Join-Path $ProjectRoot "artifacts\dusnx_smoke_v2.pt"
$Checkpoint = if ($env:DUSNX_CHECKPOINT) { $env:DUSNX_CHECKPOINT } else { $DefaultCheckpoint }

function Test-ListeningPort {
    param([int]$Port)
    return $null -ne (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
}

if (-not (Test-Path $PythonExe)) {
    throw "Python virtual environment was not found: $PythonExe"
}

if (-not (Test-Path $Checkpoint)) {
    throw @"
DUSN-X v2 checkpoint was not found: $Checkpoint
From $ProjectRoot, create it with:
  & '$PythonExe' .\python\scripts\generate_synthetic.py --events 30000 --users 1000 --out .\data\synthetic_30k_v2.jsonl
  & '$PythonExe' .\python\scripts\train.py --config .\configs\smoke_v2.yaml
"@
}

Write-Host "Starting DUSN-X local services..." -ForegroundColor Cyan

if (Test-ListeningPort 8000) {
    throw "Port 8000 is already in use. Stop the existing FastAPI process before running start-local.ps1; it may be using an older checkpoint."
}
else {
    $FastApiCommand = @"
Set-Location '$ProjectRoot\python'
`$env:PYTHONPATH='$ProjectRoot\python;$ProjectRoot\python\src'
`$env:DUSNX_CHECKPOINT='$Checkpoint'
`$env:DUSNX_DEVICE='cpu'
& '$PythonExe' -m uvicorn apps.ai_api.main:app --host 127.0.0.1 --port 8000
"@
    Start-Process powershell.exe -ArgumentList "-NoExit", "-ExecutionPolicy", "Bypass", "-Command", $FastApiCommand
    Write-Host "[START] FastAPI -> http://127.0.0.1:8000" -ForegroundColor Green
}

if (Test-ListeningPort 8080) {
    Write-Host "[SKIP] Gateway is already listening on port 8080." -ForegroundColor Yellow
}
else {
    $GatewayCommand = @"
Set-Location '$ProjectRoot\gateway-dotnet'
`$env:AI_API_URL='http://127.0.0.1:8000'
dotnet run --urls 'http://127.0.0.1:8080'
"@
    Start-Process powershell.exe -ArgumentList "-NoExit", "-ExecutionPolicy", "Bypass", "-Command", $GatewayCommand
    Write-Host "[START] Gateway -> http://127.0.0.1:8080" -ForegroundColor Green
}

if (Test-ListeningPort 3000) {
    Write-Host "[SKIP] Web UI is already listening on port 3000." -ForegroundColor Yellow
}
else {
    $WebCommand = @"
Set-Location '$ProjectRoot\web-ui'
py -3.12 -m http.server 3000 --bind 127.0.0.1
"@
    Start-Process powershell.exe -ArgumentList "-NoExit", "-ExecutionPolicy", "Bypass", "-Command", $WebCommand
    Write-Host "[START] Web UI -> http://127.0.0.1:3000" -ForegroundColor Green
}

Write-Host "Waiting for FastAPI v2 to initialize..." -ForegroundColor Cyan
$AiHealth = $null
for ($attempt = 1; $attempt -le 12; $attempt++) {
    try {
        $AiHealth = Invoke-RestMethod "http://127.0.0.1:8000/health" -TimeoutSec 3
        break
    }
    catch {
        Start-Sleep -Seconds 1
    }
}

if ($null -eq $AiHealth) {
    throw "FastAPI did not become healthy on port 8000. Check the FastAPI window for startup errors."
}
if ($AiHealth.runtime_mode -ne "trained_dusnx") {
    throw "FastAPI is not using a trained checkpoint (runtime_mode=$($AiHealth.runtime_mode)). $($AiHealth.metadata.warning)"
}
if ($AiHealth.checkpoint_loaded -ne [System.IO.Path]::GetFullPath($Checkpoint)) {
    throw "FastAPI loaded an unexpected checkpoint: $($AiHealth.checkpoint_loaded). Expected: $([System.IO.Path]::GetFullPath($Checkpoint))"
}
if ([string]::IsNullOrWhiteSpace($AiHealth.model_version)) {
    throw "FastAPI health response has no model_version; state compatibility cannot be verified."
}
Write-Host "[OK] FastAPI v2: $($AiHealth.checkpoint_loaded) ($($AiHealth.model_version))" -ForegroundColor Green

$Services = @(
    @{ Name = "FastAPI"; Url = "http://127.0.0.1:8000/health" },
    @{ Name = "Gateway"; Url = "http://127.0.0.1:8080/health" },
    @{ Name = "Web UI"; Url = "http://127.0.0.1:3000" }
)

foreach ($Service in $Services) {
    try {
        $Response = Invoke-WebRequest $Service.Url -UseBasicParsing -TimeoutSec 5
        Write-Host "[OK] $($Service.Name): HTTP $($Response.StatusCode)" -ForegroundColor Green
    }
    catch {
        Write-Host "[WAIT] $($Service.Name) is not ready yet: $($_.Exception.Message)" -ForegroundColor Yellow
    }
}

Write-Host "DUSN-X local startup finished." -ForegroundColor Cyan
Write-Host "Open: http://127.0.0.1:3000" -ForegroundColor Cyan
