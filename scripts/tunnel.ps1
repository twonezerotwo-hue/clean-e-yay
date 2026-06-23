# localtunnel watchdog — loca.lt kararsız; süreç düşerse otomatik yeniden başlatır.
# Sabit subdomain: https://eyaybrain.loca.lt
$ErrorActionPreference = "SilentlyContinue"
$npx  = "C:\Program Files\nodejs\npx.cmd"
$root = "C:\Users\twone\Desktop\Clean E-yAy"
$logs = Join-Path $root "logs"
New-Item -ItemType Directory -Force -Path $logs | Out-Null

while ($true) {
    "[$(Get-Date -Format o)] tunnel start" | Out-File -Append "$logs\tunnel.run.log"
    & $npx --yes localtunnel --port 4000 --subdomain eyaybrain *>> "$logs\tunnel.run.log"
    "[$(Get-Date -Format o)] tunnel exited, 5s sonra yeniden..." | Out-File -Append "$logs\tunnel.run.log"
    Start-Sleep -Seconds 5
}
