param(
    [int]$AiPort = $(if ($env:DUSNX_AI_PORT) { [int]$env:DUSNX_AI_PORT } else { 8000 }),
    [int]$GatewayPort = $(if ($env:DUSNX_GATEWAY_PORT) { [int]$env:DUSNX_GATEWAY_PORT } else { 8080 })
)
$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path $PSScriptRoot -Parent
Import-Module (Join-Path $PSScriptRoot 'LocalHealth.psm1') -Force
$verified = @()
foreach ($item in @(@{Port=$GatewayPort;Service='dusnx-gateway'}, @{Port=$AiPort;Service='dusnx-ai-api'})) {
    $owner = Get-DusnxListeningProcess $item.Port
    if (-not $owner) { continue }
    if (-not $owner.ProcessId) { throw "Cannot verify PID for port $($item.Port); nothing stopped." }
    $health = Invoke-RestMethod "http://127.0.0.1:$($item.Port)/health" -TimeoutSec 5
    $process = Get-CimInstance Win32_Process -Filter "ProcessId=$($owner.ProcessId)"
    $belongsToRepo = $process.CommandLine -like "*$ProjectRoot*"
    # Windows venv python.exe may launch a base interpreter child which owns the
    # socket. Require its still-live, repository-scoped uvicorn launcher as well.
    if (-not $belongsToRepo -and $process.CommandLine -match 'uvicorn apps.ai_api.main:app') {
        $parent = Get-CimInstance Win32_Process -Filter "ProcessId=$($process.ParentProcessId)"
        $belongsToRepo = $parent -and $parent.CreationDate -le $process.CreationDate -and
            $parent.CommandLine -like "*$ProjectRoot*" -and $parent.CommandLine -match 'uvicorn apps.ai_api.main:app'
    }
    if ($health.service -ne $item.Service -or -not $belongsToRepo -or
        $process.CommandLine -notmatch 'uvicorn apps.ai_api.main:app|Dusnx.Gateway.dll|Dusnx.Gateway.exe') {
        throw "Unverified process at port $($item.Port), PID $($owner.ProcessId); nothing stopped."
    }
    $verified += [PSCustomObject]@{Id=$owner.ProcessId;Created=$process.CreationDate;Port=$item.Port}
}
foreach ($item in $verified) {
    $process = Get-CimInstance Win32_Process -Filter "ProcessId=$($item.Id)"
    if (-not $process -or $process.CreationDate -ne $item.Created) { throw "PID changed; stop aborted." }
    Stop-Process -Id $item.Id
    Write-Host "Stopped verified DUSN-X PID $($item.Id) at port $($item.Port)."
}
