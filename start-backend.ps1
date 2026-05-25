# start-backend.ps1 — durable launch for MANTIS backend (uvicorn).
#
# Fixes recurring hard-crash:
#   forrtl: error (200): program aborting due to window-CLOSE event
#   Fatal Python error: PyEval_SaveThread ... the GIL is released
#
# Cause: Intel Fortran runtime (bundled in numpy/scipy/MKL) registers a Windows
# console-ctrl handler that abort()s the process when its console window receives
# a CLOSE/Ctrl event (terminal closed, session detach, parent shell exit).
#
# Two-part fix:
#   1. FOR_DISABLE_CONSOLE_CTRL_HANDLER=1  -> RTL never installs the abort handler.
#      MUST be set in the process env BEFORE python starts (pydantic-settings .env
#      does NOT reach os.environ, so .env can't carry this var).
#   2. Detached launch (Start-Process, hidden window) -> closing the launching
#      terminal no longer propagates a console-CLOSE to the backend.
#
# Usage:  pwsh -File .\start-backend.ps1        (from repo root)

$ErrorActionPreference = "Stop"
$root    = $PSScriptRoot
$backend = Join-Path $root "backend"
$python  = Join-Path $backend ".venv\Scripts\python.exe"
$ts      = Get-Date -Format "yyyyMMdd_HHmmss"
$log     = Join-Path $backend "logs\backend_restart_$ts.log"
$err     = Join-Path $backend "logs\backend_restart_$ts.err.log"

# Refuse to double-bind port 8000.
$listen = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
if ($listen) {
    Write-Host "Backend already LISTENING on 8000 (PID $($listen.OwningProcess)). Abort." -ForegroundColor Yellow
    exit 1
}

# Part 1: neutralize the Fortran console-ctrl handler for the child process.
$env:FOR_DISABLE_CONSOLE_CTRL_HANDLER = "1"

# Part 2: launch detached, hidden, logs redirected.
$p = Start-Process -FilePath $python `
    -ArgumentList "-X","faulthandler","-m","uvicorn","src.api.main:app","--host","0.0.0.0","--port","8000" `
    -WorkingDirectory $backend `
    -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput $log -RedirectStandardError $err

Write-Host "Backend started detached. PID $($p.Id)" -ForegroundColor Green
Write-Host "  log: $log"
Write-Host "  err: $err"

# Poll until it binds + answers.
$deadline = (Get-Date).AddSeconds(75)
while ((Get-Date) -lt $deadline) {
    if (Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue) {
        try {
            $r = Invoke-WebRequest -Uri "http://127.0.0.1:8000/api/trading/status" -UseBasicParsing -TimeoutSec 5
            Write-Host "Backend UP — HTTP $($r.StatusCode)" -ForegroundColor Green
            exit 0
        } catch { }
    }
    Start-Sleep -Seconds 5
}
Write-Host "Backend did NOT come up within 75s — check $err" -ForegroundColor Red
exit 1
