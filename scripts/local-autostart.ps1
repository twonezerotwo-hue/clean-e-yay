# Clean E-yAy - LOCAL autostart keeper (ASCII ONLY, project rule #10).
#
# Runs at logon via Task Scheduler "CleanEyayLocalAutostart". Idempotent +
# self-healing: every 20s it ensures the local stack is up and starts ONLY the
# parts that are down. Healthy parts are skipped (HTTP 200 / process match).
#
# Stack (LOCAL ONLY - no public tunnel):
#   API            plain uvicorn        http://127.0.0.1:9000
#   tick_worker    long-lived daemon    (30s loop, live data/positions)
#   learning_worker self-paced loop     (calibration/proposals)
#   governor_worker self-paced loop     (observe-only tasks)
#   Ollama         local LLM            http://127.0.0.1:11434 (if installed)
#   web            next start .next-prod http://127.0.0.1:4000
#
# ASCII rule: PowerShell 5.1 reads BOM-less files as ANSI; multi-byte UTF-8
# would break the parser and silently kill this keeper. Keep this file ASCII.
#
# Logs: logs\*.log under repo root. Stop: Unregister-ScheduledTask
# -TaskName CleanEyayLocalAutostart, then kill python.exe/node.exe if desired.
$ErrorActionPreference = "SilentlyContinue"

# ---- single-instance guard (named mutex) -----------------------------------
# A per-session named mutex is immune to command-line matching quirks: if a
# second keeper starts it fails to acquire the mutex and exits. Two keepers
# must never run together (each Free-Port would kill the other's services).
$mutex = New-Object System.Threading.Mutex($false, "Local\CleanEyayLocalAutostart")
if (-not $mutex.WaitOne(0)) { exit }

# ---- paths (dynamic root - works regardless of folder name) -----------------
$root = Split-Path -Parent $PSScriptRoot
$py   = Join-Path $root ".venv\Scripts\python.exe"
$node = "C:\Program Files\nodejs\node.exe"
$web  = Join-Path $root "apps\web"
$logs = Join-Path $root "logs"
New-Item -ItemType Directory -Force -Path $logs | Out-Null

# ---- keeper self-log (heartbeat + what it starts) --------------------------
function Klog([string]$msg) {
    "[$(Get-Date -Format o)] $msg" | Out-File -Append -Encoding ascii "$logs\keeper.log"
}
Klog "keeper start: root=$root py-exists=$(Test-Path $py)"

# ---- shared env for all child services -------------------------------------
$env:PYTHONPATH = $root
$env:DEV_CORS   = "true"
$env:PATH       = "C:\Program Files\nodejs;" + $env:PATH
# certifi -> SSL_CERT_FILE so live providers do not fail CERTIFICATE_VERIFY_FAILED
$cert = & $py -m certifi 2>$null
if ($cert) { $env:SSL_CERT_FILE = $cert }

# ---- helpers ---------------------------------------------------------------
function Test-Http([string]$url, [int]$sec = 5) {
    try { return ((Invoke-WebRequest $url -TimeoutSec $sec -UseBasicParsing).StatusCode -eq 200) }
    catch { return $false }
}
function Free-Port([int]$p) {
    (Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue).OwningProcess |
        Select-Object -Unique | ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }
    Start-Sleep -Seconds 1
}
function Proc-Running([string]$match) {
    return [bool](Get-CimInstance Win32_Process -Filter "name='python.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -like "*$match*" })
}

# ---- keeper loop -----------------------------------------------------------
while ($true) {
    $started = @()

    # API - plain uvicorn (endpoints run in threadpool; event loop never blocks)
    if (-not (Test-Http "http://127.0.0.1:9000/api/v1/health" 5)) {
        Free-Port 9000
        Start-Process -WindowStyle Hidden -FilePath $py `
            -ArgumentList "-m","uvicorn","apps.api.main:app","--host","127.0.0.1","--port","9000" `
            -WorkingDirectory $root `
            -RedirectStandardOutput "$logs\api.out.log" -RedirectStandardError "$logs\api.err.log"
        $started += "api"
    }

    # tick_worker - long-lived daemon (live snapshot/position refresh)
    if (-not (Proc-Running "tick_worker")) {
        Start-Process -WindowStyle Hidden -FilePath $py `
            -ArgumentList "-m","apps.tick_worker.main" -WorkingDirectory $root `
            -RedirectStandardOutput "$logs\worker.out.log" -RedirectStandardError "$logs\worker.err.log"
        $started += "tick_worker"
    }

    # learning_worker - self-paced loop variant (NOT restart-always spin)
    if (-not (Proc-Running "learning_worker.loop")) {
        Start-Process -WindowStyle Hidden -FilePath $py `
            -ArgumentList "-m","apps.learning_worker.loop" -WorkingDirectory $root `
            -RedirectStandardOutput "$logs\learning.out.log" -RedirectStandardError "$logs\learning.err.log"
        $started += "learning_worker.loop"
    }

    # governor_worker - observe-only loop (owner-gated; never opens positions)
    if (-not (Proc-Running "governor_worker.loop")) {
        Start-Process -WindowStyle Hidden -FilePath $py `
            -ArgumentList "-m","apps.governor_worker.loop" -WorkingDirectory $root `
            -RedirectStandardOutput "$logs\governor.out.log" -RedirectStandardError "$logs\governor.err.log"
        $started += "governor_worker.loop"
    }

    # Ollama - local LLM for chat/persona narration (dead process => robotic chat)
    $ollama = "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe"
    if ((Test-Path $ollama) -and -not (Test-Http "http://127.0.0.1:11434/api/tags" 3)) {
        Start-Process -WindowStyle Hidden -FilePath $ollama -ArgumentList "serve" `
            -RedirectStandardOutput "$logs\ollama.out.log" -RedirectStandardError "$logs\ollama.err.log"
        $started += "ollama"
    }

    # web - production build (next start from .next-prod; stable, no HMR rot)
    if (-not (Test-Http "http://127.0.0.1:4000/" 5)) {
        Free-Port 4000
        $env:NEXT_DIST_DIR = ".next-prod"
        Start-Process -WindowStyle Hidden -FilePath $node `
            -ArgumentList "node_modules/next/dist/bin/next","start","-p","4000","-H","127.0.0.1" `
            -WorkingDirectory $web `
            -RedirectStandardOutput "$logs\web.out.log" -RedirectStandardError "$logs\web.err.log"
        $started += "web"
    }

    if ($started.Count -gt 0) { Klog ("started: " + ($started -join ", ")) }
    else { Klog "tick OK (all up)" }

    Start-Sleep -Seconds 20
}
