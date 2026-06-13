# Current State — Clean E-yAy

_Bu dosya kısa ve güncel tutulur. Her görev sonunda güncellenir._

## Last known status

- **P1 — Paper Lifecycle Finalization tamamlandı** (2026-06-13): paper trading
  yaşam döngüsü backend'de net, güvenli, **audit edilebilir** ve öğrenmeye hazır.
  PAPER_SAFE / NO_EXECUTION sıfır diff; fiyat yoksa **fake kapanış yok**;
  RiskGate/DQS/KillSwitch/halt bypass yok.
  - **Lifecycle state machine** (`packages/paper/`): Position `lifecycle_status`
    OPEN → EXPIRED_PENDING_PRICE / EXIT_PENDING / ERROR_STATE → terminal Trade
    (CLOSED / FORCE_CLOSED). `time_stop_expired`, `pending_exit_reason` additive.
    Time-stop: fiyat varsa TIME_STOP_EXIT, yoksa EXPIRED_PENDING_PRICE (sonraki
    tick'te fiyat gelince kapanır; negatif geri sayım yok).
  - **Tek açılış yolu** `lifecycle.attempt_open` (tick_worker + paper router ortak,
    drift yok): duplicate/scale-in politikası — aynı (symbol, timeframe) yön fark
    etmeksizin bloklanır (no hedge/flip); farklı TF serbest; `scale_in=True`
    explicit'te açılır.
  - **Audit trail** (yeni `packages/paper/audit.py`, append-only
    `data/runtime/paper_audit.jsonl`): OPEN_ATTEMPT/OPENED/OPEN_BLOCKED/
    TIME_STOP_EXPIRED/EXIT_PENDING/CLOSED/KILL_SWITCH_EXIT/STATE_REPAIRED;
    best-effort (lifecycle'ı patlatmaz), bozuk satır okumada atlanır.
  - **State robustness** (`packages/paper/state.py`): `schema_version`, atomik
    yazım (temp+os.replace), corrupt → yedek + temiz default (crash yok),
    legacy/forward-uyumlu yükleme (bilinmeyen alan atlanır, eksik default'a düşer).
  - **Learning handoff**: Trade'e `open_reason`/`snapshot_id`/`lifecycle_status`
    additive (mevcut learning okuyucuları bozulmadı).
  - **API additive**: `/paper-trading/state` → `new_entries_disabled`,
    `duplicate_warning`, `audit_summary`, `recent_audit_events`; Position/Trade
    lifecycle alanları. openapi + TS api.ts senkron (codegen drift yeşil).
    PaperActionPanel: EXPIRED/EXIT_PENDING "fiyat bekleniyor" + duplicate uyarısı.
  - **393 pytest** (+18), ruff CI-scope + tsc + pnpm build yeşil, live smoke
    (health/tick/paper-state/dashboard/cockpit + web SSR 200) OK.

- **R2 — Deterministic Rolling Backtest Runner tamamlandı** (2026-06-13): kayıtlı
  snapshot serisi (`packages/data/snapshot_store.py`) üzerinde **deterministik**
  outcome ölçümü. Live provider refetch YOK, sahte geçmiş YOK, look-ahead YOK
  (outcome yalnızca GERÇEK gelecek snapshot'larla; karar zamanından sonraki İLK
  gözlemle ölçülür). PAPER_SAFE / NO_EXECUTION: backtest emir üretmez, paper
  açmaz, RiskGate bypass etmez, decide_matrix'i yeniden çalıştırmaz.
  - **Runner** (`packages/data/backtest.py`, saf fonksiyon): 15m/1h/4h/1d horizon;
    metrikler `hit_rate / false_positive / false_negative / avg_return /
    max_drawdown / blocked_decision_accuracy`, `per_timeframe / per_symbol /
    per_horizon`; bloklanmış aday-açılışlar counterfactual (blok doğru muydu?).
    Yetersiz örnekte oran null (uydurma 0 değil). `snapshot_store.all_docs()`
    kronolojik okuma helper'ı eklendi.
  - **Endpoint**: `GET /api/v1/replay/backtest` + `GET /api/v1/replay/backtest/{run_id}`
    (literal route, `{snapshot_id}` catch-all'undan ÖNCE). Dürüst durum: boş store
    → `insufficient_snapshots`, ölçülebilir gelecek yok → `insufficient_future_data`
    (ikisi de 200). `run_id` store üzerinde deterministik; sahte geçmiş run
    saklanmaz (eşleşmezse 404 + current_run_id).
  - **Sözleşme additive**: openapi `/replay/backtest(/{run_id})` +
    `ReplayBacktest`/`ReplayBacktestMetrics`; TS api.ts senkron (codegen drift
    yeşil). **375 pytest**, ruff CI-scope + tsc + pnpm build yeşil, live smoke
    (`/replay/status`, `/replay/backtest`, `/dashboard/state`) OK.

- **UX1 — Agent Operating Cockpit tamamlandı** (2026-06-13): dashboard "veri
  çöplüğü"nden operating cockpit'e çevrildi — ilk ekranda agent'ın beyni okunur
  (işlem açabilir mi, açamıyorsa **tek** ana sebep ne, ne yapmak istedi, neden
  değişti, ne izliyor). Yeni trading feature / data provider / intelligence
  module YOK; RiskGate/DQS/KillSwitch/halt SIFIR diff. Frontend hesap yapmaz —
  tüm türetilmiş alanlar backend ViewModel'inden. PAPER_SAFE / NO_EXECUTION.
  - **Backend ViewModel** (`packages/decision/cockpit.py`, saf fonksiyonlar):
    `compute_main_blocker` TEK ana engel ("veya" YOK; öncelik DQS_BLOCKED/
    PROVIDER_DOWN > HALT/kill-switch > RISK_GATE > NONE), `compute_data_mode`
    (LIVE_VERIFIED/LIVE_DEGRADED/PARTIAL_FALLBACK/SIMULATION/BLOCKED),
    `compute_status` (ACTIONABLE/NO_ACTION/WATCHING/FROZEN/BLOCKED),
    `agent_brief_view` (status/can_act/main_blocker/summary/data_mode/dqs/risk/
    top_blockers/top_candidates/next_watch_conditions/recommended_stance/
    paper_state_summary), `decision_trace_view` (candidate→final/blocked_by/
    restrictive_gates/paper_action/evidence_refs), `next_watch_conditions`.
  - **Endpoint**: `GET /api/v1/cockpit/brief` → {agent_brief, decision_trace}
    (decide_matrix+matrix_view'i diğerleriyle aynı okur, yalnızca ÖZET üretir).
  - **Tek ana engel**: report.py no_actionable/change_mind + DecisionPanel artık
    tek main_blocker yazar ("DQS BLOCKED veya risk gate kısıtlayıcı" silindi).
  - **Paper time-stop**: paper_trading `_time_stop_status` (NONE/ACTIVE/EXPIRED +
    remaining ≥0) — additive serileştirme, negatif geri sayım YOK (logic değişmedi).
  - **Learning**: summary `min_sample=20`/`sample_sufficient` → INSUFFICIENT SAMPLE.
  - **Sözleşme additive**: openapi /cockpit/brief + CockpitBrief/AgentBrief/
    DecisionTrace/MainBlocker/WatchCondition + enum'lar; Position time_stop_*;
    LearningSummary min_sample/sample_sufficient. TS api.ts senkron (drift yeşil).
  - **Frontend**: lib/selectors/cockpit.ts + useCockpitBrief. Yeni paneller
    AgentBriefPanel (üstte tek ana kart, HeroScene üzerinde) / DecisionTracePanel /
    WatchConditionsPanel / PaperActionPanel; Ask the Agent = ChatPanel. page.tsx
    Simple grid + "Uzman / Detaylar" `<details>` collapsed; registry tier
    simple|expert. TimeframeMatrix global-suspended tek banner + sade hücre;
    AgentVotes → evidence chain; CommandSignals → "Aday Sinyalleri" +
    NOT_ACTIONABLE; Replay → Uzman/Detaylar.
  - **366/366 pytest** (+16 cockpit), CI-scope ruff + tsc + pnpm build yeşil.
    **Live smoke** (izole API 8011 gerçek veri + web SSR 3100 prod build):
    cockpit/brief WATCHING/RiskGate tek engel (no "veya"); ai-report no_actionable
    tek engel; learning INSUFFICIENT SAMPLE; matrix 20/20 suspended; SSR 200
    "Agent Brief" üstte + HeroScene + PAPER_ONLY + Uzman/Detaylar + 36 panel.
    RiskGate/DQS/KillSwitch/halt sıfır diff, bypass yok.
  - Açık (NEXT): R2 deterministic rolling replay/backtest runner VEYA cockpit
    cilası (panel drag-drop düzeni, görünürlük tercih kalıcılığı).

- **R1 — Real Snapshot Replay / Backtest Foundation tamamlandı** (2026-06-13):
  replay artık `reserved_not_active` değil — gerçek **disk snapshot store**
  üzerinden çalışan minimal, dürüst replay foundation. Sahte backtest / uydurma
  geçmiş performans YOK. PAPER_SAFE / NO_EXECUTION: replay emir üretmez, paper
  pozisyon açmaz, RiskGate'i bypass etmez, LLM'e bağlanmaz, live provider çağırmaz.
  - **Store** (`packages/data/snapshot_store.py` — ARCHITECTURE §3'te zaten tanımlı
    olan dosya; yeni katman değil): atomik write (temp + `os.replace`), bozuk dosya
    → crash yok (okunurken atlanır), `latest()`/`get(id)`/`status()`/`count()`,
    zaman-sıralı dosya adı (`<ts>__<safe_id>.json`), ring-buffer prune
    (`SNAPSHOT_STORE_MAX`, default 500), aynı id en güncelse duplicate yazmaz.
    Path: `data/runtime/snapshots/` (env `SNAPSHOT_STORE_PATH`; testte temp dir).
    Kayıt alanları: schema_version, snapshot_id, generated_at, mode (provenance),
    dqs, provider_status, data_snapshot (compact prices+warnings), decision_matrix
    (matrix_view tam çıktısı — risk_gate + cells + options/vol/türev/catalyst/
    event_risk özetleri), risk_state, paper_state_summary.
  - **Producer**: `apps/tick_worker/main.py::run_once()` her tick'te matrix_view'i
    store'a kaydeder (store yazımı ASLA tick'i patlatmaz — try/except + log).
  - **Endpoint'ler** (`apps/api/routers/replay.py`, live refetch YOK):
    `GET /replay/status` → active/empty + mode (active_snapshot_replay /
    insufficient_snapshots / reserved_not_active) + snapshot_count + latest id/zaman;
    `GET /replay/{id}` → kayıtlı snapshot zarfı (yoksa 404 not_found);
    `GET /replay/{id}/decision-trace` → kayıtlı decision_matrix'ten karar izi
    (snapshot_id/generated_at/mode/DQS/RiskGate/top candidates/final decisions/
    blocked_by/paper actions/provider issues/catalyst+options+vol+türev özetleri).
    Hepsi yalnızca store'dan okur; yeni karar HESAPLAMAZ.
  - **Sözleşme** (additive + drift-safe): openapi `ReplayStatus` güncellendi +
    yeni `ReplaySnapshot` / `ReplayDecisionTrace` + `/replay/{id}/decision-trace`
    path; `ReplaySnapshotStatus` kaldırıldı. TS api.ts senkron (`ReplayStoreStatus`/
    `ReplayMode`/`ReplayExecution` enum literalleri + tipler). Codegen drift + contract
    testleri yeşil (eski reserved testi → 404 not_found testine güncellendi).
  - **Frontend**: ReplayStatusPanel artık store status + mode rozeti +
    snapshot_count + latest id/zaman + "NO LIVE EXECUTION" rozeti + "Replay does
    not execute trades" notu gösterir. Selector `lib/selectors/replay.ts`; page.tsx
    büyümedi (mevcut GridCell).
  - **349/349 pytest** (+15: store atomik/latest/by-id/missing/corrupted/dedup/
    prune/status, endpoint empty+active, found+404, decision-trace stored-matrix,
    "replay live refetch yapmaz" (pipeline boom guard), tick_worker producer
    offline; +2 contract 404 testi). CI-scope ruff + tsc + pnpm build yeşil.
    **Live smoke** (izole API 8011, gerçek veri + bir gerçek snapshot seed'lendi):
    /health /data/snapshot /decision/matrix /dashboard/state 200; /replay/status
    active (count=1, active_snapshot_replay); /replay/{id} 200 (decision_matrix
    dahil); /replay/{id}/decision-trace 200 (regime NEUTRAL, risk_gate
    NO_POSITION_INCREASE, 8 top candidate, 20 final, deep_data 5 anahtar); missing →
    404. Web SSR (izole 3100) 200 / 32 panel + replay_status paneli + HeroScene +
    PAPER_ONLY. İzole server'lar kapatıldı; data/runtime gitignore'lu (snapshot
    diske yazıldı ama commit'lenmez). RiskGate/DQS/KillSwitch/halt sıfır diff.
  - Açık (NEXT): UX1 Agent Operating Cockpit veya R2 deterministic rolling
    replay/backtest runner (replay foundation gerçek çalışıyor — yeni veri kaynağı
    gerekmez).

- **v2.6.1 — LLM Persona deep-data derinleşme tamamlandı** (2026-06-13): v2.6
  persona/chat/AI-report katmanı, v2.6'dan SONRA eklenen v2.7 deep-data
  dimensiyonlarına (D2 türev / D3 options / D4 volatilite / D5 catalyst
  half-life + event riski + rotation) **state-grounded** olarak bağlandı.
  LLM hâlâ karar VERMEZ — yalnızca açıklar; karar zinciri sıfır diff.
  - **Kök neden**: `matrix_view` bu özetleri zaten üretiyordu ama LLM kompakt
    bağlamı (`packages/agent/llm/context.py`) bunları DROP ediyordu → persona/chat
    options/vol/türev/catalyst/rotation göremiyordu.
  - **context.py**: `_deep_data_summary(view, snap)` → kompakt `deep_data` bloğu
    (options regime/ATM IV/IV-RV/skew+proxy, volatilite regime/state/z-skor, türev
    squeeze/funding+proxy, catalyst event_type/actionability/half-life, event_risk
    level/restrictive, rotation status/score/direction/evidence). Digest stabil
    (cache güvenli — hours_until gibi volatil alan girmez).
  - **report.py**: Risk Officer kanıt+itirazları options stresi / volatilite
    rejimi / türev squeeze / catalyst kapılarını içerir; Macro Strategist rotation
    + volatilite + options stresini senaryoya katar. `evidence_used` HÂLÂ koddan
    (LLM uyduramaz); deep-data yoksa boş (uydurma yok). Persona briefleri deep-data'ya
    atıf yapar (LLM yolu da görür).
  - **chat.py**: yeni intent handler'ları — "Options risk ne diyor?", "Volatility
    neden kısıtladı?", "Funding/türev ne diyor?", "Rotasyon ne durumda?", "Catalyst
    etkisi var mı?". RiskGate/why fallback'inden ÖNCE çalışır; "RiskGate neyi
    engelledi?" hâlâ risk_gate handler'ına gider (yanlış yönlenme testli). Veri
    yoksa "kısıt üretmiyor" der, uydurmaz. Injection/bypass guard değişmedi.
  - **Frontend** (additive, şema değişmedi): AIReportPanel persona `evidence_used`
    satırı + "Açıklayıcı katman · yürütme yetkisi yok — final karar deterministik
    engine + RiskGate" rozeti; ChatPanel'e options/volatility/türev öneri soruları.
    Persona/chat response şekli değişmedi → openapi/TS sıfır diff → codegen drift
    otomatik yeşil.
  - **334/334 pytest** (+11: deep-data summary filtresi, persona fallback grounding,
    boş-state'te kanıt uydurmama, 5 chat intent, risk_gate yanlış-yönlenme yok,
    endpoint state-grounded; testlerde live network yok), CI-scope ruff + tsc +
    pnpm build yeşil. **Live smoke** (izole API 8011, gerçek Deribit): risk_officer
    `options:ETHUSD PUT_SKEW_STRESS` + `volatility` + `catalyst`; macro
    `rotation:bearish 39.0`; chat 5 deep-data intent gerçek değerlerle grounded
    (BTC ATM IV 0.41 CHEAP_VOL, proxy uyarısı); bypass → guard refusal. Web SSR
    (izole 3100) 200 / 32 panel + HeroScene + PAPER_ONLY. PAPER_SAFE/NO_EXECUTION;
    RiskGate/DQS/KillSwitch/halt sıfır diff, bypass yok.
  - Açık (NEXT): gerçek replay/backtest motoru (disk snapshot store) ve/veya kalan
    deep-data slice / asset-universe genişletme.

- **v2.7 D3 — Options IV / Skew / Term Structure Intelligence tamamlandı**
  (2026-06-13): BTC/ETH options implied volatility, 25Δ skew (proxy), term
  structure ve realized-vs-implied spread karar zincirine **yalnızca kısıtlayıcı**
  eklendi. Yeni provider `packages/data/providers/options/` (saf-python engine +
  Deribit public adapter + offline fixtures + orchestrator). Live Deribit
  `get_book_summary_by_currency` → ATM IV / OTM call-put IV / OI / underlying;
  instrument_name parse (strike/expiry/call-put). Live fail → DEGRADED, chain boş
  → UNAVAILABLE (runtime mock YOK; fixture verified=false, karar dışı).
  - **Engine** (`options/engine.py`): ATM IV (ön vade, en yakın strike), 25Δ skew
    **proxy** (`is_proxy=True`; moneyness tabanlı OTM call IV − OTM put IV; gerçek
    greeks DEĞİL), put/call OI oranı, term structure (front/next/long ATM IV +
    slope), IV-RV spread (D4 realized vol 1d ile). Rejim: NORMAL / RICH_VOL /
    CHEAP_VOL / PUT_SKEW_STRESS / CALL_SKEW_EUPHORIA / TERM_STRESS. DQS = tazelik ×
    bileşen tamlığı.
  - **Gate** (`packages/risk/options_risk.py`): yalnızca verified+OK + BTC/ETH.
    PUT_SKEW_STRESS/CALL_SKEW_EUPHORIA + long aday → CAUTION ×0.5 (short/contrarian
    yalnızca WATCH bağlam); TERM_STRESS → NO_POSITION_INCREASE (block); RICH_VOL →
    CAUTION; CHEAP_VOL → WATCH (yalnızca bağlam, **boost YOK**). size_factor ≤ 1.0.
    Timeframe ağırlıklı: options 4h/1d/1w bağlamı (tam etki); 15m/1h düşük (0.25/
    0.4) → block CAUTION'a yumuşar. RiskGate hard gate'inden SONRA, yalnızca açılış
    adayına.
  - **Entegrasyon**: pipeline `MarketSnapshot.options` (Deribit chain + D4 realized
    vol; ekstra ağ yalnızca Deribit); decision engine options gate (catalyst'ten
    sonra) + `options_report` + blocked_by `options_risk:*`; matrix `options`
    özeti (rejim ≠ NORMAL); `/data/snapshot` options alanı.
  - **Sözleşme** additive: openapi `OptionsSnapshot` / `OptionsSummary` +
    `OptionsRegime` / `OptionsStatus` enum + DataSnapshot.options +
    DecisionMatrix.options. TS api.ts senkron (codegen drift yeşil).
  - **Frontend**: `OptionsVolPanel` (selector `selectOptions` + registry, page.tsx
    tek GridCell) — symbol / ATM IV / realized karşılaştırma / IV-RV / 25Δ skew
    (proxy rozeti) / put-call OI / term structure / rejim / source / freshness /
    status / karar etkisi. TimeframeMatrixPanel options banner + hücre "OPTIONS"
    rozeti. VolatilityPanel/DerivativesPanel/CatalystPanel bozulmadı.
  - **323/323 pytest** (+36 D3; live network yok), CI-scope ruff + tsc + pnpm
    build yeşil. Live smoke OK (gerçek Deribit: BTC ATM IV ~41% CHEAP_VOL, ETH
    ~23% PUT_SKEW_STRESS, verified=true, FRESH; matrix options banner; RiskGate
    suspended/DQS BLOCKED iken options hücreyi bypass etmiyor). Eski E_YAY CODEX
    `com.eyay.backend` launch agent'ı `*:8000`'de duruyor — Clean E-yAy API
    `127.0.0.1:8000`'de ayrı kalkıyor (127.0.0.1 istekleri Clean'e gider).
    PAPER_SAFE/NO_EXECUTION; RiskGate/DQS/KillSwitch/halt sıfır diff, bypass yok.
  - Açık (NEXT): gerçek replay/backtest motoru ve/veya v2.6 LLM persona derinleşme.

- **v2.7 D5 — Real News Feed + Catalyst Half-Life Intelligence tamamlandı**
  (2026-06-12): mevcut RSS haber feed'i gerçek catalyst zekâ katmanına çevrildi.
  Her başlık kural tabanlı (deterministik, **LLM YOK**, network YOK) bir
  `event_type`'a sınıflandırılır ve event_type'a göre asset × timeframe etki
  haritası + yarı-ömür + `valid_until` + actionability üretir.
  - **Sınıflandırma + motor** (`packages/data/providers/news/catalyst.py`):
    13 event_type (geopolitical de/escalation, inflation_data, jobs_data,
    central_bank, oil_supply/inventory, crypto_etf_flow, funding_oi_squeeze,
    earnings, exchange_outage, rumor_unverified, unknown). Sıralı kural seti;
    rumor → `verified=False` (trade'e dönüşmez). `build_impact` → CatalystImpact
    (affected_assets = event default ∪ başlıktan tespit; surprise_level işaretli;
    valid_until = ts + half_life×3; confidence = verified+freshness+relevance).
  - **Gate** (`packages/risk/catalyst_risk.py`): yalnızca `verified` + yarı-ömrü
    dolmamış + symbol/TF eşleşen impact'ler. CONTEXT_ONLY→NONE, WATCH→bağlam,
    CAUTION→×0.5, NO_POSITION_INCREASE→block. Yön bağımsız; size_factor ≤ 1.0.
    RiskGate hard gate'lerinden SONRA, yalnızca açılış adayına.
  - **Entegrasyon**: pipeline `MarketSnapshot.catalyst_impacts` (başlıklardan,
    ekstra ağ yok); decision engine catalyst gate (volatility'den sonra) +
    `catalyst_report` + blocked_by `catalyst_risk:*`; matrix `catalysts` özeti;
    `/data/snapshot` catalyst_impacts alanı.
  - **Sözleşme** additive: openapi `CatalystImpact` genişletildi (headline_id /
    actionability / verified / evidence / …) + `CatalystEventType` /
    `CatalystActionability` enum + `CatalystSummary` + DataSnapshot.catalyst_impacts
    + DecisionMatrix.catalysts. TS api.ts senkron (codegen drift yeşil).
  - **Frontend**: `CatalystImpactPanel` (selector `lib/selectors/catalyst.ts` +
    registry, page.tsx tek GridCell) — event_type / affected assets+TF / yarı-ömür
    countdown / valid_until / actionability / evidence / rumor rozeti. NewsPanel
    (unscheduled news) + EventCalendarPanel (scheduled) ayrı kalır.
    TimeframeMatrixPanel catalyst banner + hücre "CATALYST" rozeti.
  - **287/287 pytest** (+21 D5; live network yok), CI-scope ruff + tsc + pnpm
    build yeşil. Live smoke OK (gerçek RSS → central_bank/geopolitical/
    funding_squeeze/etf_flow/rumor sınıfları; rumor verified=false; matrix
    catalyst banner; RiskGate suspended iken catalyst hücreyi bypass etmiyor).
    PAPER_SAFE/NO_EXECUTION; RiskGate/DQS/KillSwitch/halt sıfır diff, bypass yok.
  - Açık (NEXT): D3 (options IV/skew Deribit) ve/veya gerçek replay/backtest motoru.

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

- P1 Paper Lifecycle Finalization bitti (commit `feat(paper): finalize lifecycle
  and audit trail`). Backend yeterince güçlü; yeni veri kaynağı eklenmez.
- Sıradaki: **L1 — Learning Loop Finalization** (bkz. `.tasks/NEXT_TASK.md`).
  Paper lifecycle artık sağlam + audit edilebilir; learning loop'u gerçek paper
  outcome'dan dürüst öğrenmeye hazırla: canonical outcome record normalization,
  timeframe-aware learning (15m hatası 1d'yi cezalandırmaz), mistake memory /
  calibration / auto-weight trainer yalnızca verified outcomes + owner approval,
  learning worker reliability, API/dashboard additive. PAPER_SAFE / NO_EXECUTION;
  active weights owner approval olmadan değişmez.
- `.tasks/NEXT_TASK.md` L1 ile güncellendi.
