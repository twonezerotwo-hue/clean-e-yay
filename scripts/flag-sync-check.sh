#!/usr/bin/env bash
# flag-sync-check — lokal .env ile AWS deploy (deploy-from-github.sh) arasında
# öğrenme/davranış flag'i SAPMASINI yakalar.
#
# Neden: owner kuralı "env/flag değişince lokal+AWS birlikte uygula". Ama
# deploy'daki ensure_env YALNIZ "yoksa ekle" yapar — owner lokal .env'de bir
# flag'i çevirip deploy script'e eklemeyi unutursa AWS sessizce sapar. Bu araç
# o sapmayı görünür kılar (yeni panel değil; script/keep-alive seviyesi).
#
# Kaynak: SYNC_FLAGS listesi (AWS'e senkronlanması GEREKEN davranış flag'leri).
# Yeni senkron-flag eklenince buraya + deploy script'e eklenir; test_flag_sync
# deploy script'in set ettiği her flag'in burada TANINDIĞINI doğrular (kör nokta
# olmaz). Lokal-only flag'ler (örn. LLM_MODE=ollama) bilinçli olarak LİSTEDE DEĞİL.
#
# Çıkış kodu: sapma yoksa 0, en az bir ⚠ varsa 1 (keep-alive/CI gate edebilir).
set -u

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="$ROOT/.env"
DEPLOY="$ROOT/scripts/deploy-from-github.sh"

# AWS'e senkronlanması gereken davranış/öğrenme flag'leri (tek doğruluk kaynağı).
SYNC_FLAGS="
TF_TARGET_AUTO_ONLY
TF_CALIBRATION_AUTO_ONLY
TF_TARGET_EDGE_GATE
TF_TARGET_TRAIL_AUTOTUNE
THRESHOLD_AUTOTUNE
EXIT_FORENSICS_NUDGE
WEIGHT_REGIME_FILTER
WEIGHT_LOSS_AWARE
REBALANCE_ROLLBACK_MIN_OUTCOMES
MISTAKE_MEMORY_V2
EXPECTANCY_R_MODE
DISCOVERY_SCAN_ENABLED
BACKTEST_CHALLENGER_ENABLED
LEARNING_INCLUDE_SHADOW
BAR_HISTORY_ENABLED
BINANCE_OHLCV_ENABLED
TF_TRUST_PER_BUCKET
SUBSIGNAL_SCORECARD_ENABLED
TF_SCORING_V2_SHADOW
"

# Bir flag'in dosyadaki değeri (KEY=VALUE, son eşleşme); yoksa boş.
_val_in() {  # _val_in FILE KEY
  [ -f "$1" ] || { echo ""; return; }
  grep -E "^$2=" "$1" 2>/dev/null | tail -1 | cut -d= -f2- | tr -d '[:space:]'
}

# Deploy script'in flag'e verdiği direktif değeri (ensure_env/set_env KEY VALUE);
# yoksa boş.
_deploy_directive() {  # _deploy_directive KEY
  grep -E "^\s*(ensure_env|set_env)\s+$1\s+" "$DEPLOY" 2>/dev/null \
    | tail -1 | awk '{print $3}'
}

printf '%-34s %-8s %-10s %s\n' "FLAG" "LOKAL" "AWS-DEPLOY" "DURUM"
printf '%-34s %-8s %-10s %s\n' "----" "-----" "----------" "-----"

drift=0
for f in $SYNC_FLAGS; do
  local_v="$(_val_in "$ENV_FILE" "$f")"
  deploy_v="$(_deploy_directive "$f")"
  lshow="${local_v:-unset}"
  dshow="${deploy_v:-NONE}"
  status="ok"
  # Sapma tanımı: lokal ile deploy direktifi farklıysa; VEYA lokal ON ama deploy
  # hiç set etmiyorsa (AWS default'a düşer, sessiz sapma).
  if [ -n "$local_v" ] && [ -n "$deploy_v" ] && [ "$local_v" != "$deploy_v" ]; then
    status="DRIFT (lokal!=aws)"; drift=1
  elif [ -n "$local_v" ] && [ -z "$deploy_v" ]; then
    case "$(echo "$local_v" | tr 'A-Z' 'a-z')" in
      1|true|yes|on) status="DRIFT (lokal ON, aws direktifi yok)"; drift=1 ;;
    esac
  fi
  printf '%-34s %-8s %-10s %s\n' "$f" "$lshow" "$dshow" "$status"
done

echo ""
if [ "$drift" -eq 0 ]; then
  echo "OK: lokal .env ile AWS deploy senkron (sapma yok)."
else
  echo "UYARI: en az bir flag sapması var. Lokal .env'i deploy-from-github.sh ile hizala."
fi
exit "$drift"
