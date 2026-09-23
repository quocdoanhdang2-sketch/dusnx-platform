$ErrorActionPreference = "Stop"

$ProjectRoot = $PSScriptRoot
$PythonExe = Join-Path $ProjectRoot "python\.venv\Scripts\python.exe"
$Checkpoint = Join-Path $ProjectRoot "artifacts\dusnx_smoke.pt"

function Test-ListeningPort {
    param([int]$Port)
    return $null -ne (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
}

if (-not (Test-Path $PythonExe)) {
    throw "Python virtual environment was not found: $PythonExe"
}

if (-not (Test-Path $Checkpoint)) {
    throw "DUSN-X checkpoint was not found: $Checkpoint"
}

Write-Host "Starting DUSN-X local services..." -ForegroundColor Cyan

if (Test-ListeningPort 8000) {
    Write-Host "[SKIP] FastAPI is already listening on port 8000." -ForegroundColor Yellow
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

Write-Host "Waiting for services to initialize..." -ForegroundColor Cyan
Start-Sleep -Seconds 5

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
