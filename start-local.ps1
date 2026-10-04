param(
    [int]$AiPort = $(if ($env:DUSNX_AI_PORT) { [int]$env:DUSNX_AI_PORT } else { 8000 }),
    [int]$GatewayPort = $(if ($env:DUSNX_GATEWAY_PORT) { [int]$env:DUSNX_GATEWAY_PORT } else { 8080 }),
    [string]$AiDataDir = $env:DUSNX_DATA_DIR,
    [string]$GatewayDataDir = $env:DUSNX_GATEWAY_DATA_DIR
)
$ErrorActionPreference = "Stop"
$ProjectRoot = $PSScriptRoot
Import-Module (Join-Path $ProjectRoot "scripts/LocalHealth.psm1") -Force
function Resolve-ProjectPath([string]$Path) {
    if (-not [IO.Path]::IsPathRooted($Path)) { $Path = Join-Path $ProjectRoot $Path }
    [IO.Path]::GetFullPath($Path)
}
$PythonExe = Join-Path $ProjectRoot ".venv/Scripts/python.exe"
if (-not (Test-Path $PythonExe)) { $PythonExe = Join-Path $ProjectRoot "python/.venv/Scripts/python.exe" }
if (-not (Test-Path $PythonExe)) { throw "Install .venv or python/.venv and python[dev] first." }
$Colab = Join-Path $ProjectRoot "training-results/colab-run-01/extracted/dusnx-router-full-01/router.pt"
$Checkpoint = if ($env:DUSNX_CHECKPOINT) { Resolve-ProjectPath $env:DUSNX_CHECKPOINT } elseif (Test-Path $Colab) { $Colab } else { Join-Path $ProjectRoot "artifacts/dusnx_smoke_v2.pt" }
if (-not (Test-Path -LiteralPath $Checkpoint -PathType Leaf)) { throw "Checkpoint missing: $Checkpoint. Original artifacts were not modified." }
$Device = if ($env:DUSNX_DEVICE) { $env:DUSNX_DEVICE } else { "auto" }
if (-not $AiDataDir) { $AiDataDir = "python/data" } # Preserve the previous native default DB location.
if (-not $GatewayDataDir) { $GatewayDataDir = "runtime/gateway-data" }
$AiDataDir = Resolve-ProjectPath $AiDataDir
$GatewayDataDir = Resolve-ProjectPath $GatewayDataDir
$AiUrl = "http://127.0.0.1:$AiPort"
$GatewayUrl = "http://127.0.0.1:$GatewayPort"
$Provider = if ($env:DUSNX_PROVIDER) { $env:DUSNX_PROVIDER } else { "ollama" }
$Model = if ($env:DUSNX_OLLAMA_MODEL) { $env:DUSNX_OLLAMA_MODEL } else { "qwen2.5:0.5b" }
$OllamaUrl = if ($env:DUSNX_OLLAMA_URL) { $env:DUSNX_OLLAMA_URL.TrimEnd('/') } else { "http://localhost:11434" }

