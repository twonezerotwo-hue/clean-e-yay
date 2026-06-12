# Current State — Clean E-yAy

_Bu dosya kısa ve güncel tutulur. Her görev sonunda güncellenir._

## Last known status

- **v2.7 D4 — Realized Volatility / Volatility Regime Intelligence tamamlandı**
  (2026-06-12): realized vol + rejim + squeeze/expansion/shock karar zincirine
  **yalnızca kısıtlayıcı** eklendi. Yeni provider `packages/data/providers/
  volatility/` (saf-python engine + orchestrator; mevcut OHLCV cache'inden, EKSTRA
  AĞ YOK; log-getiri annualize realized vol short/medium/long + z-skoru + rejim
  LOW/NORMAL/ELEVATED/EXTREME + squeeze/expansion/shock; bar yetersiz →
  DEGRADED/`insufficient_bars`; runtime mock yok; fixture barlar verified=false).
  - **Gate** (`packages/risk/volatility_risk.py`): yalnızca verified+OK; EXTREME→
    NO_POSITION_INCREASE, ELEVATED→CAUTION ×0.5, shock→en az CAUTION (rejim
    yüksekse block), LOW/squeeze→WATCH (yalnızca bağlam, boost yok). Yön bağımsız.
    size_factor ≤ 1.0 (asla artırmaz). RiskGate hard gate'inden SONRA, yalnızca
    açılış adayına. Timeframe ağırlıklı (15m/1h tam → shock daha etkili; 1d/1w
    block CAUTION'a yumuşar = rejim bağlamı; 1w off).
  - **Entegrasyon**: pipeline `MarketSnapshot.volatility` (symbol→tf); decision
    engine `volatility_report` + blocked_by `volatility_risk:*`; matrix
    `volatility` özeti; `/data/snapshot` volatility alanı; thresholds `volatility.*`.
  - **Sözleşme** additive: openapi `VolatilitySnapshot`/`VolatilitySummary`/
    `VolatilityRegime`/`VolState` + DataSnapshot/DecisionMatrix.volatility + TS
    api.ts senkron (codegen drift yeşil).
  - **Frontend**: `VolatilityPanel` (selector+registry, page.tsx tek GridCell) +
    TimeframeMatrixPanel vol rejim banner + hücre "VOLATİLİTE" rozeti.
  - **266/266 pytest** (+28 D4; live network yok), CI-scope ruff + tsc + pnpm
    build yeşil. Live smoke OK (gerçek OHLCV → verified vol; BTC 1d EXTREME/
    expansion z=2.53). PAPER_SAFE/NO_EXECUTION; RiskGate/DQS/KillSwitch/halt sıfır
    diff, bypass yok.
  - Açık (NEXT): D3 (options IV/skew Deribit), D5 (gerçek haber feed + T3 catalyst
    half-life) ve/veya gerçek replay/backtest motoru.

- **v2.7 D2 — Crypto Derivatives Intelligence tamamlandı** (2026-06-12): kripto
  türev zekâsı (funding / OI / squeeze proxy) karar zincirine **yalnızca
  kısıtlayıcı** eklendi. Yeni provider `packages/data/providers/derivatives/`
  (Binance public futures + deterministik squeeze proxy engine + fixtures +
  orchestrator; crypto-only BTCUSD/ETHUSD, runtime mock yok, live fail →
  DEGRADED). `squeeze_proxy` is_proxy=true — GERÇEK liquidation API'si değil.
  - **Gate** (`packages/risk/derivatives_risk.py`): yalnızca verified+OK; HIGH→
    NO_POSITION_INCREASE, ELEVATED→CAUTION ×0.5, funding-chase→CAUTION,
    contrarian→NONE. size_factor ≤ 1.0 (asla artırmaz). RiskGate hard gate'inden
    SONRA, yalnızca açılış adayına. Timeframe ağırlıklı (15m/1h tam, 1d softens,
    1w off).
  - **Entegrasyon**: pipeline `MarketSnapshot.derivatives`; decision engine
    `derivatives_report` + blocked_by `derivatives_risk:*`; matrix `derivatives`
    özeti; `/data/snapshot` derivatives alanı; thresholds `derivatives.*`.
  - **Sözleşme** additive: openapi `DerivativesSnapshot`/`DerivativesSummary`/
    `SqueezeLevel`/`FundingBias` + TS api.ts senkron (codegen drift yeşil).
  - **Frontend**: `CryptoDerivativesPanel` (selector+registry, page.tsx
    büyümedi) + TimeframeMatrixPanel türev banner + hücre "TÜREV" rozeti.
  - **238/238 pytest** (+29 D2; live network yok), CI-scope ruff + tsc + pnpm
    build yeşil. Live smoke OK. PAPER_SAFE/NO_EXECUTION; RiskGate/DQS/KillSwitch/
    halt sıfır diff, bypass yok.
  - Açık (NEXT): D2 kalan slice'ları (options IV/skew Deribit, realized vol,
    gerçek haber feed + catalyst half-life) ve/veya gerçek replay/backtest motoru.

