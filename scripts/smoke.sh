#!/usr/bin/env bash
# Clean E-yAy — deployment health smoke.
#
# Çalışan bir API (+ opsiyonel web) üzerinde kritik endpoint'leri ve web SSR'ı
# doğrular. Yeni karar HESAPLAMAZ — yalnızca canlı sağlık kontrolü. Herhangi bir
# kontrol başarısızsa exit 1.
#
# Kullanım:
#   scripts/smoke.sh
#   API_BASE=http://127.0.0.1:8050 WEB_BASE=http://127.0.0.1:3050 scripts/smoke.sh
#   SKIP_WEB=true scripts/smoke.sh        # yalnızca API
#
# PAPER_SAFE / NO_EXECUTION: bu script salt-okur GET'ler atar; emir üretmez.
set -uo pipefail

API_BASE="${API_BASE:-http://127.0.0.1:8000}"
WEB_BASE="${WEB_BASE:-http://127.0.0.1:3000}"
SKIP_WEB="${SKIP_WEB:-false}"

PASS=0
FAIL=0

check() {  # check <label> <url>
  local label="$1" url="$2" code
  code="$(curl -fsS -o /dev/null -w '%{http_code}' --max-time 20 "$url" 2>/dev/null)" || code="000"
  if [ "$code" = "200" ]; then
    printf '  ✓ %-22s 200  %s\n' "$label" "$url"
    PASS=$((PASS + 1))
  else
    printf '  ✗ %-22s %s  %s\n' "$label" "$code" "$url"
    FAIL=$((FAIL + 1))
  fi
}

echo "Clean E-yAy smoke — API=$API_BASE"
echo "── API (kritik endpoint'ler) ─────────────────────────────"
check "health"          "$API_BASE/api/v1/health"
check "system/health"   "$API_BASE/api/v1/system/health"
check "cockpit/brief"   "$API_BASE/api/v1/cockpit/brief"
check "data/snapshot"   "$API_BASE/api/v1/data/snapshot"
check "decision/matrix" "$API_BASE/api/v1/decision/matrix"
check "replay/status"   "$API_BASE/api/v1/replay/status"
check "learning/summary" "$API_BASE/api/v1/learning/summary"

# PAPER_SAFE / NO_EXECUTION bayrağını system/health'ten doğrula (rapor).
sh_body="$(curl -fsS --max-time 20 "$API_BASE/api/v1/system/health" 2>/dev/null || true)"
case "$sh_body" in
  *'"paper_safe": true'*|*'"paper_safe":true'*)
    echo "  ✓ paper_safe=true · no_execution (system/health)";;
  *) echo "  ! paper_safe doğrulanamadı (system/health gövdesi okunamadı)";;
esac

if [ "$SKIP_WEB" != "true" ]; then
  echo "── Web (SSR) ─────────────────────────────────────────────"
  check "web SSR /"      "$WEB_BASE/"
fi

echo "──────────────────────────────────────────────────────────"
echo "PASS=$PASS  FAIL=$FAIL"
[ "$FAIL" -eq 0 ] || { echo "SMOKE FAILED"; exit 1; }
echo "SMOKE OK"
