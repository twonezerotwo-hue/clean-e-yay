# Clean E-yAy - LOCAL autostart keeper (ASCII ONLY, project rule #10).
#
# Runs at logon (Startup VBS or Task Scheduler). Idempotent + self-healing:
# every 20s it ensures the local stack is up and starts ONLY what is down.
#
# Stack (LOCAL ONLY - no public tunnel):
#   API             plain uvicorn         http://127.0.0.1:9000
#   tick_worker     long-lived daemon     (30s loop, live data/positions)
#   learning_worker self-paced loop       (calibration/proposals)
#   governor_worker self-paced loop       (observe-only tasks)
#   Ollama          local LLM             http://127.0.0.1:11434 (if installed)
#   web             next start .next-prod http://127.0.0.1:4000
#
# BOOT SAFETY (2026-07-21 fix): a cold-boot API needs longer than one 20s tick
# to answer /health (imports + first snapshot, while 3 workers compete for CPU).
# The old logic ran Free-Port on EVERY unhealthy tick, so it killed the API it
# had just started - an endless restart loop that never came up. Now: if the
# process exists we treat it as BOOTING and wait GraceSec before force-healing;
# Free-Port only runs when no process owns the service (a true zombie port).
#
# FAIL-LOUD (same fix): Start-Process failures used to be swallowed by
# SilentlyContinue while the log still claimed "started" - that hid a missing
# venv python for 8 minutes. Now the exe is checked first and the log records
# the real outcome, with the reason on failure.
#
# ASCII rule: PowerShell 5.1 reads BOM-less files as ANSI; multi-byte UTF-8
# would break the parser and silently kill this keeper. Keep this file ASCII.
#
# Logs: logs\*.log under repo root (keeper's own log: logs\keeper.log).
$ErrorActionPreference = "SilentlyContinue"

# ---- single-instance guard (named mutex) -----------------------------------
# Immune to command-line matching quirks: a second keeper fails to acquire the
# mutex and exits. Two keepers must never run together (each would kill the
# other's freshly started services).
$mutex = New-Object System.Threading.Mutex($false, "Local\CleanEyayLocalAutostart")
if (-not $mutex.WaitOne(0)) { exit }

# ---- paths (dynamic root - survives moving the repo) ------------------------
$root = Split-Path -Parent $PSScriptRoot
$py   = Join-Path $root ".venv\Scripts\python.exe"
$node = "C:\Program Files\nodejs\node.exe"
$web  = Join-Path $root "apps\web"
$logs = Join-Path $root "logs"
New-Item -ItemType Directory -Force -Path $logs | Out-Null

# How long a service may stay unhealthy while its process is alive before we
# treat it as hung and force-restart it.
$GraceSec = 180

function Klog([string]$msg) {
    "[$(Get-Date -Format o)] $msg" | Out-File -Append -Encoding ascii "$logs\keeper.log"
}

