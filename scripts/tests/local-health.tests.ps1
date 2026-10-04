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

# Test 3: Checkpoint mismatch throws immediately with PID, process name, and restart instructions
$mismatchThrown = $false
$mismatchError = ""
$mockOwner = [PSCustomObject]@{
    Port = 8000
    ProcessId = 12345
    ProcessName = "python"
}
$expectedCp = "D:\Projects\dusnx-platform\training-results\colab-run-01\extracted\dusnx-router-full-01\router.pt"
$runningCp = "D:\Projects\dusnx-platform\artifacts\dusnx_smoke_v2.pt"

try {
    Assert-DusnxFastApiCheckpoint -Owner $mockOwner -ExpectedCheckpoint $expectedCp -Probe {
        [PSCustomObject]@{
            service = "dusnx-ai-api"
            status = "ok"
            runtime_mode = "trained_dusnx"
            checkpoint_loaded = $true
            checkpoint_path = $runningCp
            model_version = "checkpoint:smoke:v2"
        }
    }
}
catch {
    $mismatchThrown = $true
    $mismatchError = $_.Exception.Message
}

if (-not $mismatchThrown) { throw "Assert-DusnxFastApiCheckpoint should have thrown on checkpoint mismatch." }
if ($mismatchError -notlike "*PID 12345*") { throw "Mismatch error missing PID: $mismatchError" }
if ($mismatchError -notlike "*python*") { throw "Mismatch error missing ProcessName: $mismatchError" }
if ($mismatchError -notlike "*$runningCp*") { throw "Mismatch error missing loaded checkpoint path: $mismatchError" }
if ($mismatchError -notlike "*$expectedCp*") { throw "Mismatch error missing requested checkpoint path: $mismatchError" }
if ($mismatchError -notlike "*Stop-Process -Id 12345*") { throw "Mismatch error missing restart command: $mismatchError" }

# Test 4: Matching checkpoint passes and returns health
$matchResult = Assert-DusnxFastApiCheckpoint -Owner $mockOwner -ExpectedCheckpoint $expectedCp -Probe {
    [PSCustomObject]@{
        service = "dusnx-ai-api"
        status = "ok"
        runtime_mode = "trained_dusnx"
        checkpoint_loaded = $true
        checkpoint_path = $expectedCp
        model_version = "checkpoint:colab:v1"
    }
}
if ($null -eq $matchResult -or $matchResult.model_version -ne "checkpoint:colab:v1") {
    throw "Assert-DusnxFastApiCheckpoint should have returned health on matching checkpoint."
}

# Test 5: Checkpoint loaded=false throws informative mismatch
$unloadedThrown = $false
try {
    Assert-DusnxFastApiCheckpoint -Owner $mockOwner -ExpectedCheckpoint $expectedCp -Probe {
        [PSCustomObject]@{
            service = "dusnx-ai-api"
            status = "ok"
            runtime_mode = "bootstrap_rules"
            checkpoint_loaded = $false
            checkpoint_path = $null
            model_version = "bootstrap_rules"
        }
    }
}
catch {
    $unloadedThrown = $_.Exception.Message -like "*Stop-Process -Id 12345*"
}
if (-not $unloadedThrown) { throw "Assert-DusnxFastApiCheckpoint should fail if checkpoint_loaded is false." }

# Test 6: Unverified occupied ports must fail without suggesting a kill command.
foreach ($probe in @({ throw "connection refused" }, { [PSCustomObject]@{ status = 'ok'; service = 'wordpress' } })) {
    $failed = $false
    try { Assert-DusnxFastApiCheckpoint -Owner $mockOwner -ExpectedCheckpoint $expectedCp -Probe $probe }
    catch { $failed = $_.Exception.Message -like '*No process was stopped*' -and $_.Exception.Message -notlike '*Stop-Process*' }
    if (-not $failed) { throw 'Unverified port accepted or unsafe stop suggested.' }
}
Write-Host "Local startup health tests passed (6/6)."
