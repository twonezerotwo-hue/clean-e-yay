# TASK RESULT

Date: 2026-06-12
Task: T2 — Timeframe consensus + decision + paper time-stop + TimeframeMatrixPanel
Status: completed

## Ne yapıldı

Sinyal uzayı artık (symbol, timeframe): 15m scout / 1h confirmation /
4h tactical / 1d swing / 1w strategic (paper açmaz). Risk kapsamı GLOBAL
kaldı.

### Consensus (`packages/consensus/engine.py`)

- `build(symbol, snap, regime, timeframe="1d")` — default'la mevcut
  asset-level davranış birebir korunur (testli).
- `_touche` `technicals_by_tf[symbol][tf]`'ten okur; yoksa legacy
  `technicals[symbol]` fallback; **DEGRADED teknik → nötr 50 + uyarı**
  (doğrulanmamış sinyalle yön üretilmez).
- `ConsensusResult.timeframe` + `warnings` additive alanları.

### Decision (`packages/decision/engine.py`)

- `TradeDecision` additive: `candidate_action` (consensus niyeti),
  `blocked_by` (hangi kapı kesti), `actionable`; `timeframe` artık aktif.
- Sıra: **RiskGate önce** (KILL_SWITCH→blocked, RISK_REDUCE/
  NO_POSITION_INCREASE→hold; tüm TF'lerde) → consensus eşikleri →
  mistake gate → correlation cap → **timeframe politikası en son**:
  - `timeframe_risk` çarpanı ≤1.0 clamp'li uygulanır (15m ×0.25, 1h ×0.5)
    — hiçbir TF boyut artıramaz.
  - 1w `paper_execution=false` → final hold + 
    `blocked_by=["timeframe_policy:no_paper_execution"]` (sadece bias).
- `decide_matrix(symbols, snap, risk_in, open_positions, timeframes)` —
  5 TF × symbol kararları; **1w bias çelişkisi** (1w bearish ↔ alt TF
  long) → alt TF size ×0.5 + `1w_bias_conflict:scale_down` (asla artırma).
- `matrix_view(...)` — backend ViewModel: hücre başına candidate/final/
  blocked_by/reason/actionable + rozet (`ACTIONABLE / NOT_ACTIONABLE /
  SUSPENDED`); `suspended` = risk gate kısıtlayıcı VEYA DQS BLOCKED.
- `decide_all` (legacy 1d) aynen çalışıyor — davranış sıfır diff.

### Paper (`packages/paper`)

- `Position.valid_until` additive; `open_position(timeframe=...)` →
  `timeframe_risk.time_stop_hours`'tan hesaplar (15m→6sa, 1h→48sa,
  4h→168sa, 1d→672sa; 0 → time-stop yok). Pozisyon id'si artık
  symbol|timeframe tohumlu (aynı sembol farklı TF çakışmaz).
- `tick(state, prices, now=None)` — SL/TP sonrası **time-stop**:
  `valid_until` dolan pozisyon `TIME_STOP_EXIT` ile kapanır; fiyatı
  olmayan pozisyon kapatılmaz (mock fiyat yok — DATA_POLICY).
- `close_position` Trade'e `timeframe` taşır (önceden default'a
  düşüyordu).
- Legacy kayıtlar: timeframe yoksa "1d", valid_until yoksa None —
  time-stop hiç tetiklenmez (testli).

### Risk

- RiskGate hard gate'leri sıfır diff. Halt (G5) tüm TF'leri durdurur
  (global RiskInput → tek RiskDecision, tüm hücrelere uygulanır) — testli.
- Correlation: aynı sembol farklı TF pozisyonları rho=1.0 ile aynı
  cluster'da sayılır (mevcut davranış doğrulandı + test eklendi).

### Learning

- Fingerprint v2 artık **gerçek TF segmenti** taşır (decide_for_symbol +
  paper açılışı `d.fingerprint`'i kullanır; router/worker'daki duplicate
  fingerprint üretimi kaldırıldı). 15m hatası 1d'yi cezalandırmaz (testli).
