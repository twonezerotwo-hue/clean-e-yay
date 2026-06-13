#!/usr/bin/env bash
# Clean E-yAy — local worker runner (7/24 tick + one-shot learning).
#
# tick_worker      : UZUN-ÖMÜRLÜ daemon (TICK_INTERVAL_SEC'te döner; SIGTERM-aware).
# learning_worker  : TEK-SEFERLİK (run_once). 7/24 için zamanlayıcıyla çalıştır
#                    (cron / launchd / systemd timer) — restart-always KULLANMA.
#
# Bu script başlangıçta learning'i BİR kez seed eder, sonra tick daemon'ını
# ön planda çalıştırır (Ctrl+C durdurur). API'ye HTTP bağımlılığı yok; aynı
# data/runtime state dosyalarını paylaşır.
#
# PAPER_SAFE / NO_EXECUTION: worker'lar yalnızca paper tick + gözlem üretir;
# broker yok, gerçek emir yok.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

choose_python() {
  if [ -n "${PYTHON:-}" ] && command -v "$PYTHON" >/dev/null 2>&1; then
    echo "$PYTHON"; return
  fi
  if [ -x "$ROOT/.venv/bin/python" ]; then echo "$ROOT/.venv/bin/python"; return; fi
  alt="$ROOT/../E_YAY CODEX/.venv/bin/python"
  if [ -x "$alt" ]; then echo "$alt"; return; fi
  echo "python3"
}
PY="$(choose_python)"
export PYTHONPATH="$ROOT"
echo "[workers] python=$PY"

# SSL CA zinciri (live provider'lar) — certifi varsa otomatik.
if [ -z "${SSL_CERT_FILE:-}" ]; then
  CERT="$("$PY" -m certifi 2>/dev/null || true)"
  [ -n "$CERT" ] && export SSL_CERT_FILE="$CERT" && echo "[workers] SSL_CERT_FILE=$SSL_CERT_FILE"
fi

echo "[workers] learning_worker (one-shot) seed…"
"$PY" -m apps.learning_worker.main || echo "[workers] learning_worker non-zero (NO_DATA olabilir) — devam"

echo "[workers] tick_worker daemon (interval=${TICK_INTERVAL_SEC:-30}s) — Ctrl+C durdurur"
exec "$PY" -m apps.tick_worker.main
