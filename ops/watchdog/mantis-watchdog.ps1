<#
.SYNOPSIS
    MANTIS backend external watchdog.

.DESCRIPTION
    Probes the local FastAPI backend on /health every time it runs (intended
    cadence: Task Scheduler at 2-minute intervals). On three consecutive
    probe failures the watchdog kills the running uvicorn process and
    relaunches it with the same command MANTIS docs document.

    The in-process BackendHealthSentinel (src/monitoring/health_sentinel.py)
    handles "soft hangs" detected from inside the FastAPI process. This
    script is the second layer: when the Python process itself stops
    responding (deadlock, GIL stuck on blocking C call, OOM, ...) the
    sentinel cannot reach the network, so an external supervisor is the
    only safety net.

    Restart policy is conservative on purpose — three consecutive failures
    (6 minutes at the default cadence) mean the in-process sentinel had
    time to alert AND the soft-hang did not resolve. A faster threshold
    would risk flap-restarts on normal slow shutdowns / restarts.

.PARAMETER ProjectRoot
    Absolute path to the AlgoTrader repo. Defaults to the parent of the
    folder this script lives in (so `ops/watchdog/` infers the repo root).

.PARAMETER HealthUrl
    URL the watchdog probes. Defaults to http://127.0.0.1:8000/health.

.PARAMETER FailureThreshold
    Number of consecutive failures before triggering a restart. Default 3.

.PARAMETER ProbeTimeoutSec
    HTTP timeout for the health probe. Default 10s.

.EXAMPLE
    pwsh -ExecutionPolicy Bypass -File mantis-watchdog.ps1

.EXAMPLE
    pwsh -ExecutionPolicy Bypass -File mantis-watchdog.ps1 -HealthUrl http://10.0.0.5:8000/health
#>
[CmdletBinding()]
param(
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..\')).Path,
    [string]$HealthUrl = 'http://127.0.0.1:8000/health',
    [int]$FailureThreshold = 3,
    [int]$ProbeTimeoutSec = 10
)

$ErrorActionPreference = 'Stop'

# ─── Paths ──────────────────────────────────────────────────────────────
$projectRoot = (Resolve-Path $ProjectRoot).Path
$backendDir  = Join-Path $projectRoot 'backend'
$venvPython  = Join-Path $backendDir '.venv\Scripts\python.exe'
$logsDir     = Join-Path $projectRoot 'logs\watchdog'
$logFile     = Join-Path $logsDir   'watchdog.log'
$stateFile   = Join-Path $logsDir   'watchdog-state.json'

if (-not (Test-Path $logsDir)) { New-Item -ItemType Directory -Path $logsDir -Force | Out-Null }
if (-not (Test-Path $venvPython)) {
    throw "Backend venv python not found at $venvPython — install dependencies before running the watchdog."
}

# ─── Logging helper ─────────────────────────────────────────────────────
function Write-WatchdogLog {
    param([string]$Level, [string]$Message)
    $ts = (Get-Date).ToString('yyyy-MM-ddTHH:mm:ss.fffzzz')
    $line = "[$ts] [$Level] $Message"
    Add-Content -Path $logFile -Value $line -Encoding UTF8
    Write-Host $line
}

# ─── Persistent state (consecutive failure counter) ─────────────────────
function Read-State {
    if (Test-Path $stateFile) {
        try {
            return Get-Content $stateFile -Raw | ConvertFrom-Json
        } catch {
            Write-WatchdogLog 'WARN' "Failed to parse $stateFile — resetting state."
        }
    }
    return [pscustomobject]@{
        consecutive_failures = 0
        last_probe_at        = $null
        last_restart_at      = $null
        restart_count        = 0
    }
}

function Write-State {
    param([pscustomobject]$State)
    $State | ConvertTo-Json -Depth 4 | Set-Content -Path $stateFile -Encoding UTF8
}

