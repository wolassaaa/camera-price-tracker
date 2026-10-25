param(
    [string]$TaskName = "CameraPriceTrackerWorker",
    [string]$PythonExe = ""
)

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if ([string]::IsNullOrWhiteSpace($PythonExe)) {
    $PythonExe = if (Test-Path -LiteralPath $VenvPython) { $VenvPython } else { "python" }
}
$Action = New-ScheduledTaskAction -Execute $PythonExe -Argument "-m camera_tracker.worker" -WorkingDirectory $ProjectRoot
$Trigger = New-ScheduledTaskTrigger -AtLogOn
$Settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Days 3650) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 5)

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Description "Local Camera Price Tracker collection worker" -Force
Write-Host "Registered $TaskName using $PythonExe. Start it now with: Start-ScheduledTask -TaskName $TaskName"