# Inspect both ports before launching anything. Never terminate an existing service.
$AiOwner = Get-DusnxListeningProcess $AiPort
$GatewayOwner = Get-DusnxListeningProcess $GatewayPort
if ($AiOwner) {
    $h = Assert-DusnxFastApiCheckpoint -Owner $AiOwner -ExpectedCheckpoint $Checkpoint -Uri "$AiUrl/health"
    foreach ($sourceName in @('main.py','memory.py','provider.py','auth.py','llm_evaluation.py')) {
        $sha = (Get-FileHash (Join-Path $ProjectRoot "python/apps/ai_api/$sourceName") -Algorithm SHA256).Hash
        if ($h.source_hashes.$sourceName -ine $sha) { throw "Verified FastAPI PID $($AiOwner.ProcessId) has stale source $sourceName. Recheck PID and restart; no process was stopped." }
    }
    if ($h.api_contract -ne "week4-v1" -or $h.configuration.data_dir -ine $AiDataDir -or
        $h.configuration.device_requested -ne $Device -or $h.provider.provider -ne $Provider -or
        ($Provider -eq "ollama" -and ($h.provider.configured_model -ne $Model -or $h.configuration.ollama_url -ne $OllamaUrl)) -or
        $h.configuration.evaluation_enabled -ne ($env:DUSNX_ENABLE_LLM_EVAL -eq '1')) {
        throw "Verified DUSN-X FastAPI PID $($AiOwner.ProcessId) has stale code/configuration. Recheck PID and restart this DUSN-X process; no process was stopped."
    }
}
if ($GatewayOwner) {
    try { $h = Invoke-RestMethod "$GatewayUrl/health" -TimeoutSec 3 } catch { throw "Port $GatewayPort occupied by PID $($GatewayOwner.ProcessId); identity unverified. No process was stopped." }
    if ($h.service -ne "dusnx-gateway") { throw "Port $GatewayPort is not DUSN-X Gateway (PID $($GatewayOwner.ProcessId)). Choose another port; no process was stopped." }
    if ($h.api_contract -ne "week4-v1" -or $h.ai_api_url.TrimEnd('/') -ne $AiUrl) { throw "Verified DUSN-X Gateway PID $($GatewayOwner.ProcessId) has stale binary/configuration. Rebuild and restart this verified process." }
    $binary = Join-Path $ProjectRoot 'gateway-dotnet/bin/Release/net8.0/Dusnx.Gateway.dll'
    if (-not (Test-Path $binary) -or $h.binary_sha256 -ine (Get-FileHash $binary -Algorithm SHA256).Hash) { throw "Verified Gateway PID $($GatewayOwner.ProcessId) differs from current Release binary. Rebuild and restart this verified process." }
}
$LogDir = Join-Path $ProjectRoot "runtime/startup"
New-Item -ItemType Directory -Force $LogDir | Out-Null
$RunId = Get-Date -Format 'yyyyMMdd-HHmmss-fff'
if (-not $AiOwner) {
    $env:PYTHONPATH = "$ProjectRoot/python;$ProjectRoot/python/src"
    $env:DUSNX_CHECKPOINT = $Checkpoint
    $env:DUSNX_DEVICE = $Device
    $env:DUSNX_DATA_DIR = $AiDataDir
    $ai = Start-Process -FilePath $PythonExe -ArgumentList @('-m','uvicorn','apps.ai_api.main:app','--host','127.0.0.1','--port',"$AiPort") -WorkingDirectory $ProjectRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput "$LogDir/$RunId-ai.out.log" -RedirectStandardError "$LogDir/$RunId-ai.err.log"
    Write-Host "Started FastAPI PID $($ai.Id): $AiUrl (data: $AiDataDir)"
}
$AiHealth = Wait-DusnxHttpService -Name FastAPI -Uri "$AiUrl/health" -TimeoutSeconds 60 -Validate {
    param($h)
    if ($h.service -ne 'dusnx-ai-api' -or $h.api_contract -ne 'week4-v1') { throw 'Wrong service/code identity' }
    if ($h.runtime_mode -ne 'trained_dusnx' -or -not $h.checkpoint_loaded -or $h.checkpoint_path -ine $Checkpoint -or -not $h.model_version) { throw "Checkpoint not loaded: $($h.metadata.warning)" }
}
if (-not $GatewayOwner) {
    & dotnet build (Join-Path $ProjectRoot 'gateway-dotnet/Dusnx.Gateway.csproj') -c Release --nologo
    if ($LASTEXITCODE -ne 0) { throw 'Gateway build failed; inspect FastAPI PID above before restart.' }
    $env:AI_API_URL = $AiUrl
    $env:DUSNX_DATA_DIR = $GatewayDataDir
    $env:DUSNX_WEB_UI_DIR = Join-Path $ProjectRoot 'web-ui'
    $dll = Join-Path $ProjectRoot 'gateway-dotnet/bin/Release/net8.0/Dusnx.Gateway.dll'
    $gw = Start-Process dotnet -ArgumentList @('"' + $dll + '"','--urls',$GatewayUrl) -WorkingDirectory $ProjectRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput "$LogDir/$RunId-gateway.out.log" -RedirectStandardError "$LogDir/$RunId-gateway.err.log"
    Write-Host "Started Gateway PID $($gw.Id): $GatewayUrl"
}
$GatewayHealth = Wait-DusnxHttpService -Name Gateway -Uri "$GatewayUrl/health" -TimeoutSeconds 45 -Validate {
    param($h)
    if ($h.service -ne 'dusnx-gateway' -or $h.api_contract -ne 'week4-v1' -or $h.ai_api_url -ne $AiUrl) { throw 'Wrong Gateway identity/configuration' }
}
$null = Wait-DusnxHttpService -Name 'Gateway proxy' -Uri "$GatewayUrl/v1/health" -TimeoutSeconds 15 -Validate {
    param($h)
    if ($h.service -ne 'dusnx-ai-api' -or $h.checkpoint_path -ine $Checkpoint) { throw 'Wrong proxy target' }
}
$null = Wait-DusnxHttpService -Name Web -Uri $GatewayUrl -TimeoutSeconds 15 -Probe {
    param($uri) Invoke-WebRequest $uri -UseBasicParsing -TimeoutSec 3
} -Validate { param($r) if ($r.StatusCode -ne 200 -or $r.Content -notlike '*DUSN-X*') { throw 'Wrong Web content' } }
if (-not $AiHealth.provider_ok) { throw "Stack started, but provider unavailable: $($AiHealth.provider | ConvertTo-Json -Compress). Inspect the verified PIDs above; no process was stopped." }
Write-Host "Native stack verified. Router: $($AiHealth.model_version); LLM: $($AiHealth.provider.configured_model). Open $GatewayUrl"
