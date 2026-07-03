# Dashboard KEEPER - surekli izler, dusen bileseni (API/web/ngrok/worker'lar)
# otomatik yeniden baslatir. start-dashboard.ps1 idempotent + self-healing
# oldugundan her dongude onu cagirmak yeterli: saglikliysa atlar, oluyse
# (zombi dahil) temizleyip baslatir.
#
# ONEMLI (2026-07-03 fix 1): script eskiden `& powershell ... *>> keeper.log`
# ile cagriliyordu ve bu KILITLENIYORDU - start-dashboard'in baslattigi kalici
# servisler (node/python/ngrok) cocuk powershell'in stdout handle'ini miras
# alir, boru EOF gormez ve keeper o tick'te sonsuza dek beklerdi (tick durur,
# self-healing fiilen kapanirdi). Cozum: cikti borusu YOK; ayri surec +
# WaitForExit(zaman asimi). Servisler kendi loglarini logs\*.log'a yazar.
#
# ONEMLI (2026-07-03 fix 2): bu dosyada ASCII DISI karakter KULLANMA (Turkce
# aksan, uzun tire vb. yasak). PowerShell 5.1 BOM'suz dosyayi ANSI okur;
# UTF-8 coklu-byte karakterler parser'i bozup script'i sessizce oldurur.
$ErrorActionPreference = "SilentlyContinue"
$root = "C:\Users\twone\Desktop\Clean E-yAy"
$script = Join-Path $root "scripts\start-dashboard.ps1"
$logs = Join-Path $root "logs"
New-Item -ItemType Directory -Force -Path $logs | Out-Null

while ($true) {
    try {
        $p = Start-Process -WindowStyle Hidden -FilePath "powershell.exe" `
            -ArgumentList "-NoProfile","-ExecutionPolicy","Bypass","-File",$script -PassThru
        if ($p -and -not $p.WaitForExit(300000)) {
            Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
            "[$(Get-Date -Format o)] keeper tick TIMEOUT - start-dashboard 300s'de bitmedi, kill edildi" | Out-File -Append "$logs\keeper.log"
        } else {
            "[$(Get-Date -Format o)] keeper tick OK" | Out-File -Append "$logs\keeper.log"
        }
    } catch {
        "[$(Get-Date -Format o)] keeper hata: $($_.Exception.Message)" | Out-File -Append "$logs\keeper.log"
    }
    Start-Sleep -Seconds 20
}
