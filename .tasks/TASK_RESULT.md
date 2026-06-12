# TASK RESULT

Date: 2026-06-12
Task: v2.7 D5 — Real News Feed + Catalyst Half-Life Intelligence
Status: completed

## Prensip

Mevcut RSS haber feed'i gerçek catalyst zekâ katmanına çevrildi. Haber artık
yalnızca panelde görünmüyor; her başlık kural tabanlı (**deterministik, LLM YOK,
network YOK**) bir `event_type`'a sınıflandırılıyor ve event_type'a göre asset ×
timeframe etki haritası + yarı-ömür (half-life) + `valid_until` + actionability
üretiyor. Catalyst impact karar zincirine **yalnızca kısıtlayıcı** girer; ASLA
size artırmaz; ASLA RiskGate/DQS/KillSwitch/halt'ı bypass etmez. **Rumor**
(doğrulanmamış söylenti) `verified=False` → trade'e dönüşmez (yalnızca bağlam).
Yarı-ömrü dolmuş catalyst de karar zincirine girmez. PAPER_SAFE / NO_EXECUTION.

## Ne yapıldı

### 1. Sınıflandırma + half-life motoru (`packages/data/providers/news/catalyst.py`)
- `classify_event_type(title)`: sıralı kural seti → 13 event_type
  (geopolitical_deescalation/escalation, inflation_data, jobs_data, central_bank,
  oil_supply, oil_inventory, crypto_etf_flow, funding_oi_squeeze, earnings,
  exchange_outage, rumor_unverified, unknown). Outage/rumor güvenlik-kritik →
  önce; makro veri jeopolitikten önce; de-escalation escalation'dan önce.
- `is_rumor(title)`: rumor/unconfirmed/sources-say/… → `verified=False` zorunlu.
- `_RULES` tablosu (event_type → half_life_min / timeframes / default_assets /
  base_action / bias_kind). `build_impact(headline)`:
  - affected_assets = event default ∪ başlıktan tespit (classify_asset_impact).
  - surprise_level işaretli (-1..+1): sentiment tabanı + intensity + beat/miss.
  - valid_until = ts + half_life × 3 (≈ 3 yarı-ömür → ~%12.5 kalan).
  - actionability surprise yüksekse yükselir (CAUTION→NO_POSITION_INCREASE).
  - confidence = verified + freshness + relevance.
- `build_impacts(headlines)`: (event_type, assets) dedup + kısıtlayıcı önce sıralı.

### 2. Gate (`packages/risk/catalyst_risk.py`)
- `assess(impacts, symbol, timeframe)`: yalnızca `verified` + yarı-ömrü dolmamış
  (`now ≤ valid_until`) + symbol etkilenen + timeframe etkilenen impact'ler.
  CONTEXT_ONLY→NONE, WATCH→bağlam, CAUTION→×0.5, NO_POSITION_INCREASE→block.
  Yön bağımsız; size_factor ≤ 1.0 garanti; en kısıtlayıcı seviye belirleyici.

### 3. Entegrasyon
- `pipeline.py`: `MarketSnapshot.catalyst_impacts` (başlıklardan, ekstra ağ yok).
- `decision/engine.py`: catalyst gate volatility gate'inden SONRA, RiskGate hard
  gate'lerinden sonra (yalnızca açılış adayına). `catalyst_report` + blocked_by
  `catalyst_risk:*`. matrix_view `catalysts` özeti (verified + dolmamış + kısıtlayıcı).
- `apps/api/routers/data.py`: `/data/snapshot` catalyst_impacts alanı.

### 4. Sözleşme + tipler (additive)
- `contracts/openapi.yaml`: `CatalystImpact` genişletildi (headline_id /
  actionability / verified / source / region / freshness / ts / evidence) +
  `CatalystEventType` / `CatalystActionability` enum + `CatalystSummary` +
  DataSnapshot.catalyst_impacts + DecisionMatrix.catalysts. `api.ts` el-senkron;
  codegen drift + OpenAPI contract testleri yeşil.

### 5. Frontend (selector + panel-registry; page.tsx → 1 GridCell)
- `lib/selectors/catalyst.ts`: selectCatalystImpacts + catalystRemainingMinutes +
  catalystIsActive. `lib/selectors/decision.ts`: selectMatrixCatalysts +
  cellBlockedLabel "CATALYST".
- `CatalystImpactPanel`: event_type (TR etiket) / affected assets+TF / yarı-ömür
  countdown / valid_until / actionability rozeti / surprise / evidence / rumor
  (doğrulanmamış) rozeti. EventCalendarPanel (scheduled) + NewsPanel (unscheduled)
  ayrı kalır — çakışma yok.
- `TimeframeMatrixPanel`: catalyst banner + hücre `blocked_by` "CATALYST" rozeti.

### 6. Testler (`tests/unit/test_catalyst.py`, 21 yeni)
- classification: 11 event_type + rumor override.
- ceasefire → Brent/Gold/BTC + kısa half-life; CPI → CAUTION whipsaw; high-surprise
  → escalate; build_impacts no-network (urlopen guard); unverified → CONTEXT_ONLY.
- gate taksonomi (empty/unverified/expired/other-symbol-tf → NONE; CAUTION ×0.5;
  block; CONTEXT_ONLY no-effect; never-boost; most-restrictive).
- decide_matrix uçtan uca: CAUTION → size küçülür (açılış korunur); block → hücre
  durur + matrix catalysts; rumor → bloklamaz; **DQS BLOCKED & KILL_SWITCH her
  zaman final (catalyst bypass etmez)**.

## Sonuçlar
- **pytest: 287/287** (266 baseline + 21 D5). Live network yok.
- ruff (CI scope: packages + apps/api + workers + tests/contract): temiz.
- `pnpm tsc --noEmit` + `pnpm build`: yeşil.
- Live smoke: API health/snapshot/matrix 200; `/data/snapshot` gerçek RSS →
  central_bank/geopolitical/funding_squeeze/etf_flow/rumor sınıfları (rumor
  verified=false); `/decision/matrix` catalyst banner 4 kayıt; RiskGate suspended
  iken catalyst hücreyi bypass etmiyor (doğru öncelik); web SSR 200, "Catalyst
  Etkisi" paneli + mevcut 30 panel bozulmadı.

## PAPER_SAFE
- broker: yok · gerçek emir: yok · live execution: yok.
- RiskGate/DQS/KillSwitch/halt: sıfır diff, bypass yok.
- catalyst: yalnızca kısıtlayıcı; asla size artırmaz; verified-only + yarı-ömrü
  dolmamış karar; rumor trade'e dönüşmez.