- Position/Trade kayıtları gerçek timeframe taşır; trainer/calibration
  rewrite YOK (T2 kapsamı dışı — kayıtlar TF-aware, global calibration
  sürüyor).

### API

- Yeni `GET /api/v1/decision/matrix` (`apps/api/routers/decision.py`) —
  DecisionMatrix ViewModel + provenance `mode` bloğu.
- `POST /paper-trading/tick` → `decide_matrix` (4 sembol × 5 TF);
  aksiyonlar `timeframe` taşır; (symbol, tf) bazlı "zaten açık" kontrolü;
  açılışta `timeframe` + `valid_until` yazılır. tick_worker aynı akışa
  geçti.
- OpenAPI: `/decision/matrix` path; TimeframeDecision/DecisionMatrix
  şemaları dolduruldu (candidate_action, blocked_by, actionable, status,
  paper_action, risk_gate, suspended); Position.valid_until; Trade
  close_reason enum'una TIME_STOP_EXIT/KILL_SWITCH_EXIT.

### Dashboard

- **TimeframeMatrixPanel** (yeni): satır=symbol, sütun=15m/1h/4h/1d/1w;
  hücre = candidate→final aksiyon (farklıysa üstü çizili candidate),
  skor, ACTIONABLE/NOT ACT./SUSPENDED rozeti; tooltip'te blocked_by +
  reason + paper_action. SUSPENDED durumda panel başlığında risk gate
  banner'ı. Registry `timeframe_matrix` (span 3, decision group);
  page.tsx'e tek GridCell.
- **DecisionPanel**: BTCUSD mini TF strip (candidate→final tooltip).
- **TradingPanel**: açık pozisyon satırları — TF rozeti + valid_until
  (time-stop) görünür.
- Selector'lar `lib/selectors/decision.ts`; hook `useDecisionMatrix`;
  frontend hesap yapmaz (rozetler backend'den).

### Environment

- T1'deki SSL certifi gereksinimi kalıcılaştı: `make api-dev` ve
  `scripts/dev.sh` certifi kuruluysa `SSL_CERT_FILE`'ı otomatik ayarlar
  (env'de set ise dokunmaz); README'ye "SSL sertifikaları" bölümü eklendi.

## Güvenlik garantileri

- PAPER_SAFE / NO_EXECUTION — broker/emir/live execution yok.
- RiskGate / DQS veto / KillSwitch / halt **bypass edilmedi**; timeframe
  katmanı RiskGate'ten SONRA ve sadece küçültücü (çarpan ≤1.0 clamp).
- DQS BLOCKED → tüm TF'ler blocked + matrix SUSPENDED (testli).
- Halt aktif → tüm TF'ler blocked (testli).
- 1w hiçbir koşulda paper open üretmez (testli).

## Tests run

- `pytest -q` → **132/132 passed** (19 yeni T2 testi:
  test_timeframe_decisions.py — TF consensus farklılaşması + default 1d
  uyumu + DEGRADED nötr; matrix 5 TF / 1w asla open / ×0.25-×0.5 çarpan /
  1w bias scale-down; DQS BLOCKED + halt → tüm TF blocked/SUSPENDED;
  fingerprint TF izolasyonu; time-stop TIME_STOP_EXIT + fiyatsız kapanmaz
  + legacy default; aynı sembol farklı TF cluster; matrix + tick endpoint).
- `ruff check` (CI scope) → yeşil.
- `pnpm exec tsc --noEmit` + `pnpm build` → yeşil.

## Result

passed

## Next

- **v2.6 — LLM persona** (önerilen sıra: ROADMAP gereği T2 → v2.6;
  T3 catalyst half-life motoru gerçek haber feed'i gerektirdiği için
  v2.7 deep data ile birlikte). `.tasks/NEXT_TASK.md` hazır.
