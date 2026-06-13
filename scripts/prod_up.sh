#!/usr/bin/env bash
# Clean E-yAy — local production up. Tek komutla API + web + tick daemon
# (background, pid+log data/runtime/ altında) + learning one-shot seed.
#
#   scripts/prod_up.sh
#   API_PORT=8060 WEB_PORT=3060 scripts/prod_up.sh   # izole port
#
# Port meşgulse açık hata + eski LaunchAgent uyarısı verir; başlatmaz.
# PAPER_SAFE / NO_EXECUTION: broker yok, gerçek emir yok.
set -uo pipefail
source "$(dirname "$0")/_prod_common.sh"

PY="$(choose_python)"
export PYTHONPATH="$ROOT"
ensure_ssl "$PY"
resolve_node

echo "[prod] root=$ROOT"
echo "[prod] python=$PY"
echo "[prod] api=http://$API_HOST:$API_PORT  web=http://127.0.0.1:$WEB_PORT"
[ -n "${SSL_CERT_FILE:-}" ] && echo "[prod] SSL_CERT_FILE=$SSL_CERT_FILE"

# ── Pre-flight: port çakışması (bizim çalışan süreçlerimiz hariç) ──────────
preflight() {
  local bad=0
  if ! is_running api && port_busy "$API_PORT"; then
    echo "[prod] HATA: API portu $API_PORT meşgul (pid: $(port_pids "$API_PORT"))" >&2; bad=1
  fi
  if ! is_running web && port_busy "$WEB_PORT"; then
    echo "[prod] HATA: Web portu $WEB_PORT meşgul (pid: $(port_pids "$WEB_PORT"))" >&2; bad=1
  fi
  if [ "$bad" = 1 ]; then
    detect_old_agents
    echo "[prod] farklı port ile dene: API_PORT=8060 WEB_PORT=3060 scripts/prod_up.sh" >&2
    exit 1
  fi
}

start_proc() {  # start_proc <name> <cmd...>
  local name="$1"; shift
  if is_running "$name"; then
    echo "[prod] $name zaten çalışıyor (pid $(pid_of "$name")) — atlandı"
    return 0
  fi
  nohup "$@" >"$LOG_DIR/$name.log" 2>&1 </dev/null &
  echo $! >"$(pidfile "$name")"
  echo "[prod] $name başladı (pid $(pid_of "$name")) → $LOG_DIR/$name.log"
}

start_web() {
  if is_running web; then
    echo "[prod] web zaten çalışıyor (pid $(pid_of web)) — atlandı"; return 0
  fi
  command -v node >/dev/null 2>&1 || { echo "[prod] HATA: node yok (PATH veya ~/.local/node/bin)"; return 1; }
  [ -x "$NEXT_BIN" ] || { echo "[prod] HATA: $NEXT_BIN yok — apps/web bağımlılıkları kurulmamış (pnpm install)"; return 1; }
  if [ ! -f "$ROOT/apps/web/.next/BUILD_ID" ]; then
    echo "[prod] web prod build yok — next build…"
    ( cd "$ROOT/apps/web" && "$NEXT_BIN" build ) || { echo "[prod] HATA: web build başarısız"; return 1; }
  fi
  ( cd "$ROOT/apps/web"
    NEXT_PUBLIC_API_BASE_URL="http://$API_HOST:$API_PORT" \
      nohup "$NEXT_BIN" start -p "$WEB_PORT" -H 127.0.0.1 >"$LOG_DIR/web.log" 2>&1 </dev/null &
    echo $! >"$(pidfile web)"
  )
  echo "[prod] web başladı (pid $(pid_of web)) → $LOG_DIR/web.log"
}

detect_old_agents
preflight

start_proc api "$PY" -m uvicorn apps.api.main:app --host "$API_HOST" --port "$API_PORT"
start_web || echo "[prod] web başlatılamadı (yukarıdaki hata) — API/tick devam"
start_proc tick "$PY" -m apps.tick_worker.main

echo "[prod] learning_worker one-shot seed (periyodik için zamanlayıcı kullan — restart-always DEĞİL)…"
if "$PY" -m apps.learning_worker.main >>"$LOG_DIR/learning.log" 2>&1; then
  echo "[prod] learning bitti → $LOG_DIR/learning.log"
else
  echo "[prod] learning non-zero (NO_DATA olabilir) → $LOG_DIR/learning.log"
fi

echo "[prod] ✓ up. durum: scripts/prod_status.sh · smoke: make prod-smoke · durdur: scripts/prod_down.sh"
