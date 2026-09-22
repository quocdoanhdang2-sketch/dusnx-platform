$ErrorActionPreference = "Stop"

$gateway = "http://localhost:8080"

Write-Host "[1/4] Gateway health"
Invoke-RestMethod "$gateway/health" | ConvertTo-Json -Depth 10

Write-Host "[2/4] Send cross-platform event"
$eventBody = @{
    platform = "web"
    platformUserId = "web-user-001"
    linkedUserId = "global-demo-001"
    content = "Phân tích AI Agent cho dự án DUSN-X"
    eventType = "research.started"
    feedbackValue = 0.5
} | ConvertTo-Json

Invoke-RestMethod "$gateway/api/v1/events" `
    -Method Post `
    -ContentType "application/json" `
    -Body $eventBody | ConvertTo-Json -Depth 20

Write-Host "[3/4] Create presentation job"
$jobBody = @{
    platformUserId = "ppt-user-001"
    linkedUserId = "global-demo-001"
    prompt = "Tạo slide về kiến trúc DUSN-X"
    slideCount = 5
} | ConvertTo-Json

$job = Invoke-RestMethod "$gateway/api/v1/presentations/generations" `
    -Method Post `
    -ContentType "application/json" `
    -Body $jobBody
$job | ConvertTo-Json -Depth 20

Write-Host "[4/4] Poll job"
do {
    Start-Sleep -Milliseconds 700
    $status = Invoke-RestMethod "$gateway/api/v1/jobs/$($job.jobId)"
    Write-Host "$($status.status) - $($status.progress)% - $($status.currentStep)"
} while ($status.status -notin @("completed", "failed"))

$status | ConvertTo-Json -Depth 30
