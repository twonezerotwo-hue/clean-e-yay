#!/usr/bin/env bash
# Clean E-yAy — prod_{up,down,status}.sh ortak yardımcıları. Doğrudan
# çalıştırılmaz; source edilir.
#
# Süreç modeli:
#   api  — uzun-ömürlü HTTP (uvicorn, reload YOK)        → supervised (pid)
#   web  — uzun-ömürlü SSR (next start)                  → supervised (pid)
#   tick — uzun-ömürlü daemon (tick_worker)              → supervised (pid)
#   learning — TEK-SEFERLİK (run_once)  → prod-up'ta seed; 7/24 için zamanlayıcı
#              (cron/launchd/systemd timer) — restart-always DEĞİL (spin-loop).
#
# PAPER_SAFE / NO_EXECUTION: broker yok, gerçek emir yok; worker'lar yalnızca
# paper tick + gözlem üretir.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# .env varsa yükle (yoksa sorun değil; app .env'i otomatik yüklemez). CLI'da
# verilen env'i ezmemek için yalnızca .env içindeki anahtarlar export edilir.
if [ -f "$ROOT/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  . "$ROOT/.env" 2>/dev/null || true
  set +a
fi

API_HOST="${API_HOST:-127.0.0.1}"
API_PORT="${API_PORT:-8000}"
WEB_PORT="${WEB_PORT:-3000}"

RUN_DIR="$ROOT/data/runtime/run"
LOG_DIR="$ROOT/data/runtime/logs"
mkdir -p "$RUN_DIR" "$LOG_DIR"

# Supervised süreçler (learning hariç — o tek-seferlik).
PROCS=(api web tick)

pidfile()    { echo "$RUN_DIR/$1.pid"; }
pid_of()     { cat "$(pidfile "$1")" 2>/dev/null || true; }
is_running() { local f; f="$(pidfile "$1")"; [ -f "$f" ] && kill -0 "$(cat "$f" 2>/dev/null)" 2>/dev/null; }
port_busy()  { lsof -nP -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1; }
port_pids()  { lsof -nP -iTCP:"$1" -sTCP:LISTEN -t 2>/dev/null | tr '\n' ' '; }

# Eski E_YAY CODEX LaunchAgent'ları (port çakışmasının kök nedeni) — açık uyar.
detect_old_agents() {
  local hit
  hit="$(launchctl list 2>/dev/null | awk '/com\.eyay/{print $3}' | tr '\n' ' ')"
  if [ -n "$hit" ]; then
    echo "[prod] UYARI: eski E_YAY CODEX LaunchAgent'ları aktif: $hit" >&2
    echo "       (örn. com.eyay.backend → *:8000 / com.eyay.frontend → :3000 port çakışması)" >&2
    echo "       Oturum bazlı kapat (plist silmeden): launchctl bootout gui/\$(id -u)/com.eyay.backend" >&2
  fi
}

choose_python() {
  if [ -n "${PYTHON:-}" ] && command -v "$PYTHON" >/dev/null 2>&1; then echo "$PYTHON"; return; fi
  [ -x "$ROOT/.venv/bin/python" ] && { echo "$ROOT/.venv/bin/python"; return; }
  [ -x "$ROOT/../E_YAY CODEX/.venv/bin/python" ] && { echo "$ROOT/../E_YAY CODEX/.venv/bin/python"; return; }
  echo python3
}

ensure_ssl() {  # ensure_ssl <python>
  if [ -z "${SSL_CERT_FILE:-}" ]; then
    local cert
    cert="$("$1" -m certifi 2>/dev/null || true)"
    [ -n "$cert" ] && export SSL_CERT_FILE="$cert"
  fi
}

resolve_node() {
  if ! command -v node >/dev/null 2>&1 && [ -x "$HOME/.local/node/bin/node" ]; then
    export PATH="$HOME/.local/node/bin:$PATH"
  fi
}
NEXT_BIN="$ROOT/apps/web/node_modules/.bin/next"
