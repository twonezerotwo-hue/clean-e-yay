# Clean E-yAy — açılışta dashboard'ı ayağa kaldırır:
#   1) API (plain uvicorn) + tick_worker (ayrı süreç) -> 127.0.0.1:9000
#   2) Web (Next.js)                                -> 127.0.0.1:4000
#   3) ngrok sabit domain                           -> https://mobster-ipad-transform.ngrok-free.dev
# Idempotent + SELF-HEALING: port açık ama ölü (zombi) ise temizleyip yeniden başlatır.
# Loglar: logs\*.log
$ErrorActionPreference = "SilentlyContinue"

$root = "C:\Users\twone\Desktop\Clean E-yAy"
$node = "C:\Program Files\nodejs\node.exe"
$py   = Join-Path $root ".venv\Scripts\python.exe"
$ngrok = Join-Path $root "tools\ngrok.exe"
$logs = Join-Path $root "logs"
New-Item -ItemType Directory -Force -Path $logs | Out-Null

# Gerçek sağlık = HTTP 200 (sadece port açık olması yetmez; zombi süreç de port tutar).
function Test-Http([string]$url, [int]$timeoutSec = 5) {
    try { return ((Invoke-WebRequest $url -TimeoutSec $timeoutSec -UseBasicParsing).StatusCode -eq 200) }
    catch { return $false }
}

# Bir port'u tutan tüm süreçleri öldür (zombi temizliği).
function Free-Port([int]$p) {
    (Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue).OwningProcess |
        Select-Object -Unique | ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }
    Start-Sleep -Seconds 1
}

# 1a) API — PLAIN UVICORN (supervisor DEĞİL). Supervisor worker'ı API ile aynı
# event-loop'ta sync build_snapshot çağırıp loop'u ~23s bloke ediyor → cockpit/brief
# donuyor. Plain uvicorn'da endpoint'ler threadpool'da çalışır, loop bloke olmaz.
$env:PYTHONPATH = "."
$env:DEV_CORS   = "true"
if (-not (Test-Http "http://127.0.0.1:9000/api/v1/health" 30)) {
    Free-Port 9000
    Start-Process -WindowStyle Hidden -FilePath $py `
        -ArgumentList "-m","uvicorn","apps.api.main:app","--host","127.0.0.1","--port","9000" `
        -WorkingDirectory $root `
        -RedirectStandardOutput "$logs\api.out.log" -RedirectStandardError "$logs\api.err.log"
}

# 1b) tick_worker — AYRI süreç (canlı veri/pozisyon + disk cache tazeler).
$workerRunning = Get-CimInstance Win32_Process -Filter "name='python.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -like '*tick_worker*' }
if (-not $workerRunning) {
    Start-Process -WindowStyle Hidden -FilePath $py `
        -ArgumentList "-m","apps.tick_worker.main" -WorkingDirectory $root `
        -RedirectStandardOutput "$logs\worker.out.log" -RedirectStandardError "$logs\worker.err.log"
}

# 1b2) learning_worker — AYRI süreç (kalibrasyon/öneri döngüsü, 5 dakikada bir).
$learningRunning = Get-CimInstance Win32_Process -Filter "name='python.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -like '*learning_worker.loop*' }
if (-not $learningRunning) {
    Start-Process -WindowStyle Hidden -FilePath $py `
        -ArgumentList "-m","apps.learning_worker.loop" -WorkingDirectory $root `
        -RedirectStandardOutput "$logs\learning.out.log" -RedirectStandardError "$logs\learning.err.log"
}

# 1c) Cold cache ısıtma — API health gelince bir kez cockpit/brief tetikle (fire-and-forget).
#     İlk snapshot derlemesi arka planda olsun; kullanıcı ilk açılışta beklemesin.
Start-Job -ScriptBlock {
    $n = 0
    while ($n -lt 30) {
        try {
            Invoke-WebRequest "http://127.0.0.1:9000/api/v1/health" -TimeoutSec 5 -UseBasicParsing | Out-Null
            Invoke-WebRequest "http://127.0.0.1:9000/api/v1/cockpit/brief" -TimeoutSec 90 -UseBasicParsing | Out-Null
            break
        } catch { Start-Sleep -Seconds 3; $n++ }
    }
} | Out-Null

# 2) Web — PRODUCTION (next start), dev DEĞİL. next dev uzun çalışmada HMR ile
# çürüyüp 200 dönse de hidrasyonu bozabiliyor (beyaz ekran). next start
# önceden derlenmiş, stabil. FE değişince: `next build` (tek sefer) gerekir.
if (-not (Test-Http "http://127.0.0.1:4000/")) {
    Free-Port 4000
    # NEXT_DIST_DIR=.next-prod — platformun otomatik önizleme dev sunucusu
    # (next dev, varsayılan .next klasörü) ile build klasörü ÇAKIŞMASIN.
    $env:NEXT_DIST_DIR = ".next-prod"
    Start-Process -WindowStyle Hidden -FilePath $node `
        -ArgumentList "node_modules/next/dist/bin/next","start","-p","4000","-H","127.0.0.1" `
        -WorkingDirectory (Join-Path $root "apps\web") `
        -RedirectStandardOutput "$logs\web.out.log" -RedirectStandardError "$logs\web.err.log"
}

# Web hazır olana kadar bekle (tünel boş port'a bağlanmasın)
$tries = 0
while (-not (Test-Http "http://127.0.0.1:4000/") -and $tries -lt 90) { Start-Sleep -Seconds 2; $tries++ }

# 3) Tünel — ngrok sabit domain (güvenilir, kendi kendine yeniden bağlanır).
if (-not (Get-Process ngrok -ErrorAction SilentlyContinue)) {
    Start-Process -WindowStyle Hidden -FilePath $ngrok `
        -ArgumentList "http","4000","--url=https://mobster-ipad-transform.ngrok-free.dev" `
        -RedirectStandardOutput "$logs\ngrok.out.log" -RedirectStandardError "$logs\ngrok.err.log"
}
