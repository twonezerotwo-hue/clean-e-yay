# NEXT TASK — P0 Intelligence Parity (kalan kapsam)

P0'ın çekirdeği tamamlandı (bkz. `.tasks/TASK_RESULT.md`, 2026-06-12):
- ✅ Gerçek RSS/geo news provider + event calendar YAML provider (pipeline'a
  `provider_status` + unavailable warning'leriyle bağlı).
- ✅ Gerçek rotation engine (1d OHLCV momentum + çapraz oran), hash-mock
  kaldırıldı; veri yoksa UNAVAILABLE + redistribute (mock karar vermez).
- ✅ Consensus rotation UNAVAILABLE → quantum redistribute; news skoru sadece
  verified headlines'tan.

Aşağıdakiler bilinçli olarak ertelendi (SKIPPED → bu fazda yap):

## 1. Asset universe expansion
- Provider registry'ye temiz ekleme: TLT, HYG, LQD, JNK, IWM, SMH, XLF, FXI
  (yfinance) — rotation engine bunları zaten ROTATION_SYMBOLS/_RATIO_DEFS'te
  bekliyor; eklenince HYG/LQD kredi spread'i ve TLT/SPY savunma rotasyonu
  canlıda aktif olur (şu an 6/9 seri ile çalışıyor).
- CoinGecko global'den BTC dominance / USDT dominance / TOTAL / TOTAL2.
- FRED'den HY spread, real yield, M2, PPI (CPI var).
- Kurallar: provider fail → crash yok; API key yoksa açık DEGRADED; mock
  fallback yok; DQS/provenance açık. DEFAULT_SYMBOLS davranışı DEĞİŞMEZ.

## 2. News/geo/calendar birim testleri
- RSS fixture parse (offline); network fail → no mock + DEGRADED + nötr 50.
- Geo headline bölge sınıflandırması (USA/Iran/Israel/China/Russia/Europe/
  ME-energy) fixture testi.
- Calendar YAML load; unavailable → no mock + warning. High-impact event
  yakın → WATCH/NO_POSITION_INCREASE (bypass yok).

## 3. Event risk → RiskGate (yalnızca kısıtlayıcı)
- `packages/risk/event_risk.py`: yüksek etkili verified event yakınsa
  WATCH / NO_POSITION_INCREASE. Asla size artırmaz, asla gate gevşetmez.

## Hard rules
- PAPER_SAFE / NO_EXECUTION; RiskGate/DQS/KillSwitch/halt zayıflatılamaz.
- Endpoint path'leri ve response alan adları DEĞİŞMEZ (additive ok).
- Runtime'da mock veri yok (DATA_POLICY). Testlerde live network yok.

## Sonra
- **OPS** — contract/replay testleri + codegen drift güvencesi.
- **v2.7 deep data** — funding/OI/options IV/ETF flow + T3 catalyst
  half-life real engine.
