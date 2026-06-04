# start_forward_lab.ps1 - idempotent watchdog launcher for the Forward Demo Lab loop.
#
# Safe to run repeatedly (Scheduled Task: at logon + every 30 min): if the loop is
# already alive it exits immediately with no side effects. It must NEVER start a
# second loop - a double loop means double orders on 'Account test'.
#
# Registered as Windows Scheduled Task 'MANTIS_ForwardLab_Watchdog' (see repo docs).
# Manual run:  powershell -NoProfile -ExecutionPolicy Bypass -File backend\scripts\ab\start_forward_lab.ps1

$ErrorActionPreference = 'Stop'

$backend = 'D:\Develop\AI\_ClaudeCode\AlgoTrader\backend'
$dataDir = Join-Path $backend 'data\forward_lab'
$logFile = Join-Path $dataDir 'watchdog.log'

function Write-Log([string]$msg) {
    $ts = (Get-Date).ToUniversalTime().ToString("yyyy-MM-dd'T'HH:mm:ss'Z'")
    Add-Content -Path $logFile -Value "$ts  $msg"
}

if (-not (Test-Path $dataDir)) { New-Item -ItemType Directory -Force $dataDir | Out-Null }

# --- 1. Already running? (matches both venv-launcher parent and real interpreter child)
$existing = Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
    Where-Object { $_.CommandLine -match 'forward_lab\.py[''"]?\s+[''"]?run' }
if ($existing) { exit 0 }   # alive - nothing to do, stay silent

Write-Log 'loop DOWN - relaunching'

# --- 2. Rotate previous logs (Start-Process redirect truncates; keep history for autopsy)
$stamp = (Get-Date).ToString('yyyyMMdd-HHmmss')
foreach ($name in 'run.log', 'run.err.log') {
    $p = Join-Path $dataDir $name
    if (Test-Path $p) {
        Move-Item $p (Join-Path $dataDir ($name -replace '\.log$', ".$stamp.log")) -Force
    }
}
# prune rotated logs older than 14 days
Get-ChildItem $dataDir -Filter 'run*.????????-??????.log' |
    Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-14) } |
    Remove-Item -Force -Confirm:$false

# --- 3. Launch detached
$env:FOR_DISABLE_CONSOLE_CTRL_HANDLER = '1'   # Fortran RTL crash guard (forrtl error 200)
Start-Process (Join-Path $backend '.venv\Scripts\python.exe') `
    -ArgumentList 'scripts\ab\forward_lab.py', 'run' `
    -WorkingDirectory $backend `
    -RedirectStandardOutput (Join-Path $dataDir 'run.log') `
    -RedirectStandardError (Join-Path $dataDir 'run.err.log') `
    -WindowStyle Hidden

# --- 4. Verify it stuck
Start-Sleep -Seconds 8
$check = Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
    Where-Object { $_.CommandLine -match 'forward_lab\.py[''"]?\s+[''"]?run' }
if ($check) {
    $pids = ($check | Select-Object -ExpandProperty ProcessId) -join ','
    Write-Log "relaunch OK pid=$pids"
} else {
    Write-Log 'relaunch FAILED - no process after 8s (check run.err.log)'
}