- **OPS tamamlandı**: contract/replay testleri + codegen drift güvencesi +
  operasyonel sağlamlaştırma. Yeni trading feature YOK; karar zinciri sıfır diff.
  - **Contract testleri** (`tests/contract/`, eskiden boştu): OpenAPI'deki her
    side-effect'siz GET endpoint'i TestClient ile çağrılıp şemaya doğrulanıyor
    (required + enum + `$ref`/`oneOf` recursive; additive serbest). Path drift
    guard (openapi↔router). **Gerçek drift yakaladı**: `LLMMeta.mode` enum'unda
    bare `off`'u YAML `False`'a çeviriyordu → `"off"` tırnaklandı.
  - **Codegen drift guard**: openapi component şema adları + enum üyeleri
    `apps/web/types/generated/api.ts` ile eşleşiyor mu (el-senkron). **Gerçek
    drift yakaladı**: TS `Trade.close_reason`'da `TIME_STOP_EXIT`/`KILL_SWITCH_EXIT`
    eksikti → eklendi. CI `pytest`'i bu testleri otomatik koşar → drift CI'ı kırar.
  - **Replay foundation (dürüst)**: disk snapshot store yok (in-memory `_CACHE`);
    sahte replay üretmedik. `apps/api/routers/replay.py`: `GET /replay/status` +
    `GET /replay/{snapshot_id}` → `status: reserved_not_active`, `available:false`,
    en son okunabilir snapshot id. `ReplayStatusPanel` bu endpoint'e bağlandı
    ("REZERVE · AKTİF DEĞİL" rozeti, dürüst reason).
  - **OpenAPI ↔ runtime reconciliation (additive)**: API'de olup openapi'de eksik
    path'ler + 16 component schema eklendi (TS ile birebir): /data/snapshot,
    /learning/{calibration,calibration/retrain,mistakes,rebalance/proposal},
    /paper-trading/reset, /replay/*. TS: OHLCVBar + replay tipleri; DataSnapshot.mode
    → gerçek `ProvenanceMode` (7 alan).
  - **Dev reliability**: README'ye eski `com.eyay.backend` LaunchAgent (0.0.0.0:8000)
    port çakışması troubleshooting'i + `launchctl bootout`; smoke listesine
    decision/matrix + replay/status. SSL_CERT_FILE/certifi zaten dokümante.
  - **209/209 pytest** (+18 contract/drift; live network yok), ruff (CI scope +
    tests/contract) + tsc + `pnpm build` yeşil. Canlı smoke: Clean API 127.0.0.1:8000
    tüm endpoint 200 (replay reserved), web SSR 200 / 28 panel.
  - PAPER_SAFE/NO_EXECUTION; RiskGate/DQS/KillSwitch/halt sıfır diff.
  - Açık (NEXT): gerçek replay/backtest motoru (disk snapshot store gerekli) ve/veya
    asset-universe 2. slice + v2.7 deep data.

- **P0 intelligence parity (kalan kapsam) tamamlandı**: asset universe
  (rotation bacakları) + news/geo/calendar birim testleri + event risk →
  RiskGate (yalnızca kısıtlayıcı) + dashboard görünürlüğü.
  - **Asset universe**: `ohlcv/yfinance` map'ine TLT/HYG/LQD eklendi
    (source_registry kind: rotation). Rotation motoru artık 9/9 seriyle
    çalışıyor → TAHVİL sınıfı + GLD/TLT + TLT/SPY savunma + HYG/LQD kredi
    oranları **canlıda aktif** (smoke'ta TAHVİL & TLT/SPY evidence göründü).
    DEFAULT_SYMBOLS değişmedi. (JNK/IWM/SMH/XLF/FXI + CoinGecko dominance +
    FRED spread'leri bilinçli ertelendi — engine rolü yok = ölü veri.)
  - **Event risk** (`packages/risk/event_risk.py`): yaklaşan **doğrulanmış**
    yüksek etkili takvim olayı → WATCH / NO_POSITION_INCREASE. `RiskEngine.
    evaluate(event_candidates=...)` aynı havuzda max-priority → DQS KILL_SWITCH
    / halt event'i **her zaman ezer** (bypass yok), event riski gate gevşetmez
    / size artırmaz. `decide_all`/`decide_matrix` `snap.catalysts`'ten besler;
    `matrix_view`+`regime-report` additive `event_risk` bloğu + per-catalyst
    `event_level`. thresholds: `event_risk.{block:24h, watch:72h, high:[high,
    critical]}`.
  - **Dashboard** (selector+registry, page.tsx büyümedi): EventCalendarPanel
    actionability rozeti + banner; NewsPanel etkilenen-sembol rozetleri /
    "yalnızca bağlam" + freshness; CapitalRotationPanel "gerçek 30g momentum +
    oran" + UNAVAILABLE durumu; TimeframeMatrixPanel event-risk banner + hücre
    blocked_by rozeti. OpenAPI + TS tipleri additive (`EventRiskView`).
  - **191/191 pytest** (36 yeni: 17 event_risk + 19 news_calendar; testlerde
    live network yok), ruff (CI scope) + tsc + `pnpm build` yeşil; canlı smoke
    OK. RiskGate/DQS/KillSwitch/halt yalnızca kısıtlayıcı yönde; PAPER_SAFE
    korunuyor.
  - Açık kalan (NEXT): **OPS** (contract/replay + codegen drift); sonra
    asset-universe ikinci slice (sektör/EM/kredi modülleri) ve v2.7 deep data.

- **P0 intelligence parity (çekirdek) tamamlandı**: gerçek rotation engine +
  news/calendar pipeline entegrasyonu.
  - Hash-mock rotation kaldırıldı. `packages/data/providers/rotation/engine.py`
    Clean 1d OHLCV cache üstünde 30g momentum + çapraz oran (GLD/TLT, BTC/GLD,
    TLT/SPY, HYG/LQD, BTC/DXY, GLD/DXY) + sınıf para-akışı (legacy _FLOW_SIGNALS
    parity) hesaplar (deterministik, pure python). `rotation/__init__.
    get_rotation()` motoru OHLCV'ye bağlar: veri yetersiz → RotationView.status=
    UNAVAILABLE + nötr 50 + provider DEGRADED (mock yok). "SPY" slotu registry'deki
    SP500'e (^GSPC) eşli — hisse bacağı canlıda aktif.
  - Pipeline `provider_status`'a news/geo_news/calendar/rotation eklendi;
    news_unavailable / calendar_unavailable / rotation_unavailable warning'leri.
  - Consensus: rotation UNAVAILABLE → quantum modülü düşer, ağırlık
    `_redistribute` ile dağılır (mock skor karar zincirine giremez).
  - 155/155 pytest (5 yeni rotation testi), ruff (CI scope) + tsc yeşil;
    canlı smoke OK (API 200, rotation gerçek momentum/oran evidence; web SSR
    200). RiskGate/DQS/KillSwitch/halt sıfır diff; PAPER_SAFE korunuyor.
  - Açık kalanlar (NEXT): asset universe expansion (TLT/HYG/LQD/JNK/IWM/SMH/
    XLF/FXI + CoinGecko dominance + FRED HY spread/real yield/M2/PPI);
    news/geo/calendar birim testleri; event risk RiskGate bağı.

- **v2.6 tamamlandı**: LLM persona katmanı (Groq, narrative-only).
  LLM karar VERMEZ — sadece state'i açıklar/eleştirir/özetler.
  - `packages/agent/llm/` — client (`LLM_MODE=off|mock|groq`; anahtar
    yoksa network'süz fallback), budget (`data/runtime/llm_budget.json`,
    günlük token bütçesi + per-request limit), cache (2 saat, içerik-digest
    anahtarlı), context (kompakt state — raw market data prompt'a girmez),
    guard (injection/bypass → güvenli ret), report (3 persona: analyst /
    risk_officer / macro_strategist; summary/concerns/evidence_used/
    missing_data/actionability/what_would_change_my_mind; evidence_used
    HER ZAMAN backend'den), chat (state-grounded; sembol/TF/intent algılı
    deterministik grounded yanıt; LLM sadece anlatımı akıcılaştırır).
  - API: `/ai-report/current` additive — personas + llm meta +
    timeframe_summary (TF farkları, candidate vs final, blocked_by,
    paper_actions) + no_actionable_decision (DQS BLOCKED / kısıtlayıcı
    risk gate → verdict no_trade). Yeni **`POST /api/v1/chat`**.
  - Web: AIReportPanel persona bölümleri + LLM_GENERATED/DETERMINISTIC
    rozeti + NO ACTIONABLE banner; ChatPanel gerçek endpoint'e bağlı
    (öneri soruları, evidence satırı, GUARD damgası). Selector
    `lib/selectors/ai.ts`, hook `useChat`; page.tsx büyümedi.
  - Hard kurallar testli: decision matrix LLM'li/LLM'siz birebir aynı;
    bypass talebi → refusal; DQS BLOCKED → no actionable; testlerde
    network çağrısı yok (urlopen bekçi).
  - Pytest **150/150** (18 yeni); ruff (CI scope) + tsc + build yeşil.
  - Not: GROQ_API_KEY env'de yoksa sistem deterministik fallback ile tam
    çalışır; anahtar eklenince kod değişikliği gerekmez.

- **T2 tamamlandı**: timeframe consensus + decision matrix + paper
  time-stop + TimeframeMatrixPanel. Sinyal uzayı (symbol, timeframe).
  - Consensus `build(..., timeframe="1d")` — touche `technicals_by_tf`
    okur (DEGRADED → nötr 50); default'la legacy davranış birebir.
  - Decision: `decide_matrix` 5 TF × symbol; `TradeDecision` candidate_action/
    blocked_by/actionable taşır. **RiskGate önce, timeframe sonra**:
    çarpanlar ≤1.0 clamp (15m ×0.25, 1h ×0.5), 1w paper_execution=false →
    asla open (sadece bias); 1w bias çelişkisi alt TF'i ×0.5 küçültür.
    `matrix_view` ViewModel: hücre rozeti ACTIONABLE/NOT_ACTIONABLE/
    SUSPENDED backend'de; DQS BLOCKED veya kısıtlayıcı risk gate →
    `suspended=true`, tüm hücreler SUSPENDED.
  - Paper: `Position.valid_until` (TF time_stop_hours; 15m→6sa);
    tick'te `TIME_STOP_EXIT` (fiyatsız kapanmaz); Trade timeframe taşır;
    (symbol, tf) bazlı açık-pozisyon dedup; legacy kayıtlar "1d"/None.
  - Learning: fingerprint v2 gerçek TF segmenti — 15m hatası 1d'yi
    cezalandırmaz; router/worker duplicate fingerprint üretimi kaldırıldı
    (d.fingerprint kullanılır). Trainer/calibration global kaldı (bilinçli).
  - API: yeni `GET /api/v1/decision/matrix`; paper tick decide_matrix'e
    geçti (aksiyonlar timeframe taşır). OpenAPI dolduruldu.
  - Web: **TimeframeMatrixPanel** (registry `timeframe_matrix`, span 3) —
    candidate→final, blocked_by tooltip, SUSPENDED banner; DecisionPanel
    mini TF strip; TradingPanel pozisyon TF rozeti + valid_until.
    Selector `lib/selectors/decision.ts`; page.tsx tek GridCell.
  - Env: `make api-dev` + `scripts/dev.sh` certifi varsa `SSL_CERT_FILE`
    otomatik; README'de bölüm.
  - Pytest **132/132** (19 yeni T2); ruff + tsc + build yeşil.

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

- D2 (türev) + D4 (realized vol) bitti. Kalan deep-data slice'ları
  `.tasks/NEXT_TASK.md`'de (her biri ÖNCE karar rolü tasarlanır — ölü veri yasak):
  - **D3 — Options IV / skew (Deribit)**: ATM IV + 25Δ skew → yalnızca kısıtlayıcı
    size kısıtı/contrarian bağlam.
  - **D5 — Gerçek haber feed + T3 catalyst half-life**: RSS → gerçek feed; T0
    `CatalystImpact` contract'ını yarı-ömür motoruyla doldur (haber decay → TF bias).
  - Alternatif: gerçek deterministik replay/backtest motoru (disk snapshot store).
- `.tasks/NEXT_TASK.md` güncellendi.
