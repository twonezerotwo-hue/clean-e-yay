<#
  Clean E-yAy - Windows local dev baslatici (PowerShell).
  scripts/dev.sh'in Windows karsiligi. API + web'i ayri pencerelerde acar.

  Varsayilan portlar, eski "E_YAY CODEX" projesi 8000/3000'de calisirken
  yan yana calismak icin secildi:
    API -> http://127.0.0.1:8001
    Web -> http://127.0.0.1:4000

  Kullanim:
    .\scripts\dev.ps1                          # API 8001, Web 4000
    .\scripts\dev.ps1 -ApiPort 8000 -WebPort 3000   # repo varsayilani

  Notlar:
    - Python: repo .venv\Scripts\python.exe (yoksa PATH'teki python).
    - certifi kuruluysa SSL_CERT_FILE otomatik ayarlanir (live provider SSL).
    - apps/web/.env.local yoksa ApiPort ile olusturulur.
    - PAPER_SAFE / NO_EXECUTION korunur - broker yok.
#>
param(
  [int]$ApiPort = 8001,
  [int]$WebPort = 4000
)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Py = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Py)) { $Py = "python" }

$env:PYTHONPATH = $Root
try { $cert = & $Py -m certifi 2>$null; if ($cert) { $env:SSL_CERT_FILE = $cert } } catch {}
$env:DEV_CORS = "true"

$webEnv = Join-Path $Root "apps\web\.env.local"
if (-not (Test-Path $webEnv)) {
  "NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:$ApiPort" | Out-File -FilePath $webEnv -Encoding utf8
  Write-Host "[dev] yazildi: apps/web/.env.local"
}

Write-Host "[dev] python = $Py"
Write-Host "[dev] api -> http://127.0.0.1:$ApiPort"
Write-Host "[dev] web -> http://127.0.0.1:$WebPort"

$apiCmd = "`$env:PYTHONPATH='$Root'; `$env:SSL_CERT_FILE='$($env:SSL_CERT_FILE)'; `$env:DEV_CORS='true'; & '$Py' -m uvicorn apps.api.main:app --reload --host 127.0.0.1 --port $ApiPort"
Start-Process powershell -ArgumentList "-NoExit", "-Command", $apiCmd

$web = Join-Path $Root "apps\web"
$webCmd = "pnpm -C '$web' exec next dev --port $WebPort --hostname 127.0.0.1"
Start-Process powershell -ArgumentList "-NoExit", "-Command", $webCmd

Write-Host "[dev] iki pencere acildi (API + web). Durdurmak icin pencereleri kapat veya Ctrl+C."
