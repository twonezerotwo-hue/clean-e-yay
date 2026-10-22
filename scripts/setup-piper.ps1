param(
    [string]$Voice = "tr_TR-dfki-medium",
    [switch]$Cuda
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$ModelDir = Join-Path $Root "data\models\piper"
$ModelPath = Join-Path $ModelDir "$Voice.onnx"
$ConfigPath = Join-Path $ModelDir "$Voice.onnx.json"
$VoiceBase = "https://huggingface.co/rhasspy/piper-voices/resolve/main/tr/tr_TR/dfki/medium"
$VoiceVenv = Join-Path $Root ".voice-venv"
$VoicePython = Join-Path $VoiceVenv "Scripts\python.exe"
$PiperPath = Join-Path $VoiceVenv "Scripts\piper.exe"

New-Item -ItemType Directory -Force -Path $ModelDir | Out-Null

$python = Get-Command python.exe -ErrorAction SilentlyContinue
if (-not $python) { $python = Get-Command py.exe -ErrorAction SilentlyContinue }
if (-not $python) { throw "Python bulunamadı; Piper kurulamadı." }
if (-not (Test-Path $VoicePython)) {
    Write-Host "İzole Piper ortamı oluşturuluyor..."
    & $python.Source -m venv $VoiceVenv
    if ($LASTEXITCODE -ne 0) { throw "Piper ses ortamı oluşturulamadı." }
}
Write-Host "Piper 1.8.0 kuruluyor (ana uygulama .venv'ine dokunulmaz)..."
& $VoicePython -m pip install --upgrade --quiet "piper-tts==1.8.0"
if ($LASTEXITCODE -ne 0) { throw "piper-tts kurulumu başarısız oldu." }
if ($Cuda) {
    Write-Host "CUDA destekli ONNX Runtime kuruluyor..."
    # Piper's CPU wheel and GPU wheel share the same `onnxruntime` import
    # package. Remove the CPU wheel first; otherwise Python can silently load
    # CPU providers even though the GPU wheel is installed.
    & $VoicePython -m pip uninstall --yes --quiet onnxruntime
    & $VoicePython -m pip install --upgrade --quiet "onnxruntime-gpu[cuda,cudnn]==1.31.0"
    if ($LASTEXITCODE -ne 0) { throw "CUDA ONNX Runtime kurulumu başarısız oldu." }
}
if (-not (Test-Path $PiperPath)) { throw "İzole Piper çalıştırıcısı bulunamadı." }

function Download-IfMissing([string]$Url, [string]$Path) {
    if (Test-Path $Path) {
        Write-Host "Mevcut: $Path"
        return
    }
    Write-Host "İndiriliyor: $Url"
    Invoke-WebRequest -Uri $Url -OutFile $Path -UseBasicParsing
    if (-not (Test-Path $Path) -or (Get-Item $Path).Length -lt 1024) {
        throw "İndirilen Piper dosyası geçersiz: $Path"
    }
}

Download-IfMissing "$VoiceBase/$Voice.onnx" $ModelPath
Download-IfMissing "$VoiceBase/$Voice.onnx.json" $ConfigPath

$envPath = Join-Path $Root ".env"
if (-not (Test-Path $envPath)) {
    $examplePath = Join-Path $Root ".env.example"
    if (Test-Path $examplePath) {
        Copy-Item $examplePath $envPath
    } else {
        New-Item -ItemType File -Path $envPath | Out-Null
    }
}
$lines = [System.Collections.Generic.List[string]](Get-Content $envPath)
function Set-EnvLine([string]$Name, [string]$Value) {
    for ($i = 0; $i -lt $lines.Count; $i++) {
        if ($lines[$i] -match "^$([regex]::Escape($Name))=") {
            $lines[$i] = "$Name=$Value"
            return
        }
    }
    $lines.Add("$Name=$Value")
}
Set-EnvLine "PIPER_MODEL" "data/models/piper/$Voice.onnx"
Set-EnvLine "PIPER_BIN" ".voice-venv/Scripts/piper.exe"
Set-EnvLine "PIPER_USE_CUDA" ($(if ($Cuda) { "1" } else { "0" }))
[System.IO.File]::WriteAllText(
    $envPath,
    (($lines -join [Environment]::NewLine) + [Environment]::NewLine),
    (New-Object System.Text.UTF8Encoding($false))
)

Write-Host "Piper hazır: $PiperPath"
Write-Host "Model hazır: $ModelPath"
