# Dashboard KEEPER — sürekli izler, düşen bileşeni (API/web/ngrok) otomatik
# yeniden başlatır. start-dashboard.ps1 idempotent + self-healing olduğundan
# her döngüde onu çağırmak yeterli: sağlıklıysa atlar, ölüyse (zombi dahil)
# temizleyip başlatır. Bu sayede deploy/test için API öldürülse bile dashboard
# ~20s içinde kendiliğinden geri gelir — "sürekli kapanıyor" sorununu bitirir.
$ErrorActionPreference = "SilentlyContinue"
$root = "C:\Users\twone\Desktop\Clean E-yAy"
$script = Join-Path $root "scripts\start-dashboard.ps1"
$logs = Join-Path $root "logs"
New-Item -ItemType Directory -Force -Path $logs | Out-Null

while ($true) {
    try {
        & powershell -NoProfile -ExecutionPolicy Bypass -File $script *>> "$logs\keeper.log"
        "[$(Get-Date -Format o)] keeper tick OK" | Out-File -Append "$logs\keeper.log"
    } catch {
        "[$(Get-Date -Format o)] keeper hata: $($_.Exception.Message)" | Out-File -Append "$logs\keeper.log"
    }
    Start-Sleep -Seconds 20
}
