# TASK RESULT

Date: 2026-06-13
Task: v2.7 D3 — Options IV / Skew / Implied Volatility Intelligence
Status: completed

## Prensip

BTC/ETH options chain'inden implied volatility, 25Δ skew (proxy), term structure
ve realized-vs-implied spread okunup bir **options stress rejimine** sınıflandırılır
ve karar zincirine **yalnızca kısıtlayıcı / bağlam** olarak girer. ASLA size
artırmaz (CHEAP_VOL bile yalnızca bağlam — boost YOK); ASLA RiskGate / DQS /
KillSwitch / halt'ı bypass etmez (RiskGate hard gate'lerinden SONRA çalışır).
Yalnızca **verified=True + status=OK** snapshot karar zincirine girer; fixture
(verified=False) ve DEGRADED/UNAVAILABLE yalnızca dashboard bağlamıdır. skew_25d
GERÇEK 25Δ greeks DEĞİLDİR — moneyness tabanlı **proxy** (`is_proxy=True`).
Runtime'da mock yok; testlerde live network yok. PAPER_SAFE / NO_EXECUTION.

## WIP recovery

Önceki session `OptionsSnapshot` modelini `packages/data/types.py`'a ekleyip
options `engine.py`'ı yazmış (264 satır, syntax + import OK) ama provider'ın geri
kalanı (deribit/fixtures/__init__), pipeline, gate, contract, frontend, tests
eksikti. Baştan yazılmadı; engine'den devam edildi.

## Ne yapıldı

### 1. Provider (`packages/data/providers/options/`)
- `engine.py` (WIP'ten): ATM IV (ön vade, underlying'e en yakın strike), 25Δ skew
  proxy (OTM call IV − OTM put IV), put/call OI oranı, term structure (front/next/
  long ATM IV + slope), IV-RV spread, rejim sınıflandırma, DQS. Chain boş →
  UNAVAILABLE; ATM hesaplanamıyor → DEGRADED. Comment typo düzeltildi.
- `deribit.py`: public `get_book_summary_by_currency?currency=BTC&kind=option`
  adapter; `instrument_name` (BTC-27JUN25-60000-C) → strike/expiry/call-put parse;
  mark_iv yüzde puan → ondalık; hata/timeout → None (mock yok, crash yok).
- `fixtures.py`: offline deterministik chain (3 vade × strike × call/put; put skew
  + hafif backwardation); verified=false.
- `__init__.py`: orchestrator; crypto-only; fixture mode (`TEST_USE_MOCK` /
  `OPTIONS_USE_FIXTURE`); live fail → DEGRADED; provider status + realized_vol
  (D4 1d) IV-RV spread için beslenir.

### 2. Pipeline + decision (`packages/...`)
- `pipeline.py`: `MarketSnapshot.options` alanı; build_snapshot BTC/ETH options
  (Deribit chain + D4 realized vol 1d); provider status + `options_degraded` warning.
- `risk/options_risk.py`: kısıtlayıcı gate (NONE/WATCH/CAUTION/NO_POSITION_INCREASE);
  PUT_SKEW/CALL_SKEW + long → CAUTION, short/contrarian → WATCH; TERM_STRESS →
  block; RICH_VOL → CAUTION; CHEAP_VOL → WATCH; timeframe ağırlıklı (4h/1d/1w tam,
  15m/1h düşük → block yumuşar).
- `decision/engine.py`: options gate (catalyst'ten sonra) + `TradeDecision.
  options_report` + blocked_by `options_risk:*`; matrix_view `options` özeti.
- `config/thresholds_v1.0.yaml`: `options:` bölümü (eşikler + timeframe_weight).

### 3. Sözleşme + frontend
- `contracts/openapi.yaml`: `OptionsSnapshot`/`OptionsSummary` + `OptionsRegime`/
  `OptionsStatus` enum + DataSnapshot.options + DecisionMatrix.options.
- `apps/web/types/generated/api.ts`: aynı tipler + DataSnapshot/DecisionMatrix
  alanları (codegen drift guard yeşil).
- `apps/api/routers/data.py`: `/data/snapshot` options serileştirme.
- `OptionsVolPanel` + selector `selectOptions` + registry + page.tsx tek GridCell;
  TimeframeMatrixPanel options banner + "OPTIONS" hücre rozeti + `selectMatrixOptions`.

### 4. Tests
- `tests/unit/test_options.py` (36): engine metrik + 6 rejim, deribit parse/fail,
  orchestrator crypto-only/DEGRADED/ağsız, gate kısıtlayıcı + timeframe yumuşatma,
  decide_matrix uçtan uca (TERM_STRESS block / CHEAP_VOL context-only / unverified
  no-block / DQS BLOCKED → options bypass yok).

## Sonuç

- **pytest: 323/323** (287 baseline + 36 D3); live network yok.
- **ruff (CI-scope): temiz**; **tsc --noEmit: temiz**; **pnpm build: yeşil**.
- **Live smoke**: gerçek Deribit verisi — BTC ATM IV ~41% (CHEAP_VOL), ETH ~23%
  (PUT_SKEW_STRESS), verified=true, FRESH; `/health` `/data/snapshot`
  `/decision/matrix` `/dashboard/state` 200; web SSR'da OptionsVolPanel +
  Kripto Türevleri + Timeframe Matrisi + PAPER_ONLY görünüyor; log temiz.
- Eski E_YAY CODEX `com.eyay.backend` launch agent'ı `*:8000`'de; Clean E-yAy API
  `127.0.0.1:8000`'de ayrı kalktı (127.0.0.1 → Clean).

## PAPER_SAFE check
- broker: none · real order: none · live execution: none
- RiskGate/DQS/KillSwitch/halt: sıfır diff, bypass yok
- options yalnızca kısıtlayıcı; asla size artırmaz; 1w direct paper execution yok
