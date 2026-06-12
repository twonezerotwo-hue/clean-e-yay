# NEXT TASK — OPS (contract/replay + codegen drift güvencesi)

P0 intelligence parity **tamamen** tamamlandı (bkz. `.tasks/TASK_RESULT.md`,
2026-06-12): rotation engine + news/calendar pipeline, asset universe (rotation
bacakları TLT/HYG/LQD), news/geo/calendar birim testleri, event risk → RiskGate
(yalnızca kısıtlayıcı) + dashboard görünürlüğü.

ROADMAP sırası: **OPS**, sonra v2.7 deep data.

## OPS kapsamı

1. **Contract testleri** (`tests/contract/` şu an boş):
   - `contracts/openapi.yaml` ↔ FastAPI runtime response uyumu. En azından
     `/regime-report/current`, `/decision/matrix`, `/data/snapshot`,
     `/ai-report/current` için: required alanlar mevcut, enum'lar tutuyor,
     additive alanlar (event_risk, event_level, actionable/freshness) şemada.
   - Amaç: el-senkron TS tipleri + openapi.yaml drift'ini yakalamak.

2. **Codegen drift güvencesi**:
   - `apps/web/types/generated/api.ts` openapi.yaml'dan türetiliyor (el ile).
   - Bir drift testi/script: openapi şemasındaki tip adları TS'te var mı,
     enum üyeleri eşleşiyor mu (en azından isim düzeyinde).

3. **Replay testleri** (`tests/replay/`): deterministik snapshot → karar →
   paper akışının regresyon kilidi (aynı girdi = aynı çıktı).

## Hard rules

- PAPER_SAFE / NO_EXECUTION; RiskGate/DQS/KillSwitch/halt zayıflatılamaz.
- Endpoint path'leri ve response alan adları DEĞİŞMEZ (additive ok).
- Runtime'da mock veri yok. Testlerde live network yok.

## Sonra (sıra ile)

- **Asset universe — 2. slice**: JNK/IWM/SMH/XLF/FXI + CoinGecko dominance +
  FRED HY spread/real yield/M2/PPI. ÖNCE her veri için bir karar rolü tasarla
  (sektör genişliği / EM riski / kredi teyidi / makro spread modülü) — engine
  rolü olmadan provider'a ekleme (ölü veri yasak, DATA_POLICY + prensip).
- **v2.7 deep data** — funding/OI/options IV/ETF flow + T3 catalyst half-life
  real engine.
