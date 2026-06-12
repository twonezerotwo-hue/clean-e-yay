# TASK RESULT

Date: 2026-06-12
Task: P0 intelligence parity (kalan kapsam) — asset universe (rotation
      bacakları) + news/geo/calendar birim testleri + event risk → RiskGate
      (yalnızca kısıtlayıcı) + dashboard görünürlüğü
Status: completed (asset universe kısmı bilinçli olarak daraltıldı — aşağıda)

## Prensip

"Yeni veri eklemek tek başına amaç değil." Her eklenen veri için karar
zincirine etkisi + dashboard görünürlüğü birlikte teslim edildi:
- TLT/HYG/LQD → rotation motoru artık 9/9 seriyle çalışıyor; TAHVİL sınıfı +
  TLT/SPY savunma + HYG/LQD kredi oranları **canlıda aktif** (smoke'ta
  TAHVİL sınıfı ve TLT/SPY oranı evidence'ta göründü).
- Event riski → RiskGate'e kısıtlayıcı candidate; matrix/regime-report'ta
  görünür; EventCalendarPanel'da actionability rozeti.
- Haber etkisi → NewsPanel'da etkilenen sembol rozetleri / "yalnızca bağlam".

## Ne yapıldı

1. **Asset universe (rotation bacakları)**: `ohlcv/yfinance._SYMBOL_MAP`'e
   TLT/HYG/LQD eklendi (Yahoo ticker = sembol). `source_registry`'ye
   `tlt/hyg/lqd_yfinance` (kind: rotation, decision_usage: simulation_only,
   fallback_to_mock: false). Engine bunları zaten bekliyordu → TAHVİL sınıfı,
   GLD/TLT, TLT/SPY, HYG/LQD oranları canlandı. DEFAULT_SYMBOLS DEĞİŞMEDİ.
2. **Event risk → RiskGate (yalnızca kısıtlayıcı)**: yeni
   `packages/risk/event_risk.py`. Yaklaşan **doğrulanmış** yüksek etkili
   takvim olayı → WATCH veya NO_POSITION_INCREASE. `RiskEngine.evaluate()`
   opsiyonel `event_candidates` alır; aynı havuza girip max-priority seçilir
   → DQS KILL_SWITCH / halt event riskini **her zaman ezer** (bypass yok),
   event riski hiçbir gate'i gevşetmez, size artırmaz. `decide_all` /
   `decide_matrix` `snap.catalysts`'ten candidate üretir. `matrix_view` +
   `regime-report` additive `event_risk` bloğu + per-catalyst `event_level`.
   thresholds: `event_risk.{block_window_hours:24, watch_window_hours:72,
   high_importance:[high,critical]}`.
3. **News/geo/calendar birim testleri** (`tests/unit/test_news_calendar.py`,
   19 test): RSS fixture parse (offline, urlopen bekçi), stale/dateless/
   irrelevant eleme, geo bölge zorunluluğu, `detect_region` 6 bölge,
   asset-impact yön, YAML calendar load + geçmiş filtre + bozuk dosya →
   DEGRADED (mock yok), calendar→event-risk köprüsü.
4. **Event risk testleri** (`tests/unit/test_event_risk.py`, 17 test):
   high→NO_POSITION_INCREASE, mid→WATCH, low→NONE, unverified ignore,
   en-kısıtlayıcı kazanır, DQS BLOCKED & daily-loss halt event'i ezer,
   candidate yalnızca WATCH/NO_POSITION_INCREASE, no-network bekçi,
   decide_matrix uçtan uca SUSPENDED + event_risk bloğu.
5. **Dashboard görünürlüğü** (selector + registry, page.tsx büyümedi):
   - EventCalendarPanel: event-risk özet banner + per-olay actionability rozeti.
   - NewsPanel: etkilenen sembol rozetleri (↑/↓) / "yalnızca bağlam" rozeti +
     freshness.
   - CapitalRotationPanel: "gerçek 30g momentum + çapraz oran" + UNAVAILABLE
     (veri yetersiz · nötr) durumu.
   - TimeframeMatrixPanel: event-risk banner + hücre `blocked_by` rozeti.
   - selectors: `selectEventRisk`/`headlineImpactBadges` (regime),
     `selectMatrixEventRisk`/`cellBlockedLabel` (decision).
   - OpenAPI + hand-synced TS tipleri additive: `EventRiskView`/
     `EventRiskTrigger` + NewsHeadline/Catalyst/RegimeReport/DecisionMatrix.

## Files changed

- `config/thresholds_v1.0.yaml` — `event_risk` bloğu.
- `config/source_registry_v1.0.yaml` — tlt/hyg/lqd_yfinance (kind: rotation).
- `packages/data/providers/ohlcv/yfinance.py` — TLT/HYG/LQD ticker map.
- `packages/risk/event_risk.py` — yeni (kısıtlayıcı event-risk gate).
- `packages/risk/engine.py` — `evaluate(..., event_candidates=...)`.
- `packages/decision/engine.py` — event candidates wiring + matrix_view event_risk.
- `apps/api/routers/regime_report.py` — additive event_risk + catalyst/headline alanları.
- `contracts/openapi.yaml` — EventRiskView/EventRiskTrigger + additive alanlar.
- `apps/web/types/generated/api.ts` — TS tipleri (additive).
- `apps/web/lib/selectors/{regime,decision}.ts` — yeni selector'lar.
- `apps/web/components/panels/{EventCalendar,News,CapitalRotation,TimeframeMatrix}Panel/index.tsx`.
- `tests/unit/test_event_risk.py`, `tests/unit/test_news_calendar.py` — yeni.

## Tests run

- `pytest` → **191 passed** (36 yeni: 17 event_risk + 19 news_calendar).
- `ruff check packages apps/api apps/tick_worker apps/learning_worker`
  (CI scope) → **All checks passed**.
- `apps/web: tsc --noEmit` → **exit 0**.
- `pnpm build` → **✓ Compiled successfully** (lint + type check dahil).

## Live dashboard smoke

- API (127.0.0.1:8000): `/regime-report/current` 200, `/decision/matrix` 200.
- regime-report: `event_risk={level:NONE,...}` (yakın yüksek-etkili olay yok —
  en yakın CRITICAL FOMC 2026-06-17, ~120h > 72h penceresi, doğru davranış);
  catalyst[0] `event_level:NONE importance:critical`; headline[0]
  `actionable:true freshness:FRESH`.
- decision/matrix: `event_risk.level=NONE`; `risk_gate=NO_POSITION_INCREASE`
  ("6 açık pozisyon" — mevcut paper state davranışı, event'ten bağımsız).
- Rotation (layer "Sermaye Rotasyonu"): score 41 + gerçek evidence —
  **TAHVİL sınıfı ve TLT/SPY oranı artık görünüyor** (TLT/HYG/LQD canlı).
- Web (127.0.0.1:3001, prod build): SSR 200; Olay Takvimi / Haberler /
  Sermaye Rotasyonu / Timeframe Matrisi panelleri render.

## PAPER_SAFE check

- broker: none · real order: none · live execution: none
- RiskGate/DQS/KillSwitch/halt: event riski **yalnızca kısıtlayıcı** —
  max-priority havuzunda; DQS/halt KILL_SWITCH her zaman ezer; size artmaz.
- LLM karar motoruna girmedi; frontend hesap yapmıyor; page.tsx büyümedi.

## SKIPPED / NEXT (bilinçli)

- Asset universe'in kalanı (JNK/IWM/SMH/XLF/FXI + CoinGecko dominance + FRED
  HY spread/real yield/M2/PPI) **eklenmedi**: bunların rotation/consensus'ta
  bir karar rolü yok — yfinance map'e eklemek "ölü veri" üretirdi (prensibe
  aykırı). Bunlar için önce engine rolü (sektör genişliği / EM riski / kredi
  teyidi / makro spread modülü) tasarlanmalı → ayrı NEXT slice.
