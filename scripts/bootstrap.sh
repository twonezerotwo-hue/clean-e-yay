#!/usr/bin/env bash
# Clean E-yAy — fresh-clone bootstrap (Mac/Linux).
#
# Yeni bir makineye klonladıktan sonra TEK komutla çalışır hale getirir:
#   ./scripts/bootstrap.sh
#
# Adımlar:
#   1. .venv oluştur (yoksa) + Python deps kur (pyproject [project] dependencies).
#   2. data/runtime klasörünü oluştur (worker'lar bekler, gitignored).
#   3. Basit "import + boot smoke" testi.
#   4. (Opsiyonel) --dev / --worker bayrağı verilirse: API + worker'ı başlat.
#
# Kullanım:
#   ./scripts/bootstrap.sh                # sadece kur
#   ./scripts/bootstrap.sh --dev          # kur + dev.sh ile API + web aç
#   ./scripts/bootstrap.sh --worker       # kur + tick_worker ön planda
#
# Gerekli: Python 3.11+ PATH'te.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "[bootstrap] root = $ROOT"

# ---- 1. Python yorumlayıcı --------------------------------------------------
choose_python() {
  for cand in python3.13 python3.12 python3.11 python3 python; do
    if command -v "$cand" >/dev/null 2>&1; then
      ver=$("$cand" -c 'import sys; print(sys.version_info[:2])' 2>/dev/null || echo "(0,0)")
      case "$ver" in
        "(3, 11)"|"(3, 12)"|"(3, 13)"|"(3, 14)") echo "$cand"; return ;;
      esac
    fi
  done
  return 1
}
PY_HOST="$(choose_python || true)"
if [ -z "$PY_HOST" ]; then
  echo "[bootstrap] HATA: Python 3.11+ bulunamadı." >&2
  echo "  macOS:  brew install python@3.12" >&2
  echo "  Linux:  apt install python3.12 python3.12-venv" >&2
  exit 1
fi
echo "[bootstrap] python (host) = $PY_HOST"
"$PY_HOST" --version

# ---- 2. .venv (yoksa) -------------------------------------------------------
if [ ! -x "$ROOT/.venv/bin/python" ]; then
  echo "[bootstrap] .venv oluşturuluyor..."
  "$PY_HOST" -m venv .venv
fi
VENV_PY="$ROOT/.venv/bin/python"
echo "[bootstrap] venv python = $VENV_PY"
"$VENV_PY" -m pip install --upgrade pip --quiet

# ---- 3. Backend deps kur (pyproject) ----------------------------------------
echo "[bootstrap] backend bağımlılıkları kuruluyor (pyproject)..."
"$VENV_PY" -m pip install -e ".[dev]" --quiet

# ---- 4. data/runtime --------------------------------------------------------
mkdir -p "$ROOT/data/runtime"

# ---- 4b. git hooks (F1: pre-push ruff guard — CI-red → AWS drift önler) ------
if [ -d "$ROOT/.git" ]; then
  git -C "$ROOT" config core.hooksPath .githooks
  chmod +x "$ROOT/.githooks/pre-push" 2>/dev/null || true
  echo "[bootstrap] git hooks aktif (.githooks; pre-push ruff guard)"
fi

# ---- 5. Smoke: import + bir tick + bir learning -----------------------------
export PYTHONPATH="$ROOT"
echo "[bootstrap] import smoke..."
"$VENV_PY" -c "import fastapi, uvicorn, pydantic, yaml, httpx; from apps.api.main import app; from apps.tick_worker import main; from apps.learning_worker import main as lw; print('imports OK')"

echo "[bootstrap] tick + learning bir kez koşulu (uçtan uca smoke)..."
"$VENV_PY" -c "import asyncio; from apps.tick_worker import main as tw; asyncio.run(tw.run_once()); from apps.learning_worker import main as lw; lw.run_once(); print('worker smoke OK')"

echo ""
echo "[bootstrap] ✅ BACKEND HAZIR."
echo "    Test:    $VENV_PY -m pytest -q"
echo "    API:     $VENV_PY -m uvicorn apps.api.main:app --host 127.0.0.1 --port 8001"
echo "    Worker:  $VENV_PY -m apps.tick_worker.main"
echo "    Dev (API+web): ./scripts/dev.sh"
echo ""

# ---- 6. Opsiyonel: çalıştır -------------------------------------------------
for arg in "$@"; do
  case "$arg" in
    --worker)
      echo "[bootstrap] tick_worker ön planda başlatılıyor (Ctrl+C ile durur)..."
      exec "$VENV_PY" -m apps.tick_worker.main
      ;;
    --dev)
      echo "[bootstrap] dev.sh çağrılıyor..."
      exec "$ROOT/scripts/dev.sh"
      ;;
  esac
done