Klog "keeper start: root=$root"
if (-not (Test-Path $py))   { Klog "FATAL: venv python yok -> $py (bootstrap gerekli)" }
if (-not (Test-Path $node)) { Klog "WARN: node yok -> $node (web kalkamaz)" }

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
function Get-Procs([string]$exe, [string]$match) {
    return @(Get-CimInstance Win32_Process -Filter "name='$exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -like "*$match*" })
}
function Proc-Running([string]$exe, [string]$match) { return ((Get-Procs $exe $match).Count -gt 0) }
function Kill-Procs([string]$exe, [string]$match) {
    Get-Procs $exe $match | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
}

# Start a service, but only if its executable exists. Logs the real outcome so
# the log never claims success for a start that actually failed.
function Start-Svc([string]$label, [string]$exe, [string[]]$argList, [string]$workDir,
                   [string]$outLog, [string]$errLog) {
    if (-not (Test-Path $exe)) { Klog "$label BASLATILAMADI: exe yok -> $exe"; return $false }
    try {
        Start-Process -WindowStyle Hidden -FilePath $exe -ArgumentList $argList `
            -WorkingDirectory $workDir `
            -RedirectStandardOutput $outLog -RedirectStandardError $errLog -ErrorAction Stop
        Klog "$label baslatildi"
        return $true
    } catch {
        Klog "$label BASLATILAMADI: $($_.Exception.Message)"
        return $false
    }
}

# Ensure an HTTP service: start it when nothing owns it; if a process exists but
# is not answering yet, let it boot (GraceSec) before force-restarting.
function Ensure-HttpSvc([string]$label, [string]$url, [int]$port, [string]$exe, [string]$match,
                        [string[]]$argList, [string]$workDir, [string]$outLog, [string]$errLog,
                        [ref]$downSince) {
    if (Test-Http $url 5) { $downSince.Value = $null; return }

    if (-not (Proc-Running $exe $match)) {
        Free-Port $port            # only when no process owns it (true zombie port)
        if (Start-Svc $label $exe $argList $workDir $outLog $errLog) { $downSince.Value = Get-Date }
        return
    }

    # Process alive but not answering yet -> it is booting; start the grace clock.
    if ($null -eq $downSince.Value) { $downSince.Value = Get-Date; return }
    if (((Get-Date) - $downSince.Value).TotalSeconds -gt $GraceSec) {
        Klog "$label $GraceSec sn+ saglksiz (surec canli) -> zorla yeniden baslatiliyor"
        Kill-Procs $exe $match
        Free-Port $port
        if (Start-Svc $label $exe $argList $workDir $outLog $errLog) { $downSince.Value = Get-Date }
        else { $downSince.Value = $null }
    }
}

# Ensure a worker that has no HTTP surface: process presence is the health check.
function Ensure-Worker([string]$label, [string]$module) {
    if (Proc-Running "python.exe" $module) { return }
    Start-Svc $label $py @("-m", $module) $root "$logs\$label.out.log" "$logs\$label.err.log" | Out-Null
}

# ---- shared env for all child services -------------------------------------
$env:PYTHONPATH = $root

# .env -> process environment, so ALL FOUR services inherit it (2026-07-21 fix).
# Only apps/api/main.py calls _load_dotenv(); tick/learning/governor workers never
# read the file. That silently disabled every owner-approved learning flag and
# every provider key in exactly the processes that consume them - the API looked
# configured while the workers ran blind. AWS never hit this because deploy
# exports the values into the service environment; local had no such step.
# Set-only-if-absent mirrors _load_dotenv(), so a real env var still wins.
$envFile = Join-Path $root ".env"
if (Test-Path $envFile) {
    $loaded = 0
    foreach ($line in (Get-Content $envFile)) {
        $s = $line.Trim()
        if (-not $s -or $s.StartsWith("#") -or ($s -notmatch "=")) { continue }
        $i = $s.IndexOf("=")
        $k = $s.Substring(0, $i).Trim()
        $v = $s.Substring($i + 1).Trim()
        if (-not $k) { continue }
        if (-not [Environment]::GetEnvironmentVariable($k)) {
            [Environment]::SetEnvironmentVariable($k, $v)
            $loaded++
        }
    }
    Klog "env yuklendi: $loaded degisken (.env)"
} else {
    # FAIL-LOUD (project rule): a missing .env is not a warning - it silently
    # reverts every flag to its OFF default and drops every provider key.
    Klog "FATAL: .env yok -> $envFile (tum bayraklar OFF, saglayici anahtarlari yok)"
}
# DEV_CORS is deliberately NOT set: this keeper runs an ALWAYS-ON service, and
# DEV_CORS=true makes the API answer every origin (allow_origins=["*"]). With
# no API_AUTH_TOKEN in the environment the write-auth middleware is a no-op, so
# a wide-open CORS would let any visited web page read state-changing responses
# from 127.0.0.1:9000. Unset => code falls back to the 127.0.0.1:4000 /
# localhost:4000 whitelist, which is all the local dashboard needs.
$env:PATH       = "C:\Program Files\nodejs;" + $env:PATH
# certifi -> SSL_CERT_FILE so live providers do not fail CERTIFICATE_VERIFY_FAILED
if (Test-Path $py) { $cert = & $py -m certifi 2>$null; if ($cert) { $env:SSL_CERT_FILE = $cert } }
$env:NEXT_DIST_DIR = ".next-prod"

# ---- keeper loop -----------------------------------------------------------
$apiDown = $null
$webDown = $null

while ($true) {
    # API - plain uvicorn (endpoints run in threadpool; event loop never blocks)
    Ensure-HttpSvc "api" "http://127.0.0.1:9000/api/v1/health" 9000 $py "uvicorn" `
        @("-m","uvicorn","apps.api.main:app","--host","127.0.0.1","--port","9000") `
        $root "$logs\api.out.log" "$logs\api.err.log" ([ref]$apiDown)

    # workers - process presence is the health signal
    Ensure-Worker "worker"   "apps.tick_worker.main"
    Ensure-Worker "learning" "apps.learning_worker.loop"
    Ensure-Worker "governor" "apps.governor_worker.loop"

    # Ollama - local LLM for chat/persona narration (dead process => robotic chat)
    $ollama = "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe"
    if ((Test-Path $ollama) -and -not (Test-Http "http://127.0.0.1:11434/api/tags" 3)) {
        if (-not (Proc-Running "ollama.exe" "serve")) {
            Start-Svc "ollama" $ollama @("serve") $root "$logs\ollama.out.log" "$logs\ollama.err.log" | Out-Null
        }
    }

    # web - production build (next start from .next-prod; stable, no HMR rot)
    Ensure-HttpSvc "web" "http://127.0.0.1:4000/" 4000 $node "next" `
        @("node_modules/next/dist/bin/next","start","-p","4000","-H","127.0.0.1") `
        $web "$logs\web.out.log" "$logs\web.err.log" ([ref]$webDown)

    Start-Sleep -Seconds 20
}
