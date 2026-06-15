# run_vix_gate_track.ps1 - daily VIX-gate forward paper-track step (mark + open).
#
# NO capital, NO broker. Free yfinance data (^VIX/^VIX3M/^GSPC). Idempotent per date:
# safe to re-run; skips weekends/holidays automatically (no new US session bar => same
# asof => 'open' skips, 'mark' holds). 'mark' realizes the prior frozen decision once its
# D+1 close is cached; 'open' freezes the latest completed US session's gate decision.
#
# Registered as Windows Scheduled Task 'MANTIS_VixGateTrack' (daily 08:30, StartWhenAvailable
# so a run missed while the PC was off fires at next availability).
# Manual run:  powershell -NoProfile -ExecutionPolicy Bypass -File backend\scripts\ab\run_vix_gate_track.ps1

$ErrorActionPreference = 'Stop'

$backend = 'D:\Develop\AI\_ClaudeCode\AlgoTrader\backend'
$py = Join-Path $backend '.venv\Scripts\python.exe'
$script = 'scripts\ab\vix_gate_track.py'
$dataDir = Join-Path $backend 'data\vix_gate'
$log = Join-Path $dataDir 'track.log'

if (-not (Test-Path $dataDir)) { New-Item -ItemType Directory -Force $dataDir | Out-Null }

function Write-Log([string]$m) {
    $ts = (Get-Date).ToUniversalTime().ToString("yyyy-MM-dd'T'HH:mm:ss'Z'")
    Add-Content -Path $log -Value "$ts  $m"
}

Set-Location $backend
Write-Log 'step start (mark + open)'
foreach ($cmd in 'mark', 'open') {
    try {
        $out = (& $py $script $cmd 2>&1 | Out-String).Trim()
        Write-Log "[$cmd] $out"
    } catch {
        Write-Log "[$cmd] ERROR: $_"
    }
}
Write-Log 'step done'
