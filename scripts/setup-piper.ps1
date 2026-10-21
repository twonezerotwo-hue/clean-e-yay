param(
    [string]$Voice = "tr_TR-dfki-medium"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$ModelDir = Join-Path $Root "data\models\piper"
$ModelPath = Join-Path $ModelDir "$Voice.onnx"
$ConfigPath = Join-Path $ModelDir "$Voice.onnx.json"
$VoiceBase = "https://huggingface.co/rhasspy/piper-voices/resolve/main/tr/tr_TR/dfki/medium"

New-Item -ItemType Directory -Force -Path $ModelDir | Out-Null

function Find-Piper {
    $venvPiper = Join-Path $Root ".venv\Scripts\piper.exe"
    if (Test-Path $venvPiper) { return $venvPiper }
    $command = Get-Command piper.exe -ErrorAction SilentlyContinue
    if ($command) { return $command.Source }

    $candidates = @(
        (Join-Path $env:LOCALAPPDATA "Programs\Python\Python312\Scripts\piper.exe"),
        (Join-Path $env:APPDATA "Python\Python312\Scripts\piper.exe"),
        (Join-Path $Root ".voice-venv\Scripts\piper.exe")
    )
    return $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
}

$venvPython = Join-Path $Root ".venv\Scripts\python.exe"
$venvPiper = Join-Path $Root ".venv\Scripts\piper.exe"
$piperPath = if (Test-Path $venvPiper) { $venvPiper } else { $null }
if (-not $piperPath -and (Test-Path $venvPython)) {
    Write-Host "Piper .venv içine kuruluyor..."
    & $venvPython -m pip install piper-tts --quiet
    if ($LASTEXITCODE -ne 0) { throw "piper-tts kurulumu başarısız oldu." }
    $piperPath = Find-Piper
}
if (-not $piperPath) {
    $python = Get-Command py.exe -ErrorAction SilentlyContinue
    if (-not $python) { $python = Get-Command python.exe -ErrorAction SilentlyContinue }
    if (-not $python) { throw "Python bulunamadı; Piper kurulamadı." }

    & $python.Source -m pip install --user piper-tts
    if ($LASTEXITCODE -ne 0) { throw "piper-tts kurulumu başarısız oldu." }
    $piperPath = Find-Piper
}
if (-not $piperPath) { throw "Piper çalıştırıcısı bulunamadı." }

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
Set-EnvLine "TTS_PROVIDER" "piper"
Set-EnvLine "PIPER_MODEL" "data/models/piper/$Voice.onnx"
[System.IO.File]::WriteAllText(
    $envPath,
    (($lines -join [Environment]::NewLine) + [Environment]::NewLine),
    (New-Object System.Text.UTF8Encoding($false))
)

Write-Host "Piper hazır: $piperPath"
Write-Host "Model hazır: $ModelPath"
