<#
.SYNOPSIS
    Unregisters the MANTIS watchdog scheduled task.

.PARAMETER TaskName
    Name registered with Task Scheduler. Default `MantisWatchdog`.
#>
[CmdletBinding()]
param(
    [string]$TaskName = 'MantisWatchdog'
)

$ErrorActionPreference = 'Stop'

try {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction Stop
    Write-Host "Removed scheduled task '$TaskName'."
} catch {
    Write-Warning "Task '$TaskName' was not registered (or removal failed): $($_.Exception.Message)"
}
