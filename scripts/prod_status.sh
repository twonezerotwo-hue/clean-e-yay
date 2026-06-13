#!/usr/bin/env bash
# Clean E-yAy — local production status. Supervised süreçlerin (api/web/tick)
# durumu + portlar + (API ayaktaysa) system/health özeti. Salt-okur.
#
#   scripts/prod_status.sh
set -uo pipefail
source "$(dirname "$0")/_prod_common.sh"

echo "Clean E-yAy — prod status"
echo "── süreçler ──────────────────────────────────────────────"
for name in "${PROCS[@]}"; do
  if is_running "$name"; then
    printf "  ● %-5s RUNNING  pid %-7s log %s\n" "$name" "$(pid_of "$name")" "$LOG_DIR/$name.log"
  else
    printf "  ○ %-5s stopped  %s\n" "$name" "$( [ -f "$(pidfile "$name")" ] && echo "(eski pid $(pid_of "$name"))" || echo "(pid yok)" )"
  fi
done

# learning tek-seferlik — son satırı göster.
if [ -f "$LOG_DIR/learning.log" ]; then
  echo "  · learning (one-shot) son: $(tail -n 1 "$LOG_DIR/learning.log" 2>/dev/null | cut -c1-90)"
fi

echo "── portlar ───────────────────────────────────────────────"
for p in "$API_PORT" "$WEB_PORT"; do
  if port_busy "$p"; then
    printf "  :%-5s LISTEN  pid %s\n" "$p" "$(port_pids "$p")"
  else
    printf "  :%-5s boş\n" "$p"
  fi
done
detect_old_agents

# API ayaktaysa system/health özeti (network-free ViewModel).
if is_running api && command -v curl >/dev/null 2>&1; then
  body="$(curl -fsS --max-time 10 "http://$API_HOST:$API_PORT/api/v1/system/health" 2>/dev/null || true)"
  if [ -n "$body" ]; then
    echo "── system/health ─────────────────────────────────────────"
    case "$body" in *'"paper_safe": true'*|*'"paper_safe":true'*) echo "  ✓ paper_safe=true · no_execution";; *) echo "  ! paper_safe doğrulanamadı";; esac
    # stale_workers / warnings varsa kısaca göster (jq yoksa grep).
    echo "$body" | grep -o '"stale_workers":[^]]*]' | head -1 | sed 's/^/  /' || true
    echo "$body" | grep -o '"warnings":[^]]*]' | head -1 | sed 's/^/  /' || true
  fi
fi

echo "──────────────────────────────────────────────────────────"
echo "smoke: make prod-smoke · durdur: scripts/prod_down.sh · loglar: $LOG_DIR"
