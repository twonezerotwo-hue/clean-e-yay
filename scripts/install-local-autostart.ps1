# OPTIONAL upgrade: move local autostart from the Startup-folder VBS to a
# Task Scheduler task (more reliable, restarts on failure). ASCII only.
#
# Run this in a NORMAL PowerShell window (admin NOT required for -AtLogOn).
# It CANNOT be run from sandboxed tooling (Register-ScheduledTask -> Access
# Denied there). The Startup VBS already provides working autostart; this just
# upgrades the mechanism. Idempotent.
$ErrorActionPreference = "Stop"

$taskName   = "CleanEyayLocalAutostart"
$scriptPath = Join-Path (Split-Path -Parent $PSScriptRoot) "scripts\local-autostart.ps1"
if (-not (Test-Path $scriptPath)) { throw "local-autostart.ps1 bulunamadi: $scriptPath" }

if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
    Write-Host "Eski gorev kaldirildi (yeniden kaydedilecek)."
}

$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$scriptPath`""
$trigger = New-ScheduledTaskTrigger -AtLogOn
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable `
    -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit (New-TimeSpan -Seconds 0) `
    -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings `
    -Description "Clean E-yAy local stack keeper (API 9000 + workers + web 4000). Local only - no public tunnel." `
    -Force | Out-Null

# Owner note pattern: Register can fail non-terminating -> verify BEFORE removing VBS.
if (-not (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue)) {
    throw "Gorev kaydedilemedi - Startup VBS'ine DOKUNULMADI (yedek mekanizma duruyor)."
}
Write-Host "Gorev '$taskName' kaydedildi (AtLogOn)."

# Remove the Startup VBS so two keepers do not both run (mutex would stop the
# second, but keep it clean). The task now owns autostart.
$vbs = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Startup\CleanEyayLocalAutostart.vbs"
if (Test-Path $vbs) { Remove-Item $vbs -Force; Write-Host "Startup VBS kaldirildi: $vbs" }

Write-Host "Gorevi simdi test amacli baslatiyorum..."
Start-ScheduledTask -TaskName $taskName
Start-Sleep -Seconds 3
Get-ScheduledTask -TaskName $taskName | Get-ScheduledTaskInfo
