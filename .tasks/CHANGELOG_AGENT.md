# Agent Changelog

## 2026-06-12 — v2.7 D5 Real News Feed + Catalyst Half-Life Intelligence
- Yeni motor `packages/data/providers/news/catalyst.py` (kural tabanlı,
  deterministik, LLM/network YOK). Başlık → 13 event_type (geopolitical
  de/escalation, inflation_data, jobs_data, central_bank, oil_supply/inventory,
  crypto_etf_flow, funding_oi_squeeze, earnings, exchange_outage,
  rumor_unverified, unknown). `build_impact` → CatalystImpact (affected_assets =
  event default ∪ başlık tespiti; surprise_level işaretli; valid_until = ts +
  half_life×3; confidence = verified+freshness+relevance). Rumor → verified=False
  (trade'e dönüşmez).
- `packages/risk/catalyst_risk.py`: yalnızca kısıtlayıcı gate (verified + yarı-ömrü
  dolmamış + symbol/TF eşleşen; CONTEXT_ONLY→NONE, WATCH→bağlam, CAUTION→×0.5,
  NO_POSITION_INCREASE→block). Yön bağımsız; size_factor ≤ 1.0.
- Entegrasyon: pipeline `MarketSnapshot.catalyst_impacts` (başlıklardan, ekstra ağ
  yok); decision engine gate volatility'den SONRA + `catalyst_report` + blocked_by
  `catalyst_risk:*`; matrix `catalysts` özeti; `/data/snapshot` catalyst_impacts.
- Sözleşme additive: openapi CatalystImpact genişletildi + CatalystEventType /
  CatalystActionability enum + CatalystSummary + DataSnapshot.catalyst_impacts +
  DecisionMatrix.catalysts; TS api.ts senkron (codegen drift yeşil).
- Frontend: `CatalystImpactPanel` (selector `lib/selectors/catalyst.ts` + registry,
  page.tsx tek GridCell) + TimeframeMatrixPanel catalyst banner + hücre "CATALYST"
  rozeti. NewsPanel (unscheduled) + EventCalendarPanel (scheduled) ayrı.
- Testler: +21 (`tests/unit/test_catalyst.py`). 287/287 pytest, CI-scope ruff +
  tsc + pnpm build yeşil. Live smoke OK (gerçek RSS → central_bank/geopolitical/
  funding_squeeze/etf_flow/rumor; rumor verified=false; matrix catalyst banner;
  RiskGate suspended iken catalyst bypass yok). PAPER_SAFE/NO_EXECUTION;
  RiskGate/DQS/KillSwitch/halt sıfır diff, bypass yok.

## 2026-06-12 — v2.7 D4 Realized Volatility / Volatility Regime Intelligence
- Yeni provider `packages/data/providers/volatility/` (saf-python engine +
  orchestrator). Mevcut OHLCV cache'inden (ekstra ağ YOK) log-getiri tabanlı
  annualize realized vol (short/medium/long pencere) + z-skoru + rejim
  (LOW/NORMAL/ELEVATED/EXTREME) + squeeze/expansion/shock bayrağı. Bar yetersiz
  → DEGRADED (`insufficient_bars`); runtime mock yok; fixture barlar verified=false.
- `packages/risk/volatility_risk.py`: yalnızca kısıtlayıcı gate (EXTREME→
  NO_POSITION_INCREASE, ELEVATED→CAUTION ×0.5, shock→en az CAUTION (rejim yüksekse
  block), LOW/squeeze→WATCH yalnızca bağlam). verified-only, yön bağımsız.
  size_factor ≤ 1.0. Timeframe ağırlıklı (15m/1h tam → shock daha etkili; 1d/1w
  block CAUTION'a yumuşar = rejim bağlamı; 1w off).
- Entegrasyon: pipeline `MarketSnapshot.volatility` (symbol→tf); decision engine
  gate RiskGate'ten SONRA + `volatility_report` + blocked_by `volatility_risk:*`;
  matrix `volatility` özeti; thresholds `volatility.*`; `/data/snapshot`
  volatility alanı.
- Sözleşme additive: openapi `VolatilitySnapshot`/`VolatilitySummary`/
  `VolatilityRegime`/`VolState` + DataSnapshot.volatility + DecisionMatrix.
  volatility; TS api.ts senkron (codegen drift yeşil).
- Frontend: `VolatilityPanel` (selector+registry, page.tsx tek GridCell) +
  TimeframeMatrixPanel vol rejim banner + hücre "VOLATİLİTE" rozeti.
- Testler: +28 (`tests/unit/test_volatility.py`). 266/266 pytest, CI-scope ruff
  + tsc + pnpm build yeşil. Live smoke OK (gerçek OHLCV → verified vol; BTC 1d
  EXTREME/expansion z=2.53). PAPER_SAFE/NO_EXECUTION; RiskGate/DQS/halt bypass yok.

## 2026-06-12 — v2.7 D2 Crypto Derivatives Intelligence
- Yeni provider `packages/data/providers/derivatives/` (binance public futures
  funding/OI + deterministik squeeze proxy engine + offline fixtures +
  orchestrator). Crypto-only (BTCUSD/ETHUSD); runtime mock yok, live fail →
  DEGRADED. squeeze_proxy is_proxy=true (gerçek liquidation değil).
- `packages/risk/derivatives_risk.py`: yalnızca kısıtlayıcı gate (HIGH→
  NO_POSITION_INCREASE, ELEVATED→CAUTION ×0.5, funding-chase→CAUTION,
  contrarian→NONE). verified-only. size_factor ≤ 1.0. Timeframe ağırlıklı
  (15m/1h tam, 1d softens block, 1w off).
- Entegrasyon: pipeline `MarketSnapshot.derivatives`; decision engine gate
  RiskGate'ten SONRA + `derivatives_report` + blocked_by; matrix `derivatives`
  özeti; thresholds `derivatives.*`; `/data/snapshot` derivatives alanı.
- Sözleşme additive: openapi `DerivativesSnapshot`/`DerivativesSummary`/
  `SqueezeLevel`/`FundingBias` + TS api.ts senkron (codegen drift yeşil).
- Frontend: `CryptoDerivativesPanel` (selector+registry, page.tsx büyümedi) +
  TimeframeMatrixPanel türev banner + hücre "TÜREV" rozeti.
- Testler: +29 (`tests/unit/test_derivatives.py`). 238/238 pytest, CI-scope ruff
  + tsc + pnpm build yeşil. Live smoke OK. PAPER_SAFE/NO_EXECUTION; karar
  zincirinde RiskGate/DQS/halt bypass yok.

## 2026-06-11
- Initialized persistent context protocol.
- Added docs for architecture, safety, roadmap, dashboard rules.
- Next task set to G1 real providers.
- G1 completed: CoinGecko/yfinance/FRED providers + orchestrator with
  mock fallback, provider_status tracker, `/api/v1/data/snapshot`
  endpoint, 4 dashboard panels (DataQuality / ProviderStatus / Snapshot
  / MarketData). 12/12 pytest, ruff green.
- G1.1 completed: data policy enforced — runtime mock fallback removed.
  PriceQuote nullable price + verified/status/error; DQS BLOCKED status;
  test-only mock via TEST_USE_MOCK; runtime opt-in PRICE_USE_MOCK shows
  red banner. Frontend panels show "VERİ YOK" / BLOCKED states. 18/18
  pytest, ruff green. DATA_POLICY.md added.
- G2 completed: auto-weight trainer + owner-approved rebalance flow.
  Position/Trade carry data_verified; trainer filters non-verified.
  RebalanceProposal generated when ≥10 verified trades; constraints
  enforced; `/learning/rebalance/{proposal,propose,approve,reject}`.
  Approve writes weights_v1.x.yaml + manifest, consensus reads via
  load_active_weights(). 2 dashboard panels (WeightProposal,
  WeightHistory). 26/26 pytest, ruff green.
- G6 completed: confidence calibration tam entegrasyon. Decision engine
  raw → Platt-calibrated p(win) üretir; RiskGate'i bypass etmez.
  Position/Trade calibration trio taşır; trainer verified+predicted
  filter eder; MIN_SAMPLES=10 altında identity. New endpoints
  /learning/calibration[/retrain] + CalibrationPanel. 36/36 pytest,
  ruff green.
- G3 completed: mistake memory gate. verified+fingerprint'li closed
  trade'lerden AVOID/BOOST/WARNING/NEUTRAL verdict; decision engine
  consensus eşiği aşıldıktan sonra applies; RiskGate hard gate'leri
  bypass etmez (KILL_SWITCH > BOOST, DQS BLOCKED > BOOST). Yeni
  endpoint /learning/mistakes + MistakeMemoryPanel. 47/47 pytest,
  ruff green.
- L (local live dev) completed: scripts/dev.sh + Makefile dev/api-dev/
  web-dev/compose-up, apps/web/.env.example, client reads
  NEXT_PUBLIC_API_BASE_URL (fallback NEXT_PUBLIC_API_BASE), API CORS
  3000/3001/DEV_CORS, docker-compose.dev.yml, README "Run locally".
  Canlı doğrulandı: 6 API endpoint 200, web HTML 25 panel + HeroScene
  canvas + PAPER_ONLY banner.
- Next task → G4 correlation-aware sizing.
- Provenance mode block commit'lendi (önceki oturum işi): LIVE/MOCK_MODE/
  SIMULATION/INSUFFICIENT_DATA damgası + module_health data/news durumu.
- G4 completed: correlation-aware sizing. Verified trade PnL'den 30g
  pairwise rho (computed→baseline→neutral fallback); aynı yönlü |rho|≥0.7
  cluster toplamı ≥%30 equity → hold, ≥%15 → size×0.5; ters yön hedge
  ayrı; asla size artırmaz; RiskGate/DQS bypass yok. Yeni endpoint
  /risk/correlation + CorrelationPanel (heatmap + cluster uyarıları) +
  TradingPanel cluster satırları. 72/72 pytest, ruff + tsc + build yeşil;
  SSR'de 26 panel doğrulandı.
- Next task → G5 daily-loss / max-DD halt.
- G5 completed: daily-loss / max-DD halt. File-backed halt store
  (RISK_HALT_PATH); breach tick'te persist; DAILY_LOSS→KILL_SWITCH
  (flatten KILL_SWITCH_EXIT), MAX_DRAWDOWN→RISK_REDUCE (yeni açılış yok);
  otomatik reset yok, sadece owner reset endpoint'i; RiskGate bypass yok.
  Yeni endpoint'ler /risk/halts + /risk/halts/reset; DrawdownGuardPanel
  (gauge'lar + timeline + reset) + TradingPanel RISK FREEZE badge.
  85/85 pytest, ruff + tsc + build yeşil; SSR'de 27 panel doğrulandı.
- Next task → v2.6 LLM persona (Groq, narrative-only).
- Mimari değerlendirme: timeframe first-class dimension raporu kabul
  edildi; v2.6 ertelendi → yeni sıra T0→T1→T2→v2.6 (T3 half-life motoru
  v2.7 deep data ile).
- T0 completed: timeframe contracts + schema seeding. Timeframe Literal
  (15m/1h/4h/1d/1w); Position/Trade/TradeDecision.timeframe default "1d"
  (legacy uyumlu); technicals_by_tf taslağı; fingerprint v2 (TF segmenti,
  legacy çakışmaz, NEUTRAL karantina); thresholds.timeframe_risk (1w
  paper_execution=false, çarpanlar ≤1.0); CatalystImpact +
  TimeframeDecision/DecisionMatrix OpenAPI şemaları (motor/endpoint yok);
  web'de sadece types. Runtime logic sıfır diff. 94/94 pytest, ruff +
  tsc + build yeşil.
- Next task → T1 OHLCV provider + gerçek multi-TF technicals.

## 2026-06-12
- T1 completed: OHLCV provider + gerçek multi-TF technicals. Hash-mock
  teknik üretim kaldırıldı; CoinGecko market_chart + Yahoo chart
  adapter'ları, disk cache (TF orantılı TTL, stale-cache fallback),
  resample (4h=1h bucket, 1w=1d ISO hafta, source="resampled:<base>"),
  gerçek RSI/MACD/ATR/EMA-stack (yetersiz bar → None + DEGRADED, mock
  yok), TF bazlı freshness (15m>30dk ... 1w>10g), technicals_by_tf
  5 TF × 4 sembol dolu, legacy technicals 1d'den beslenir.
  /data/snapshot additive technicals_by_tf; OpenAPI'ye OHLCVBar +
  TechnicalSnapshotTF. Web: MarketDataPanel TF chip satırı +
  SnapshotPanel TF kapsama (selector'larla). RiskGate/DQS/halt sıfır
  diff; consensus/decision hâlâ 1d (T2). 113/113 pytest (19 yeni),
  ruff + tsc + build yeşil.
- Next task → T2 timeframe consensus + decision + paper (time-stop) +
  TimeframeMatrixPanel.
- T2 completed: sinyal uzayı (symbol, timeframe). Consensus build TF
  parametresi (touche technicals_by_tf'ten, DEGRADED→nötr); decide_matrix
  5 TF × symbol + matrix_view ViewModel (candidate/final/blocked_by/
  ACTIONABLE-NOT_ACTIONABLE-SUSPENDED rozetleri backend'de); RiskGate
  önce, timeframe sonra (çarpan ≤1.0: 15m×0.25 1h×0.5; 1w paper açmaz,
  bias çelişkisi alt TF ×0.5); paper valid_until + TIME_STOP_EXIT
  (fiyatsız kapanmaz, legacy "1d"/None); fingerprint v2 gerçek TF —
  15m hatası 1d'yi cezalandırmaz; aynı sembol farklı TF cluster'da
  birlikte (rho=1, testli). Yeni GET /decision/matrix; paper tick +
  tick_worker decide_matrix'e geçti. Web: TimeframeMatrixPanel +
  DecisionPanel TF strip + TradingPanel TF/valid_until. make api-dev +
  dev.sh SSL_CERT_FILE'ı certifi'den otomatik ayarlar (README bölümü).
  132/132 pytest (19 yeni), ruff + tsc + build yeşil.
- Next task → v2.6 LLM persona (Groq, narrative-only); T3 catalyst
  half-life → v2.7 deep data ile.
- v2.6 completed: LLM persona katmanı (narrative-only, karar vermez).
  packages/agent/llm — LLM_MODE=off|mock|groq, Groq adapter (anahtarsız/
  hatada network'süz deterministik fallback), günlük token budget +
  per-request limit, 2 saatlik içerik-digest cache, kompakt state context
  (raw data prompt'a girmez), injection guard (TR+EN, bypass → ret),
  3 persona (analyst/risk_officer/macro_strategist; evidence_used hep
  backend'den), state-grounded chat. /ai-report/current additive
  (personas, llm meta, timeframe_summary, no_actionable_decision);
  yeni POST /api/v1/chat. Web: AIReportPanel persona bölümleri +
  provenance rozeti + NO ACTIONABLE banner; ChatPanel canlı endpoint'e
  bağlı. Decision matrix LLM'li/LLM'siz birebir aynı (testli); RiskGate/
  DQS/KillSwitch/halt sıfır diff. 150/150 pytest (18 yeni), ruff + tsc +
  build yeşil; canlı smoke OK (28 panel SSR, PAPER_ONLY korunuyor).
- Next task önerisi → OPS (contract/replay testleri; TS tip drift riski)
  → sonra v2.7 deep data + T3 catalyst half-life.
- P0 intelligence parity (kısmî) — gerçek RSS/geo news + event calendar
  YAML + **gerçek rotation engine**. Hash-mock rotation kaldırıldı:
  `providers/rotation/engine.py` Clean 1d OHLCV cache üstünde 30g momentum +
  çapraz oran (GLD/TLT, BTC/GLD, TLT/SPY, HYG/LQD, BTC/DXY, GLD/DXY) + sınıf
  para-akışı (legacy _FLOW_SIGNALS parity) hesaplar; deterministik, pure
  python. `providers/rotation/__init__.get_rotation()` motoru OHLCV'ye bağlar:
  veri yetersiz → RotationView.status=UNAVAILABLE, nötr 50, provider DEGRADED
  (mock yok). SPY slotu Clean registry'deki SP500'e (^GSPC) eşlendi → hisse
  bacağı canlıda aktif. Pipeline: provider_status'a news/geo_news/calendar/
  rotation eklendi; news_unavailable / calendar_unavailable / rotation_
  unavailable warning'leri. Consensus: rotation UNAVAILABLE → quantum modülü
  düşer, ağırlık _redistribute ile dağıtılır (mock skor karar zincirine
  girmez). RiskGate/DQS/KillSwitch/halt sıfır diff; PAPER_SAFE/NO_EXECUTION.
  155/155 pytest (5 yeni rotation testi), ruff (CI scope) + tsc yeşil; canlı
  smoke OK (API 200, gerçek fiyatlarla rotation OK + gerçek momentum/oran
  evidence; web SSR 200, paneller mevcut). pnpm build atlandı (frontend sıfır
  diff + canlı Clean dev sunucusunu bozmamak için; tsc temiz).
- SKIPPED/NEXT → asset universe expansion (TLT/HYG/LQD/JNK/IWM/SMH/XLF/FXI +
  CoinGecko dominance + FRED HY spread/real yield/M2/PPI); news/geo/calendar
  birim testleri (RSS fixture parse / geo classification / YAML load); event
  risk RiskGate bağı (kısıtlayıcı WATCH/NO_POSITION_INCREASE).
- P0 intelligence parity (kalan kapsam) tamamlandı: (1) **Asset universe** —
  `ohlcv/yfinance` map'ine TLT/HYG/LQD eklendi (source_registry kind:rotation,
  fallback_to_mock:false); rotation 9/9 seriyle çalışıyor → TAHVİL sınıfı +
  GLD/TLT + TLT/SPY + HYG/LQD oranları canlıda aktif (smoke doğruladı).
  JNK/IWM/SMH/XLF/FXI + CoinGecko dominance + FRED bilinçli ertelendi (engine
  rolü yok = ölü veri). (2) **Event risk** — yeni `packages/risk/event_risk.py`:
  yaklaşan doğrulanmış yüksek-etkili olay → WATCH/NO_POSITION_INCREASE.
  `RiskEngine.evaluate(event_candidates=...)` aynı havuzda max-priority → DQS
  KILL_SWITCH/halt event'i her zaman ezer (bypass yok), event riski gate
  gevşetmez/size artırmaz. decide_all/decide_matrix snap.catalysts'ten besler;
  matrix_view+regime-report additive event_risk bloğu + per-catalyst
  event_level. thresholds.event_risk {block:24h,watch:72h,high:[high,critical]}.
  (3) **Birim testleri** — test_event_risk.py (17) + test_news_calendar.py (19):
  RSS fixture parse/geo/asset-impact, YAML load+bozuk dosya DEGRADED, event-risk
  taksonomisi, DQS/halt bypass yok, decide_matrix uçtan uca; testlerde live
  network yok. (4) **Dashboard** (selector+registry, page.tsx büyümedi):
  EventCalendarPanel actionability rozeti+banner; NewsPanel etkilenen-sembol
  rozetleri / "yalnızca bağlam" + freshness; CapitalRotationPanel gerçek
  evidence + UNAVAILABLE; TimeframeMatrixPanel event-risk banner + hücre
  blocked_by rozeti. OpenAPI + TS tipleri additive (EventRiskView). 191/191
  pytest (36 yeni), ruff (CI scope) + tsc + pnpm build yeşil; canlı smoke OK
  (regime-report/matrix 200, event_risk serialize, rotation TAHVİL/TLT-SPY
  evidence, web SSR 200). PAPER_SAFE/NO_EXECUTION; RiskGate/DQS/KillSwitch/halt
  yalnızca kısıtlayıcı yönde.
- OPS completed: contract/replay testleri + codegen drift güvencesi + dev
  reliability. (1) **Contract** (`tests/contract/`, eskiden boş): openapi'deki
  her side-effect'siz GET TestClient'la şemaya doğrulanıyor (required+enum+
  $ref/oneOf recursive, additive serbest) + path drift guard. (2) **Codegen
  drift guard**: openapi şema adları + enum üyeleri api.ts ile eşleşiyor mu;
  CI pytest'inde koşar → drift CI'ı kırar. İki gerçek drift yakalandı &
  düzeltildi: openapi `LLMMeta.mode` bare `off` → YAML False'a dönüyordu
  (→`"off"`); TS `Trade.close_reason`'da TIME_STOP_EXIT/KILL_SWITCH_EXIT eksikti.
  (3) **Replay foundation (dürüst)**: disk snapshot store yok → sahte replay
  üretmedik; `routers/replay.py` `GET /replay/status` + `/replay/{id}` →
  reserved_not_active + en son okunabilir snapshot; ReplayStatusPanel bağlandı.
  (4) **OpenAPI↔runtime additive reconciliation**: eksik path'ler (/data/snapshot,
  /learning/{calibration,calibration/retrain,mistakes,rebalance/proposal},
  /paper-trading/reset, /replay/*) + 16 component schema eklendi (TS ile birebir);
  TS OHLCVBar + replay tipleri + DataSnapshot.mode→ProvenanceMode. (5) **Dev
  reliability**: README eski com.eyay.backend LaunchAgent (0.0.0.0:8000) port
  çakışması + launchctl bootout; smoke listesi genişledi. 209/209 pytest (+18),
  ruff + tsc + pnpm build yeşil; canlı smoke OK (Clean API 127.0.0.1:8000 tüm
  endpoint 200 + replay reserved, web SSR 200 / 28 panel). RiskGate/DQS/KillSwitch/
  halt sıfır diff; PAPER_SAFE korunuyor.
- Next task → v2.7 deep data (karar rolü önce) VEYA asset universe 2. slice.
