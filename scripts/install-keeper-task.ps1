# Tek seferlik kurulum: Başlangıç klasöründeki VBS'i, daha güvenilir bir
# Görev Zamanlayıcı görevine taşır. NORMAL bir PowerShell penceresinde
# (admin gerekmez) elle çalıştır — sandboxed araçlardan çalıştırılamaz.
$ErrorActionPreference = "Stop"

$scriptPath = "C:\Users\twone\Desktop\Clean E-yAy\scripts\keep-alive.ps1"
$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$scriptPath`""

$triggerLogon = New-ScheduledTaskTrigger -AtLogOn
$triggerBoot = New-ScheduledTaskTrigger -AtStartup

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RestartCount 999 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit (New-TimeSpan -Seconds 0) `
    -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName "EyAyDashboardKeeper" `
    -Action $action `
    -Trigger @($triggerLogon, $triggerBoot) `
    -Settings $settings `
    -Description "Clean E-yAy dashboard keep-alive loop (API/web/ngrok self-healing). Startup klasoru VBS'inin yerini alir." `
    -Force

Write-Host "Görev oluşturuldu. Eski Başlangıç VBS'ini siliyorum (çift keeper döngüsü olmasın)..."
$vbs = "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup\EyAyDashboard.vbs"
if (Test-Path $vbs) {
    Remove-Item $vbs -Force
    Write-Host "Silindi: $vbs"
}

Write-Host "Görevi şimdi test amaçlı çalıştırıyorum..."
Start-ScheduledTask -TaskName "EyAyDashboardKeeper"
Start-Sleep -Seconds 5
Get-ScheduledTask -TaskName "EyAyDashboardKeeper" | Get-ScheduledTaskInfo
