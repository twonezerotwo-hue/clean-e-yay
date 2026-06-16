<#
  Clean E-yAy - fresh-clone bootstrap (Windows / PowerShell).

  Yeni bir makineye klonladiktan sonra TEK komutla calisir hale getirir:
    .\scripts\bootstrap.ps1

  Adimlari:
    1. .venv olustur (yoksa) + Python deps kur (pyproject [project] dependencies).
    2. data/runtime klasorunu olustur (worker'lar bekler, gitignored).
    3. Basit "import + boot smoke" testi.
    4. (Opsiyonel) -RunDev verilirse: API + worker'i baslat.

  Kullanim:
    .\scripts\bootstrap.ps1                # sadece kur
    .\scripts\bootstrap.ps1 -RunDev        # kur + dev.ps1 ile API + web ac
    .\scripts\bootstrap.ps1 -RunWorker     # kur + tick_worker on-planda

  Gerekli: Python 3.11+ PATH'te. (Yoksa python.org'dan indirin.)
#>
param(
  [switch]$RunDev,
  [switch]$RunWorker
)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

Write-Host "[bootstrap] root = $Root"

# ---- 1. Python yorumlayici --------------------------------------------------
$pythonCmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $pythonCmd) { $pythonCmd = Get-Command py -ErrorAction SilentlyContinue }
if (-not $pythonCmd) {
  Write-Error "Python bulunamadi. https://www.python.org/downloads/ adresinden 3.11+ kurun."
  exit 1
}
$pythonExe = $pythonCmd.Source
Write-Host "[bootstrap] python = $pythonExe"
& $pythonExe --version

# ---- 2. .venv olustur (yoksa) -----------------------------------------------
$venvPy = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPy)) {
  Write-Host "[bootstrap] .venv olusturuluyor..."
  & $pythonExe -m venv .venv
}
Write-Host "[bootstrap] venv python = $venvPy"
& $venvPy -m pip install --upgrade pip --quiet

# ---- 3. Backend deps kur (pyproject) ----------------------------------------
Write-Host "[bootstrap] backend bagimliliklari kuruluyor (pyproject)..."
& $venvPy -m pip install -e ".[dev]" --quiet
if ($LASTEXITCODE -ne 0) { Write-Error "pip install basarisiz"; exit 1 }

# ---- 4. data/runtime klasoru -------------------------------------------------
$runtime = Join-Path $Root "data\runtime"
if (-not (Test-Path $runtime)) {
  New-Item -ItemType Directory -Force -Path $runtime | Out-Null
  Write-Host "[bootstrap] data/runtime/ olusturuldu"
}

# ---- 5. Smoke: import + tek tick + pytest (hizli) ---------------------------
$env:PYTHONPATH = $Root
Write-Host "[bootstrap] import smoke..."
& $venvPy -c "import fastapi, uvicorn, pydantic, yaml, httpx; from apps.api.main import app; from apps.tick_worker import main; from apps.learning_worker import main as lw; print('imports OK')"
if ($LASTEXITCODE -ne 0) { Write-Error "Import smoke FAIL"; exit 1 }

Write-Host "[bootstrap] tick + learning bir kez kosulu (uctan uca smoke)..."
& $venvPy -c "import asyncio; from apps.tick_worker import main as tw; asyncio.run(tw.run_once()); from apps.learning_worker import main as lw; lw.run_once(); print('worker smoke OK')"
if ($LASTEXITCODE -ne 0) { Write-Error "Worker smoke FAIL"; exit 1 }

Write-Host ""
Write-Host "[bootstrap] BACKEND HAZIR." -ForegroundColor Green
Write-Host "    Test:     `"$venvPy`" -m pytest -q -p no:cacheprovider --basetemp=`".pytest_tmp/basetemp`""
Write-Host "    API:      `"$venvPy`" -m uvicorn apps.api.main:app --host 127.0.0.1 --port 8001"
Write-Host "    Worker:   `"$venvPy`" -m apps.tick_worker.main"
Write-Host "    Dev (API+web pencereli): .\scripts\dev.ps1"
Write-Host ""

if ($RunWorker) {
  Write-Host "[bootstrap] tick_worker on planda baslatiliyor (Ctrl+C ile durur)..."
  & $venvPy -m apps.tick_worker.main
} elseif ($RunDev) {
  Write-Host "[bootstrap] dev.ps1 cagriliyor..."
  & (Join-Path $Root "scripts\dev.ps1")
}
