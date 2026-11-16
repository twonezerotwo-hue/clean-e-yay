param([switch]$Once)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root ".voice-venv\Scripts\python.exe"
$Agent = Join-Path $Root "scripts\jarvis_voice_agent.py"
$LogDir = Join-Path $Root "logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

if (-not (Test-Path $Python)) {
    throw "Jarvis kurulmamış. Önce scripts\setup-jarvis-voice.ps1 çalıştırılmalı."
}

# Match the agent filename rather than the full command line.  Windows can
# expose one launch with quotes and another without them; the old full-path
# wildcard check could miss a just-started instance and open a second mic.
$running = @(Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -match 'jarvis_voice_agent\.py(?:\s|$)' })
if ($running.Count -gt 0) { Write-Host "Jarvis zaten çalışıyor."; exit 0 }

$args = @($Agent)
if ($Once) { $args += "--once" }
Start-Process -WindowStyle Hidden -FilePath $Python -ArgumentList $args -WorkingDirectory $Root `
    -RedirectStandardOutput (Join-Path $LogDir "jarvis-voice.out.log") `
    -RedirectStandardError (Join-Path $LogDir "jarvis-voice.err.log")
Write-Host "Jarvis yerel ses ajanı başlatıldı; durum data\runtime\jarvis_voice_status.json dosyasına yazılıyor."
