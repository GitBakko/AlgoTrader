<#
.SYNOPSIS
    Registers the MANTIS watchdog as a Windows Scheduled Task.

.DESCRIPTION
    Creates a recurring task `MantisWatchdog` that runs
    `mantis-watchdog.ps1` every $IntervalMinutes minutes (default 2).
    The task runs whether the user is logged on or not, with the highest
    available privileges, so a backend hang detected at 3 a.m. still gets
    restarted.

    Run this script once on the host machine. Subsequent edits to the
    underlying watchdog .ps1 are picked up automatically — only the
    schedule is registered with Windows.

.PARAMETER IntervalMinutes
    How often the task runs. Default 2.

.PARAMETER TaskName
    Name registered with Task Scheduler. Default `MantisWatchdog`.

.PARAMETER User
    Account the task runs as. Default the current user.

.EXAMPLE
    pwsh -ExecutionPolicy Bypass -File install-watchdog.ps1

.EXAMPLE
    pwsh -ExecutionPolicy Bypass -File install-watchdog.ps1 -IntervalMinutes 5
#>
[CmdletBinding()]
param(
    [int]$IntervalMinutes = 2,
    [string]$TaskName = 'MantisWatchdog',
    [string]$User = "$env:USERDOMAIN\$env:USERNAME"
)

$ErrorActionPreference = 'Stop'

$watchdogScript = (Resolve-Path (Join-Path $PSScriptRoot 'mantis-watchdog.ps1')).Path
$pwshPath       = (Get-Command pwsh -ErrorAction SilentlyContinue)?.Source
if (-not $pwshPath) { $pwshPath = (Get-Command powershell -ErrorAction Stop).Source }

Write-Host "Registering scheduled task '$TaskName' (interval: ${IntervalMinutes}m, runs as $User)"

# Best-effort cleanup if the task already exists.
try {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction Stop
    Write-Host "Removed previous '$TaskName' registration."
} catch {
    # Not registered yet — ignore.
}

$action = New-ScheduledTaskAction -Execute $pwshPath `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$watchdogScript`""

$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) `
    -RepetitionInterval (New-TimeSpan -Minutes $IntervalMinutes)

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 5) `
    -MultipleInstances IgnoreNew

$principal = New-ScheduledTaskPrincipal -UserId $User -LogonType S4U -RunLevel Highest

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal | Out-Null

Write-Host "OK — task '$TaskName' registered."
Write-Host "Logs:  logs/watchdog/watchdog.log"
Write-Host "State: logs/watchdog/watchdog-state.json"
Write-Host ""
Write-Host "Inspect:   Get-ScheduledTask -TaskName $TaskName"
Write-Host "Run now:   Start-ScheduledTask -TaskName $TaskName"
Write-Host "Remove:    pwsh -File uninstall-watchdog.ps1"
