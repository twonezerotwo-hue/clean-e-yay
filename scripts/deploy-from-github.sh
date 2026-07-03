#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/clean-e-yay}"
BRANCH="${DEPLOY_BRANCH:-main}"
LOCK_FILE="${DEPLOY_LOCK_FILE:-/tmp/clean-e-yay-deploy.lock}"

exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  echo "deploy already running"
  exit 1
fi

cd "$APP_DIR"

echo "deploy: fetch origin/${BRANCH}"
git fetch origin "$BRANCH"
git checkout "$BRANCH"
git reset --hard "origin/${BRANCH}"

if [ ! -d ".venv" ]; then
  python3 -m venv .venv
fi

echo "deploy: python deps"
. .venv/bin/activate
pip install --upgrade pip
pip install -e .

echo "deploy: web deps"
pnpm install --filter web --frozen-lockfile

echo "deploy: web build"
(
  cd apps/web
  NEXT_DIST_DIR=.next-prod pnpm build
)

# Öğrenme otonomi flag'leri (Grup B, owner kararı) — PROD .env'de yoksa ekle.
# Bunlar SIR DEĞİL, davranış toggle'ı: apps.api.main._load_dotenv APP_DIR/.env'i
# supervisor import'unda yükler. Idempotent (grep -q guard) → deploy'da çoğalmaz;
# owner .env'de değeri elle değiştirirse (örn. =0) korunur (yalnız YOK ise eklenir).
# Instance rebuild'de de kalıcı (SSH gerektirmez).
ensure_env() {  # ensure_env KEY VALUE — yalnız YOK ise ekle (owner elle ezerse korunur)
  touch "$APP_DIR/.env"
  grep -q "^$1=" "$APP_DIR/.env" 2>/dev/null || echo "$1=$2" >> "$APP_DIR/.env"
}
set_env() {  # set_env KEY VALUE — replace-or-add (değeri ZORLA ayarla; diğer satırlar korunur)
  touch "$APP_DIR/.env"
  grep -v "^$1=" "$APP_DIR/.env" > "$APP_DIR/.env.tmp" 2>/dev/null || true
  echo "$1=$2" >> "$APP_DIR/.env.tmp"
  mv "$APP_DIR/.env.tmp" "$APP_DIR/.env"
}
ensure_env WEIGHT_LOSS_AWARE 1
ensure_env REBALANCE_ROLLBACK_MIN_OUTCOMES 8
# Grup C — tam otonom öz-ayar (CP5'e kadar). Trailing/threshold autotune AÇIK.
ensure_env TF_TARGET_TRAIL_AUTOTUNE 1
ensure_env THRESHOLD_AUTOTUNE 1
# Kalite tuning'i AKTİF: edge-gate KAPALI (0) → geometri/trailing stop/exit'i ŞİMDİ
# düzeltsin (±%15 bant + outcome-rollback net). Owner kararı — bekletme, aktif çalışsın.
# set_env: AWS .env'de =1 kalmışsa ZORLA 0'a çevirir (ensure_env yetmez).
set_env TF_TARGET_EDGE_GATE 0
# Denetim 2026-07-03 — TF kalibrasyon veri hijyeni: owner_manual gibi verified ama
# fingerprint'siz kayıtlar TF kalibrasyonuna sızmasın (1d'de 6 manuel işlem sızıyordu,
# 19→13). Lokal .env'de =1; AWS'e de aynısı (owner kuralı: lokal+AWS her zaman senkron).
ensure_env TF_CALIBRATION_AUTO_ONLY 1
# E-4 aktivasyon (2026-07-03, owner kararı): aynı veri hijyeni çıkış/geometri
# öğrenmesinde de — tf_target_trainer + entry_exit_quality dataset'i yalnız AUTO
# kohort. EDGE_GATE=0 KALIR (aktif tuning); EXIT_FORENSICS_NUDGE 2 hafta shadow sonra.
ensure_env TF_TARGET_AUTO_ONLY 1

echo "deploy: restart services"
sudo systemctl restart eyay-supervisor.service
sudo systemctl restart eyay-web.service

# Health-check retry: t3.small'da API/web port'a bind olması 6sn'den uzun
# sürebiliyor (ağır import + state yükleme). Tek-seferlik curl yanlış-negatif
# veriyordu (kod aslında canlıya çıkmış olsa bile deploy "failed" görünüyordu).
# Başarı için ~60sn grace; gerçek crash'te (servis active değil / port hiç
# açılmıyor) yine non-zero exit ile patlar.
wait_for() {
  local what="$1" tries="${3:-30}" i
  for ((i = 1; i <= tries; i++)); do
    if eval "$2" >/dev/null 2>&1; then
      echo "deploy: $what ok (${i}. denemede)"
      return 0
    fi
    sleep 2
  done
  echo "deploy: $what FAILED ($((tries * 2))sn sonra hâlâ cevap yok)" >&2
  return 1
}

systemctl is-active --quiet eyay-supervisor.service
systemctl is-active --quiet eyay-web.service
wait_for "api"  "curl -fsS http://127.0.0.1:9000/api/v1/health" 30
wait_for "web"  "curl -fsSI http://127.0.0.1:3000/" 30

echo "deploy: ok $(git rev-parse --short HEAD)"
