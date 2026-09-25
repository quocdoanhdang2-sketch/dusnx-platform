$ErrorActionPreference = "Stop"
Import-Module (Join-Path $PSScriptRoot "..\LocalHealth.psm1") -Force

$attempt = 0
$result = Wait-DusnxHttpService -Name "eventual" -Uri "http://test" -TimeoutSeconds 3 -Probe {
    $script:attempt++
    if ($script:attempt -lt 3) { throw "not ready" }
    [PSCustomObject]@{ status = "ok" }
} -Validate {
    param($response)
    if ($response.status -ne "ok") { throw "bad status" }
}
if ($result.status -ne "ok" -or $attempt -ne 3) { throw "Wait helper did not retry until healthy." }

$failed = $false
try {
    Wait-DusnxHttpService -Name "never" -Uri "http://test" -TimeoutSeconds 1 -Probe { throw "still down" }
}
catch {
    $failed = $_.Exception.Message -like "never did not become healthy*still down*"
}
if (-not $failed) { throw "Wait helper reported success or lost the useful timeout error." }
Write-Host "Local startup health tests passed (2/2)."
