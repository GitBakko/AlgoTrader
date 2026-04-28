# MANTIS external watchdog

Sprint C deliverable. Two layers of backend health enforcement now run side by side:

| Layer | Where | What it catches |
|---|---|---|
| In-process sentinel | `backend/src/monitoring/health_sentinel.py` (alert-only) | Soft hangs detected from inside the FastAPI process — paper-loop stall, hourly refresh dead, ping silent. |
| External watchdog | `ops/watchdog/mantis-watchdog.ps1` (this folder) | The Python process itself stops responding (deadlock, blocking C call, OOM, port already in use). Restarts via Task Scheduler. |

The external layer is necessary because the in-process sentinel cannot fire alerts when the runtime is stuck — it lives inside the same process.

## Files

| File | Role |
|---|---|
| `mantis-watchdog.ps1` | One-tick health probe + restart action. Reads/writes `logs/watchdog/watchdog-state.json` so consecutive-failure tracking survives between Task Scheduler firings. |
| `install-watchdog.ps1` | Registers the watchdog as a Windows Scheduled Task (`MantisWatchdog`, default 2-minute cadence). Runs whether the user is logged on or not, highest privileges. |
| `uninstall-watchdog.ps1` | Removes the registration. |

## Install

```powershell
cd <repo>\ops\watchdog
pwsh -ExecutionPolicy Bypass -File install-watchdog.ps1
```

Custom cadence:

```powershell
pwsh -ExecutionPolicy Bypass -File install-watchdog.ps1 -IntervalMinutes 5
```

## Behaviour

Each tick:

1. Probe `http://127.0.0.1:8000/health` (10 s timeout).
2. HTTP 200 + `success: true` → reset failure counter, exit.
3. Otherwise → bump counter in `logs/watchdog/watchdog-state.json`.
4. Counter ≥ `FailureThreshold` (default 3, ≈ 6 minutes at 2-minute cadence):
   - Locate every `python.exe` whose command line includes the project's venv **and** invokes `uvicorn`. Kill them.
   - Relaunch with the same command MANTIS docs document:
     ```powershell
     <repo>\backend\.venv\Scripts\python.exe -m uvicorn src.api.main:app --host 0.0.0.0 --port 8000
     ```
   - Counter reset to 0, restart count incremented.

The 6-minute threshold is conservative on purpose — it gives the in-process sentinel time to fire its CRITICAL alert and rules out brief slow shutdowns. A faster threshold would risk flap-restarts.

## Logs / state

```
logs/watchdog/
├── watchdog.log          ; one line per probe + every restart action
└── watchdog-state.json   ; { consecutive_failures, last_probe_at, last_restart_at, restart_count }
```

`watchdog.log` is the source of truth for "did the watchdog ever restart the backend, and when?" Search for `CRITICAL` lines.

## Verify

```powershell
# Inspect registration
Get-ScheduledTask -TaskName MantisWatchdog

# Force one tick
Start-ScheduledTask -TaskName MantisWatchdog

# Tail logs
Get-Content logs\watchdog\watchdog.log -Tail 20 -Wait
```

## Manual run (no scheduler)

```powershell
pwsh -ExecutionPolicy Bypass -File mantis-watchdog.ps1
```

## Why not Linux / systemd?

MANTIS currently runs on Windows. Porting the watchdog to Linux means swapping `Start-Process` for `systemctl restart mantis-backend` and the install step for a `systemd` unit file — the failure-counter state file works as-is. Open `ops/watchdog/mantis-watchdog.sh` if/when a Linux host appears.
