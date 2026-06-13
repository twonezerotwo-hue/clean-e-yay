#!/usr/bin/env bash
# Clean E-yAy — local production down. Supervised süreçleri (api/web/tick)
# pid dosyalarından nazikçe (SIGTERM, sonra gerekirse SIGKILL) durdurur.
# learning tek-seferlik olduğu için zaten çıkmıştır (supervise edilmez).
#
#   scripts/prod_down.sh
set -uo pipefail
source "$(dirname "$0")/_prod_common.sh"

stop_proc() {  # stop_proc <name>
  local name="$1" f pid
  f="$(pidfile "$name")"
  if [ ! -f "$f" ]; then
    echo "[prod] $name: pid dosyası yok (çalışmıyor)"; return 0
  fi
  pid="$(cat "$f" 2>/dev/null || true)"
  if [ -z "$pid" ] || ! kill -0 "$pid" 2>/dev/null; then
    echo "[prod] $name: süreç yok (eski pid '${pid:-?}') — pid dosyası temizlendi"
    rm -f "$f"; return 0
  fi
  kill -TERM "$pid" 2>/dev/null || true
  local i
  for i in $(seq 1 20); do
    kill -0 "$pid" 2>/dev/null || break
    sleep 0.25
  done
  if kill -0 "$pid" 2>/dev/null; then
    echo "[prod] $name (pid $pid) SIGTERM'e yanıt vermedi — SIGKILL"
    kill -KILL "$pid" 2>/dev/null || true
  fi
  echo "[prod] $name durduruldu (pid $pid)"
  rm -f "$f"
}

for name in "${PROCS[@]}"; do
  stop_proc "$name"
done
echo "[prod] ✓ down."
