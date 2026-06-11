#!/usr/bin/env bash
# Clean E-yAy — local live dev başlatıcısı.
#
# API'yi 127.0.0.1:8000'da uvicorn --reload ile,
# Web'i 127.0.0.1:3000'de `pnpm dev` ile çalıştırır.
# Ctrl+C ile her ikisini durdurur.
#
# Çevre değişkenleri:
#   API_PORT (default 8000)
#   WEB_PORT (default 3000)
#   PYTHON   (default: önce repo .venv/bin/python, yoksa cross-repo venv,
#             yoksa python3)
#   DEV_CORS=true → API tüm origin'leri kabul eder
#   TEST_USE_MOCK=true → opsiyonel, mock provider'lar
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

API_PORT="${API_PORT:-8000}"
WEB_PORT="${WEB_PORT:-3000}"

# Python yorumlayıcısını seç (uvicorn'u içeren bir venv).
choose_python() {
  if [ -n "${PYTHON:-}" ] && command -v "$PYTHON" >/dev/null 2>&1; then
    echo "$PYTHON"; return
  fi
  if [ -x "$ROOT/.venv/bin/python" ]; then
    echo "$ROOT/.venv/bin/python"; return
  fi
  # Geliştirici makinesinde cross-repo venv olabilir (eski E_YAY CODEX).
  alt="$ROOT/../E_YAY CODEX/.venv/bin/python"
  if [ -x "$alt" ]; then
    echo "$alt"; return
  fi
  if command -v python3 >/dev/null 2>&1; then
    echo "python3"; return
  fi
  echo "python3"
}

PY="$(choose_python)"
echo "[dev] python=$PY"
echo "[dev] api  → http://127.0.0.1:$API_PORT"
echo "[dev] web  → http://127.0.0.1:$WEB_PORT"

# .env.local yoksa .env.example'dan otomatik oluştur (sadece bilgilendirme).
WEB_ENV="$ROOT/apps/web/.env.local"
if [ ! -f "$WEB_ENV" ]; then
  echo "NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:$API_PORT" > "$WEB_ENV"
  echo "[dev] yazıldı: apps/web/.env.local"
fi

cleanup() {
  echo "[dev] kapanıyor…"
  jobs -p | xargs -r kill 2>/dev/null || true
  wait 2>/dev/null || true
}
trap cleanup EXIT INT TERM

# API
(
  cd "$ROOT"
  export PYTHONPATH="$ROOT"
  exec "$PY" -m uvicorn apps.api.main:app --reload --host 127.0.0.1 --port "$API_PORT"
) &
API_PID=$!

# Web — pnpm install'ı zaten geçirildiyse fast path.
(
  cd "$ROOT/apps/web"
  if [ ! -d node_modules ]; then
    echo "[dev] pnpm install…"
    pnpm install --no-frozen-lockfile
  fi
  PORT="$WEB_PORT" exec pnpm dev --port "$WEB_PORT"
) &
WEB_PID=$!

echo "[dev] api pid=$API_PID  web pid=$WEB_PID"
wait
