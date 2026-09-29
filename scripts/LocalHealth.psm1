function Wait-DusnxHttpService {
    param(
        [Parameter(Mandatory)][string]$Name,
        [Parameter(Mandatory)][string]$Uri,
        [int]$TimeoutSeconds = 45,
        [scriptblock]$Validate,
        [scriptblock]$Probe
    )
    $deadline = [DateTimeOffset]::UtcNow.AddSeconds($TimeoutSeconds)
    $lastError = "No response received."
    do {
        try {
            $response = if ($Probe) { & $Probe $Uri } else { Invoke-RestMethod -Uri $Uri -TimeoutSec 10 }
            if ($Validate) { & $Validate $response }
            return $response
        }
        catch {
            $lastError = $_.Exception.Message
            if ([DateTimeOffset]::UtcNow -lt $deadline) { Start-Sleep -Milliseconds 500 }
        }
    } while ([DateTimeOffset]::UtcNow -lt $deadline)
    throw "$Name did not become healthy at $Uri within $TimeoutSeconds seconds. Last error: $lastError"
}

function Get-DusnxListeningProcess {
    param([Parameter(Mandatory)][int]$Port)
    $connection = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($null -eq $connection) {
        $client = [System.Net.Sockets.TcpClient]::new()
        try {
            $task = $client.ConnectAsync("127.0.0.1", $Port)
            if (-not $task.Wait(500) -or -not $client.Connected) { return $null }
            return [PSCustomObject]@{ Port = $Port; ProcessId = $null; ProcessName = "unknown (PID lookup unavailable)" }
        }
        catch { return $null }
        finally { $client.Dispose() }
    }
    $process = Get-Process -Id $connection.OwningProcess -ErrorAction SilentlyContinue
    [PSCustomObject]@{
        Port = $Port
        ProcessId = $connection.OwningProcess
        ProcessName = if ($process) { $process.ProcessName } else { "unknown" }
    }
}

function Assert-DusnxFastApiCheckpoint {
    param(
        [Parameter(Mandatory)][PSCustomObject]$Owner,
        [Parameter(Mandatory)][string]$ExpectedCheckpoint,
        [string]$Uri = "http://127.0.0.1:8000/health",
        [scriptblock]$Probe
    )
    $expectedNorm = [System.IO.Path]::GetFullPath($ExpectedCheckpoint)
    $health = try {
        if ($Probe) { & $Probe $Uri } else { Invoke-RestMethod -Uri $Uri -TimeoutSec 3 }
    }
    catch {
        return $null
    }

    $isDusnx = ($health -and ($health.runtime_mode -or $health.status -eq "ok" -or $health.checkpoint -or $health.checkpoint_path))
    if (-not $isDusnx) {
        return $null
    }

    $loadedPath = if ($health.checkpoint_path) {
        try { [System.IO.Path]::GetFullPath($health.checkpoint_path) } catch { [string]$health.checkpoint_path }
    } elseif ($health.checkpoint) {
        try { [System.IO.Path]::GetFullPath($health.checkpoint) } catch { [string]$health.checkpoint }
    } else {
        $null
    }

    $isMatch = ($health.checkpoint_loaded -eq $true -and $loadedPath -and ($loadedPath -ieq $expectedNorm))
    if (-not $isMatch) {
        $loadedDisplay = if ($loadedPath) {
            if ($health.checkpoint_loaded -eq $true) { $loadedPath } else { "$loadedPath (checkpoint_loaded=false, mode=$($health.runtime_mode))" }
        } else {
            "<none / not loaded, mode=$($health.runtime_mode)>"
        }
        $pidInfo = if ($Owner.ProcessId) { "PID $($Owner.ProcessId)" } else { "PID unknown" }
        $procInfo = if ($Owner.ProcessName) { "$($Owner.ProcessName)" } else { "unknown" }
        $stopCmd = if ($Owner.ProcessId) { "Stop-Process -Id $($Owner.ProcessId) -Force" } else { "Stop-Process -Name python -Force" }

        $msg = "Port 8000 is already running FastAPI ($pidInfo, $procInfo) with a different checkpoint:`n" +
               "  Loaded checkpoint:    $loadedDisplay`n" +
               "  Requested checkpoint: $expectedNorm`n" +
               "To restart with the requested checkpoint, stop the existing process:`n" +
               "  $stopCmd`n" +
               "then rerun .\start-local.ps1"
        throw $msg
    }

    return $health
}

Export-ModuleMember -Function Wait-DusnxHttpService, Get-DusnxListeningProcess, Assert-DusnxFastApiCheckpoint