# ─── Health probe ───────────────────────────────────────────────────────
function Test-BackendHealth {
    try {
        $resp = Invoke-WebRequest -Uri $HealthUrl -Method GET -TimeoutSec $ProbeTimeoutSec -UseBasicParsing
        if ($resp.StatusCode -ne 200) {
            return @{ ok = $false; reason = "HTTP $($resp.StatusCode)" }
        }
        $payload = $resp.Content | ConvertFrom-Json
        if ($payload.success -ne $true) {
            return @{ ok = $false; reason = "success=false (status=$($payload.data.status))" }
        }
        return @{ ok = $true; reason = "status=$($payload.data.status)" }
    } catch [System.Net.WebException] {
        return @{ ok = $false; reason = "WebException: $($_.Exception.Message)" }
    } catch {
        return @{ ok = $false; reason = "Probe error: $($_.Exception.Message)" }
    }
}

# ─── Restart action ─────────────────────────────────────────────────────
function Stop-RunningBackend {
    # Find every python.exe whose command line invokes uvicorn AND lives
    # inside this project's venv. Filtering by venv path keeps the script
    # safe on machines that run multiple uvicorn services.
    $venvParent = (Split-Path $venvPython -Parent).ToLowerInvariant()
    $procs = Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" |
        Where-Object { $_.CommandLine -and $_.CommandLine.ToLowerInvariant().Contains($venvParent) -and $_.CommandLine -match 'uvicorn' }

    foreach ($proc in $procs) {
        Write-WatchdogLog 'WARN' "Killing stale backend PID=$($proc.ProcessId) cmd=$($proc.CommandLine)"
        try {
            Stop-Process -Id $proc.ProcessId -Force -ErrorAction Stop
        } catch {
            Write-WatchdogLog 'ERROR' "Stop-Process PID=$($proc.ProcessId) failed: $($_.Exception.Message)"
        }
    }
    Start-Sleep -Seconds 2
}

function Start-Backend {
    $args = @('-m', 'uvicorn', 'src.api.main:app', '--host', '0.0.0.0', '--port', '8000')
    Write-WatchdogLog 'INFO' "Launching backend: $venvPython $($args -join ' ') (cwd=$backendDir)"
    # Detached process so the watchdog scheduled task can exit immediately.
    Start-Process -FilePath $venvPython -ArgumentList $args -WorkingDirectory $backendDir -WindowStyle Hidden | Out-Null
}

function Invoke-BackendRestart {
    Stop-RunningBackend
    Start-Backend
}

# ─── Main loop (single tick) ────────────────────────────────────────────
$state = Read-State
$state.last_probe_at = (Get-Date).ToString('yyyy-MM-ddTHH:mm:ss.fffzzz')

$result = Test-BackendHealth

if ($result.ok) {
    if ($state.consecutive_failures -gt 0) {
        Write-WatchdogLog 'INFO' "Backend recovered after $($state.consecutive_failures) failure(s) — $($result.reason)"
    } else {
        Write-WatchdogLog 'DEBUG' "Healthy — $($result.reason)"
    }
    $state.consecutive_failures = 0
    Write-State $state
    exit 0
}

# Failure path
$state.consecutive_failures = [int]$state.consecutive_failures + 1
Write-WatchdogLog 'WARN' "Probe failed ($($state.consecutive_failures)/$FailureThreshold) — $($result.reason)"

if ($state.consecutive_failures -ge $FailureThreshold) {
    Write-WatchdogLog 'CRITICAL' "Threshold reached — restarting backend."
    try {
        Invoke-BackendRestart
        $state.last_restart_at = (Get-Date).ToString('yyyy-MM-ddTHH:mm:ss.fffzzz')
        $state.restart_count   = [int]$state.restart_count + 1
        $state.consecutive_failures = 0
        Write-WatchdogLog 'INFO' "Restart kicked off (total restarts: $($state.restart_count))."
    } catch {
        Write-WatchdogLog 'ERROR' "Restart failed: $($_.Exception.Message)"
    }
}

Write-State $state
