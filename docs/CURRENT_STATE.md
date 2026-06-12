# Current State — Clean E-yAy

_Bu dosya kısa ve güncel tutulur. Her görev sonunda güncellenir._

## Last known status

- **T1 tamamlandı**: OHLCV provider + gerçek multi-timeframe technicals.
  - `packages/data/providers/ohlcv/` — CoinGecko market_chart (BTC/ETH) +
    Yahoo chart (XAU/XAG/DXY/VIX/...) adapter'ları; disk cache
    (`data/runtime/ohlcv/`, TTL: 15m→5dk ... 1d→6sa); live fail → stale
    cache → boş liste (runtime'da mock/fixture bar ASLA yok).
  - Resample: **4h = 1h bucket**, **1w = 1d ISO hafta** (kripto; yfinance
    1w native); resampled barlar `source="resampled:<base>"`.
  - Gerçek indikatörler: RSI(14)/ATR(14) Wilder, MACD(12/26/9) histogram
    normalize (hist/close×100), EMA stack 20/50/200. Yetersiz bar →
    alanlar None + `TechnicalSnapshot.status="DEGRADED"`, score nötr 50.
  - TF bazlı freshness: 15m>30dk, 1h>2sa, 4h>8sa, 1d>48sa, 1w>10g →
    DEGRADED. Global DQS (fiyat bazlı) ve RiskGate davranışı değişmedi.
  - `MarketSnapshot.technicals_by_tf` dolu (5 TF × DEFAULT_SYMBOLS[:4]);
    legacy `technicals` = 1d snapshot'ın kendisi (geriye uyum).
    `/data/snapshot` additive `technicals_by_tf` döner; OpenAPI'ye
    `OHLCVBar` + `TechnicalSnapshotTF` eklendi.
  - Frontend minimum görünürlük: `MarketDataPanel` TF chip satırı,
    `SnapshotPanel` "TF teknikleri x/y OK"; selector'lar
    `lib/selectors/snapshot.ts`. Panel/page.tsx büyümedi
    (TimeframeMatrixPanel T2'de).
  - Consensus/decision hâlâ yalnızca legacy 1d okur — multi-TF karar T2.
  - Pytest **113/113** (19 yeni T1); ruff + tsc + build yeşil.

- **T0 tamamlandı**: timeframe-first contracts + schema seeding (runtime
  davranış değişmedi, tamamı additive/backward-compatible).
  - `Timeframe = Literal["15m","1h","4h","1d","1w"]` (`data/types.py`);
    `TechnicalSnapshot.timeframe` genişledi; provider passthrough.
  - `Position`/`Trade`/`TradeDecision` → `timeframe` alanı (default "1d";
    legacy JSON kayıtları default ile yüklenir).
  - `MarketSnapshot.technicals_by_tf` opsiyonel taslak (None — T1 doldurur).
  - **Fingerprint v2**: `asset|v2|tf|regime|...` — legacy ile çakışmaz;
    eski kayıtlar doğal karantinada (NEUTRAL fallback).
  - `thresholds.timeframe_risk`: 15m scout ×0.25 / 1h ×0.5 / 4h ×1.0 /
    1d ×1.0 / 1w ×0.0 + `paper_execution: false` (1w trade açamaz).
    Tüm çarpanlar ≤1.0 — sadece risk azaltıcı.
  - `CatalystImpact` contract'ı (Pydantic + OpenAPI) tanımlı — motor
    v2.7'de. `TimeframeDecision`/`DecisionMatrix` OpenAPI taslakları T2 için.
  - Frontend: sadece types (Timeframe/CatalystImpact/TimeframeDecision/
    DecisionMatrix + Position/Trade.timeframe) — panel T2/T4'te.
  - Pytest **94/94** (9 yeni T0); ruff + tsc + build yeşil.
- **v2.6 LLM persona ertelendi** → T1+T2 sonrası (bkz. ROADMAP).

- **G5 tamamlandı**: daily-loss / max-DD halt — file-backed, sadece risk
  azaltıcı.
  - `packages/risk/halt.py` — breach tespiti tick yollarında
    `sync(risk_input)` ile persist edilir (`RISK_HALT_PATH`, default
    `data/runtime/risk_halts.json`). DAILY_LOSS → KILL_SWITCH seviyesi,
    MAX_DRAWDOWN → RISK_REDUCE seviyesi. **Otomatik reset yok** — halt
    sticky; yalnızca `POST /api/v1/risk/halts/reset` (owner) kapatır.
  - `packages/risk/engine.py` — aktif halt ek candidate olarak okunur
    (sadece kısıtlayıcı; mevcut gate'ler değişmedi).
  - KILL_SWITCH halt → `flatten_all` (KILL_SWITCH_EXIT) paper tick +
    tick_worker'da; fiyatı olmayan pozisyon kapatılmaz (mock fiyat yok).
    RISK_REDUCE halt → yeni açılış yok, SL/TP yönetimi sürer.
  - `GET /api/v1/risk/halts` — aktif halt + timeline + gauge metrikleri
    (daily_loss_ratio, drawdown_ratio — frontend hesap yapmaz).
- **Frontend (G5)**: `DrawdownGuardPanel` — DailyLossGauge + MaxDDGauge
  (oran bazlı bar gauge) + KillSwitchTimeline + Owner Reset butonu;
  `TradingPanel` "RISK FREEZE" badge. Selector `lib/selectors/halts.ts`;
  registry `drawdown_guard`; page.tsx'e tek GridCell.
- Pytest: **85/85** yeşil (13 yeni G5 testi). Ruff + tsc + build yeşil.
- Canlı: `/api/v1/risk/halts` 200; SSR'de **27 panel**
  (`drawdown_guard` dahil), HeroScene + PAPER_ONLY korunuyor.

- **G4 tamamlandı**: correlation-aware sizing — sadece risk azaltıcı.
  - `packages/risk/correlation.py` — verified kapalı trade'lerin günlük
    PnL serisinden 30g pencerede pairwise rho (`computed`); ortak gün <
    `correlation_min_overlap_days` (5) → config `correlation_baseline`
    (`baseline`, örn. BTC↔ETH=0.75, XAU↔XAG=0.80); o da yoksa `neutral`
    (rho=0, `insufficient_correlation_data` uyarısı, adjustment yok).
  - `cluster_exposure(open_positions, aday)` — işaretli hizalama
    rho×side×side ≥ 0.7 → aynı risk cluster; ≤ -0.7 → hedge (ayrı
    raporlanır, cap'e girmez). Cluster toplamı ≥ `max_cluster_pct`
    (0.30 equity) → size_factor 0 (hold); ≥ yarısı → ×0.5. **Asla
    artırmaz** (factor ≤ 1.0).
  - `packages/decision/engine.py` — mistake gate'ten sonra cluster cap;
    TradeDecision `cluster_report` taşır. decide_all `open_positions`
    parametresi aldı (paper_trading router + tick_worker geçirir).
  - **Hard kural**: correlation sizing **RiskGate'i bypass etmez**.
    KILL_SWITCH→blocked, RISK_REDUCE/NO_POSITION_INCREASE→hold; DQS<55
    BLOCKED → trade yok.
  - `GET /api/v1/risk/correlation` — matris + open-position cluster'ları
    (union-find, OK/WARNING/BREACH) + insufficient_pairs.
- **Frontend**: `CorrelationPanel` — matrix heatmap (cyan=+, magenta=-)
  + cluster exposure uyarıları; `TradingPanel` flagged cluster satırları
  gösterir. Yeni selector `lib/selectors/correlation.ts`; panel-registry
  `correlation` girişi; page.tsx'e tek GridCell.
- Ayrıca commit'lendi: **provenance mode block** (önceki oturumdan) —
  LIVE/MOCK_MODE/SIMULATION/INSUFFICIENT_DATA damgası dashboard/ai-report
  endpoint'lerinde.
- Pytest: **72/72** yeşil (14 yeni G4 testi: neutral/baseline/computed
  fallback sırası, verified filtresi, REDUCED/CAPPED, hedge, engine cap→
  hold, size×0.5, hedge full size, KILL_SWITCH > correlation, DQS
  BLOCKED → trade yok, endpoint 200 + BREACH cluster).
- Ruff (CI scope): yeşil. Web: `tsc --noEmit` + `pnpm build` yeşil.
- Canlı doğrulandı: `/api/v1/risk/correlation` 200; web SSR'de **26
  panel** (`data-panel="correlation"` dahil), HeroScene canvas +
  PAPER_ONLY banner korunuyor.

- **Local live dev**: `make dev` → API (8000) + web (3000).
  Docker alternatifi: `docker compose -f docker-compose.dev.yml up`.

## Next task

- **T2** — timeframe consensus + decision + paper (time-stop) +
  TimeframeMatrixPanel.
- `.tasks/NEXT_TASK.md` T2 için hazır.
