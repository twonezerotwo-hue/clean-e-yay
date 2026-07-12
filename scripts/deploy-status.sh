#!/usr/bin/env bash
# deploy-status — remote main HEAD GERÇEKTEN AWS'e deploy oldu mu? (F1, 2026-07-12)
#
# Neden: "push başarılı" ≠ "AWS aldı". Deploy EC2 workflow'u CI'ın
# `workflow_run.conclusion == success` şartına bağlı — CI kırmızıysa deploy
# SESSİZCE `skipped` olur, push yine "başarılı" görünür. 2026-07-12 canlı olay:
# tek bir ruff hatası CI'ı kırdı → 5 commit / ~14 saat AWS geride kaldı, kimse
# fark etmedi. Bu araç o sapmayı görünür kılar: remote HEAD ile son BAŞARILI
# Deploy EC2 run'ını kıyaslar, senkron değilse SEBEBİYLE uyarır.
#
# Kullanım: scripts/deploy-status.sh   (push sonrası koştur)
# Çıkış kodu: senkronsa 0, AWS geride/uyarı varsa 1 (keep-alive/CI gate edebilir).
set -u

if ! command -v gh >/dev/null 2>&1; then
  echo "[deploy-status] gh CLI yok — kontrol atlandı (kur: https://cli.github.com)"
  exit 0
fi

REMOTE_SHA="$(git ls-remote origin main 2>/dev/null | cut -f1)"
if [ -z "$REMOTE_SHA" ]; then
  echo "[deploy-status] remote main okunamadı (ağ/erişim?) — kontrol atlandı"
  exit 0
fi
REMOTE_SHORT="${REMOTE_SHA:0:8}"

# En son Deploy EC2 ve CI run'ları (gh'in gömülü jq'su — harici jq gerekmez).
DEP="$(gh run list --workflow "Deploy EC2" --branch main --limit 1 \
        --json headSha,status,conclusion \
        --jq '.[0] | "\(.headSha)|\(.status)|\(.conclusion)"' 2>/dev/null)"
CI="$(gh run list --workflow "CI" --branch main --limit 1 \
        --json headSha,status,conclusion \
        --jq '.[0] | "\(.headSha)|\(.status)|\(.conclusion)"' 2>/dev/null)"

DEP_SHA="${DEP%%|*}"; _r="${DEP#*|}"; DEP_STATUS="${_r%%|*}"; DEP_CONC="${_r##*|}"
CI_SHA="${CI%%|*}";  _r="${CI#*|}";  CI_STATUS="${_r%%|*}";  CI_CONC="${_r##*|}"

behind="?"
behind="$(git rev-list --count "${DEP_SHA}..${REMOTE_SHA}" 2>/dev/null || echo '?')"

echo "Remote main HEAD : $REMOTE_SHORT"
echo "Son Deploy EC2   : ${DEP_SHA:0:8}  [${DEP_STATUS}/${DEP_CONC:-–}]"
echo "Son CI (main)    : ${CI_SHA:0:8}  [${CI_STATUS}/${CI_CONC:-–}]"
echo ""

if [ "$DEP_SHA" = "$REMOTE_SHA" ] && [ "$DEP_CONC" = "success" ]; then
  echo "✅ AWS SENKRON — remote HEAD ($REMOTE_SHORT) başarıyla deploy edildi."
  exit 0
fi

echo "⚠️  AWS remote HEAD'DE DEĞİL — kod canlıya gitmemiş olabilir (AWS $behind commit geride)."
if [ "$CI_STATUS" = "in_progress" ] || [ "$DEP_STATUS" = "in_progress" ]; then
  echo "   Sebep: CI/Deploy hâlâ ÇALIŞIYOR — birkaç dakika sonra tekrar bak."
elif [ "$CI_SHA" = "$REMOTE_SHA" ] && [ "$CI_CONC" = "failure" ]; then
  echo "   Sebep: CI KIRMIZI ($REMOTE_SHORT) → Deploy EC2 skip ediyor."
  echo "   Çözüm: 'gh run view --log-failed' ile bak, düzelt, tekrar push."
elif [ "$DEP_CONC" = "skipped" ]; then
  echo "   Sebep: son Deploy EC2 SKIPPED (muhtemelen CI red). CI'ı yeşile getir."
else
  echo "   AWS ${DEP_SHA:0:8}'de kalmış; aradaki commit'ler deploy olmamış."
fi
exit 1
