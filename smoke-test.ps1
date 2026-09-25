param(
    [string]$Gateway = "http://127.0.0.1:8080",
    [string]$AiApi = "http://127.0.0.1:8000",
    [string]$WebUi = "http://127.0.0.1:3000"
)
$ErrorActionPreference = "Stop"

$runId = [Guid]::NewGuid().ToString("N")
$linkedKey = "dusnx-smoke-$runId"
$prefix = "[$runId]"

Write-Host "[1/5] Verify service health"
$aiHealth = Invoke-RestMethod "$AiApi/health"
if ($aiHealth.runtime_mode -ne "trained_dusnx" -or [string]::IsNullOrWhiteSpace($aiHealth.model_version)) {
    throw "FastAPI is not serving a trained checkpoint with model_version."
}
$gatewayHealth = Invoke-RestMethod "$Gateway/health"
if ($gatewayHealth.status -ne "ok") { throw "Gateway health is not ok." }
$web = Invoke-WebRequest $WebUi -UseBasicParsing
if ($web.StatusCode -ne 200 -or $web.Content -notlike "*DUSN-X Cross-Platform Demo*") { throw "Web UI is not ready." }

Write-Host "[2/5] Send Web -> Zalo -> PowerPoint events for unique test identity"
$events = @(
    @{ platform = "web"; platformUserId = "smoke-web-$runId"; content = "$prefix research routing demo" },
    @{ platform = "zalo"; platformUserId = "smoke-zalo-$runId"; content = "$prefix clarify the previous result" },
    @{ platform = "powerpoint"; platformUserId = "smoke-ppt-$runId"; content = "$prefix create one slide from the previous result" }
)
$responses = foreach ($event in $events) {
    $body = $event + @{
        linkedUserId = $linkedKey
        eventType = "smoke_test.message"
        feedbackValue = 0.0
    }
    Invoke-RestMethod "$Gateway/api/v1/events" -Method Post -ContentType "application/json" -Body ($body | ConvertTo-Json)
}

Write-Host "[3/5] Verify identity and causal state continuity"
$globalIds = @($responses | ForEach-Object global_user_id | Select-Object -Unique)
if ($globalIds.Count -ne 1) { throw "Cross-platform requests did not resolve to one global identity." }
$versions = @($responses | ForEach-Object { [long]$_.state_snapshot.state_version })
if (-not ($versions[1] -eq $versions[0] + 1 -and $versions[2] -eq $versions[1] + 1)) {
    throw "State versions are not consecutive: $($versions -join ', ')."
}
if (@($responses | Where-Object state_reset).Count -ne 0) { throw "Smoke sequence unexpectedly reset compatible state." }

Write-Host "[4/5] Read timeline and verify stable newest-first order"
$historyUrl = "$Gateway/api/v1/history/web/$($events[0].platformUserId)?linkedUserId=$linkedKey&limit=10"
$history = Invoke-RestMethod $historyUrl
$ours = @($history.items | Where-Object { $_.content -and $_.content.StartsWith($prefix, [StringComparison]::Ordinal) })
if ($ours.Count -ne 3) { throw "Expected 3 events from this run in timeline, found $($ours.Count)." }
$expectedPlatforms = @("powerpoint", "zalo", "web")
if (($ours.platform -join ",") -ne ($expectedPlatforms -join ",")) {
    throw "Timeline order/platform mismatch: $($ours.platform -join ',')."
}
if (($ours.state_version -join ",") -ne ((@($versions[2], $versions[1], $versions[0])) -join ",")) {
    throw "Timeline state versions do not match responses."
}

Write-Host "[5/5] Smoke test passed"
[PSCustomObject]@{
    run_id = $runId
    linked_key = $linkedKey
    global_user_id = $globalIds[0]
    platforms_newest_first = $ours.platform
    state_versions_sent_order = $versions
    runtime_mode = $aiHealth.runtime_mode
    model_version = $aiHealth.model_version
    gateway_status = $gatewayHealth.status
    web_status = $web.StatusCode
} | ConvertTo-Json -Depth 5

Write-Host "Test records use the unique prefix $prefix in runtime/gateway-data/events.jsonl. Remove runtime/gateway-data only when no local state needs to be retained."
