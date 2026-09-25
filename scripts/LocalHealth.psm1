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
            $response = if ($Probe) { & $Probe $Uri } else { Invoke-RestMethod -Uri $Uri -TimeoutSec 3 }
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

Export-ModuleMember -Function Wait-DusnxHttpService, Get-DusnxListeningProcess
