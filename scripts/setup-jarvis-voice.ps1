$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$VoiceVenv = Join-Path $Root ".voice-venv"
$VoicePython = Join-Path $VoiceVenv "Scripts\python.exe"

if (-not (Test-Path $VoicePython)) {
    throw "Önce scripts\setup-piper.ps1 çalıştırılmalı; .voice-venv bulunamadı."
}

Write-Host "Jarvis yerel mikrofon bağımlılıkları kuruluyor..."
& $VoicePython -m pip install --upgrade --quiet "sounddevice>=0.5" "websockets>=14" "pystray>=0.19" "Pillow>=10"
if ($LASTEXITCODE -ne 0) { throw "Jarvis ses bağımlılıkları kurulamadı." }

& $VoicePython -m py_compile (Join-Path $Root "scripts\jarvis_voice_agent.py")
if ($LASTEXITCODE -ne 0) { throw "Jarvis ses ajanı sözdizimi doğrulaması başarısız." }

$envPath = Join-Path $Root ".env"
if (-not (Test-Path $envPath)) { New-Item -ItemType File -Path $envPath | Out-Null }
Write-Host "Jarvis hazır. Başlatmak için:"
Write-Host "  $VoicePython scripts\jarvis_voice_agent.py"
