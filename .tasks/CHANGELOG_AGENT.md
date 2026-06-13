# Agent Changelog

## 2026-06-14 — UX4 Live Feedback Polish
- Canlı cockpit okunabilirlik cilası — yeni panel/veri/backend logic yok, mevcut
  componentler sadeleştirildi. **Frontend-only**; backend FREEZE korundu (packages/ +
  apps/* SIFIR diff; openapi/TS değişmedi → codegen drift otomatik yeşil). Frontend
  hesap yapmaz; selector/brief korundu. Önceki oturumun commit edilmemiş WIP'i
  kurtarıldı (AgentBrief banner / Matrix capList / News collapse / Catalyst muted /
  OptionsVol impact-first + duplicate rozet zaten kalkmıştı), üzerine eksik parçalar
  tamamlandı.
- **Market structure impact-first** (`OptionsVolPanel` · `VolatilityPanel` ·
  `CryptoDerivativesPanel`): kartın üstünde tek belirgin "karar etkisi: …" satırı;
  teknik sayılar (ATM IV / rv / funding-OI / 25Δ skew / term) altta + daha küçük
  (white/60). Alttaki **duplicate impact rozeti** üç panelde de kaldırıldı.
- `TimeframeMatrixPanel`: market-structure banner özetleri `capList` ile ilk 3 etki +
  "+K" (detay expert panelde); global gate'te hücreler gate'i tekrar etmez (üstte tek
  banner; UX1 davranışı korundu).
- `NewsPanel`: ilk 6 başlık görünür, kalanlar `<details>` collapsed; ham haber Macro/
  Catalyst expert'te; uzun başlık `break-words`.
- `CatalystImpactPanel`: expired / unknown / context-only (rumor unverified dahil)
  muted (opacity-50); aktif CAUTION / NO_POSITION_INCREASE sol kenar renkli vurgu.
- `AgentBriefPanel`: hard-stop (HALT/DQS_BLOCKED/PROVIDER_DOWN) ilk ekranda ⛔ kırmızı
  banner ("YENİ İŞLEM YOK — {main_blocker.label}" + detail); soft RISK_GATE ⚠ magenta.
  `main_blocker` backend cockpit'ten (frontend hesap yok).
- Copy/Learning zaten temizdi (UX1/UX2): AIReport/DecisionPanel tek `main_blocker`
  (stale "DQS BLOCKED veya risk gate" grep 0), LearningPanel insufficient tek satır +
  muted metrik → dokunulmadı.
- Validation: tsc temiz; next build ✓ (4/4 static prerender); SSR (prerendered + live
  izole 3100) HTTP 200, AgentBrief görünür, expert `<details>` collapsed, grup
  başlıkları (Karar/Risk/Uzman), PAPER_ONLY + NO_EXECUTION + HeroScene canvas korundu,
  "karar etkisi" client bundle'da. Backend testleri çalıştırılmadı (gerekmez —
  yalnızca apps/web/components/panels/*.tsx + docs değişti). Commit:
  `feat(web): polish live dashboard readability`.

## 2026-06-13 — UX3 Dashboard Information Architecture
- Dashboard "veri çöplüğü"nden önem sırasına göre **gruplu IA**'ya. **Frontend-only**;
  backend FREEZE korundu (packages/ + apps/* SIFIR diff; openapi/TS değişmedi →
  codegen drift otomatik yeşil). Frontend hesap yapmaz; selector/brief korundu.
- `app/page.tsx`: düz panel grid'i kalktı. **Simple** 5 önem-sıralı bölüm: Agent
  Command Center (AgentBrief hero + Karar Merkezi + AI Analist) → Risk & Yürütme
  Donması (RiskGate+Drawdown+Paper+PositionChecks; KILL_SWITCH/HALT matristen ÖNCE)
  → Karar İzi/Aday Matrisi (TimeframeMatrix+DecisionTrace+AgentVotes+CommandSignals)
  → İzlenecek Koşullar → Agent'a Sor. **Expert** (collapsed) 5 grup: Data Quality &
  Providers · Market Structure · Macro/Catalyst · Paper & Learning · Ops/System.
  Ortak `PanelGroup` helper (eski `ExpertGroup` yeniden adlandırıldı); page.tsx
  şişmedi.
- `lib/panel-registry.ts`: yeni `PanelGroupId` (command/risk/decision/watch/chat +
  data/market/macro/learning/ops); her panel doğru gruba + IA sırası (group/tier
  metadata; layout elle). Replay/Provider/MarketData/Snapshot/PanelAudit/Learning
  paneller ana ekrandan expert gruplara taşındı; Macro'da Catalyst önce, ham haber
  geri planda.
- `components/panels/LearningPanel/index.tsx`: yetersiz örnekte tek satır
  "Learning inactive — insufficient verified closed trades (n/min)".
- Copy/replay zaten temizdi (UX1/UX2 + R1/R2): AIReport/DecisionPanel tek
  main_blocker; ReplayStatus active/insufficient (REZERVE copy yok) → Ops/System'e
  alındı. Responsive: TimeframeMatrix overflow-x-auto korundu, grup gridleri
  mobil tek sütun.
- Validation: tsc temiz; next build ✓; SSR (prerendered + live izole 3061) HTTP 200,
  AgentBrief görünür, expert `<details>` collapsed (open yok), 5 grup başlığı görünür,
  PAPER_ONLY + HeroScene canvas korundu, sıralama doğru. Backend testleri
  çalıştırılmadı (gerekmez). Commit: `feat(web): reorganize dashboard information architecture`.

## 2026-06-13 — REL1 Release Packaging / Local Production Runbook
- Tek komutla, arka planda, tekrar edilebilir local production. **Devops/scripts/
  docs**; backend FREEZE korundu (packages/ + apps/* runtime kodu SIFIR diff —
  scriptler yalnızca mevcut süreçleri başlatır). PAPER_SAFE/NO_EXECUTION; canlı
  paper_safe=true doğrulandı.
- Yeni `scripts/_prod_common.sh` (ortak helper: pid/port/python/node/SSL +
  `.env` yükleme + **eski E_YAY CODEX LaunchAgent tespiti**).
- Yeni `scripts/prod_up.sh`: API+web (next start, prod build)+tick daemon'ı
  **background** başlatır (pid `data/runtime/run/`, log `data/runtime/logs/`),
  learning'i **bir kez** seed eder. Preflight port-conflict → açık hata + meşgul
  pid + LaunchAgent uyarısı (`com.eyay.backend → *:8000`) + bootout ipucu.
- Yeni `scripts/prod_down.sh`: api/web/tick SIGTERM→(gerekirse SIGKILL) + pid
  temizliği. learning supervise edilmez (tek-seferlik).
- Yeni `scripts/prod_status.sh`: süreç (RUNNING/stopped+pid) + port + (API ayaktaysa)
  system/health özeti (paper_safe + stale_workers + warnings). Salt-okur.
- `Makefile`: +`prod-up`/`prod-down`/`prod-status`/`prod-smoke` (mevcut dev/workers/
  smoke bozulmadı). `prod-smoke` = smoke.sh API_PORT/WEB_PORT'a göre.
- `README.md`: "Local production runbook (REL1)" bölümü (first run/start/stop/
  status/smoke/common failures/port conflict + LaunchAgent/SSL certifi/worker stale/
  data/runtime cleanup); Logs bölümü prod log dosyalarını işaret eder. PAPER_SAFE
  deploy checklist (DEP1) korundu.
- `scripts/smoke.sh` dokunulmadı (task-#6 endpoint listesini + PAPER_ONLY marker'ı
  zaten karşılıyor).
- Validation: `bash -n` 7/7 ✓; canlı prod lifecycle (izole 8060/3060, TEST_USE_MOCK):
  prod_up→status→smoke(8/8)→down temiz; tsc temiz; next build ✓; pytest **419/419**
  (backend regresyon — kod değişmedi). Commit: `chore(release): add local production runbook`.

## 2026-06-13 — UX2 Dashboard Polish / Usability Pass
- Agent Operating Cockpit okunabilirlik cilası. **Frontend-only**; backend FREEZE
  korundu (packages/ + apps/api + worker SIFIR diff; openapi/TS şeması değişmedi →
  codegen drift otomatik yeşil). RiskGate/DQS/KillSwitch/halt/paper/learning/replay
  dokunulmadı. PAPER_ONLY/NO_EXECUTION rozetleri korundu.
- **Uzman bölümü gruplandı** (`app/page.tsx` + yeni yerel `ExpertGroup` helper):
  düz ~30 panel grid'i 6 okunur başlığa ayrıldı — Karar & Analiz / Risk / Piyasa
  Yapısı / Veri / Öğrenme / Ops (her grup hint + ayraç). Simple layout + collapsed
  `<details>` aynı.
- **Vague copy fix** (`AIReportPanel`): "NO ACTIONABLE — DQS BLOCKED **veya** risk
  gate" (UX1'de başka yerlerden silinmişti, burada kalmış) → backend'in tek
  `main_blocker`'ını yazan net copy (useCockpitBrief, read-only). "X veya Y" gitti.
- **AgentBrief** (`AgentBriefPanel`): "Önerilen duruş" satır-içi vurgulu callout +
  okunur tipografi (ilk-ekran çıkarımı belirginleşti).
- **Chat** (`ChatPanel` + `panel-registry`): başlık "Ask the Agent" → "Agent'a Sor";
  öneri "Neden BTC açmadın?" → "BTC 1h neden hold?" (backend symbol+why intent'ine
  net yönlenir; diğer öneriler intent eşleşmesi korunarak bırakıldı).
- **Responsive** (`TimeframeMatrixPanel`): tablo `overflow-x-auto`+`min-w` sarıldı
  (dar ekran taşma → yatay kaydırma). TimeframeMatrix tek-banner suspended düzeni
  (UX1) zaten temiz — dokunulmadı.
- Validation: tsc temiz, next build ✓ (`/` 334 kB static), canlı SSR smoke (izole
  API 8050 + web 3050, TEST_USE_MOCK): smoke.sh 8/8 PASS; SSR'da Agent Brief +
  HeroScene canvas + PAPER_ONLY + gruplu başlıklar; `<details>` open YOK (collapsed);
  eski "BLOCKED veya risk gate" copy kaldırıldı. Backend testleri çalıştırılmadı
  (gerekmez — backend dosyası değişmedi). Commit: `feat(web): polish agent cockpit usability`.

## 2026-06-13 — DEP1 Deployment / DevOps Checklist
- Backend RC'yi gerçek 7/24 çalıştırmaya hazırladı: yalnızca **docs/devops**;
  packages/ + apps/ runtime kodu **SIFIR diff**. Backend FREEZE korundu (yeni
  feature/data source/intelligence yok; RiskGate/DQS/KillSwitch/halt/paper/
  learning/replay dokunulmadı).
- **`.env.example` yeniden yazıldı** (doğru + tam). Phantom var fix: kod
  `LLM_DAILY_TOKEN_BUDGET` okuyor (`.env` `GROQ_DAILY_BUDGET_TOKENS` yazıyordu);
  `ANTHROPIC_API_KEY`/`API_HOST`/`API_PORT`/`YFINANCE_CACHE_TTL_SEC`/
  `NEWS_CACHE_TTL_SEC` kod tarafından OKUNMUYOR → kaldırıldı. Eklendi: `LLM_MODE`,
  `PRICE_USE_MOCK`, `DEV_CORS`/`CORS_EXTRA_ORIGINS`, `TICK_INTERVAL_SEC`,
  `SSL_CERT_FILE`, tüm runtime `*_PATH` override'ları + default'lar. `.env`
  otomatik yüklenmiyor (dotenv yok) — doc. PAPER_ONLY/NO_EXECUTION YAPISAL
  (kodda zorlanır; `/system/health` paper_safe/no_execution sabit true).
- Yeni `scripts/smoke.sh` (+`make smoke`): health/system-health (paper_safe
  doğrular)/cockpit/snapshot/decision-matrix/replay-status/learning-summary +
  web SSR; API_BASE/WEB_BASE/SKIP_WEB override; fail → exit 1.
- Yeni `scripts/workers.sh` (+`make workers`): tick_worker uzun-ömürlü daemon +
  learning_worker tek-seferlik (run_once) seed. Süreç modeli netleşti: tick =
  daemon (restart-always), learning = zamanlayıcı (cron/timer, restart-always
  DEĞİL = spin-loop).
- README: stale status header ("v2.5-web") → **Backend Release Candidate**; smoke
  bölümü script tabanlı (eski stale `replay reserved` + eksik endpoint'ler
  düzeltildi); yeni **"Deployment / 7-24 readiness"** bölümü (süreç tablosu +
  restart politikası + supervision launchd/systemd/pm2/compose + health check +
  stale alert + logs + runtime volume) + açık **PAPER_SAFE deploy checklist**.
- Validation: pytest **419/419** (sıfır diff — regresyon yok), ruff CI-scope temiz,
  tsc temiz, next build ✓, `bash -n` scripts ✓. Canlı smoke (izole API 8050 + web
  3050, TEST_USE_MOCK, eski :8000/:3000 agent çakışmasından kaçınıldı): smoke.sh
  **8/8 PASS** (paper_safe=true + web SSR 200); learning one-shot exit 0;
  tick daemon cycle OK + SIGTERM temiz kapanış. data/runtime sızıntı yok.
- PAPER_SAFE/NO_EXECUTION: broker yok, gerçek emir yok, live execution yok; kod
  sıfır diff. Commit: `chore(devops): add deployment readiness checklist`.

## 2026-06-13 — A1 Final Backend Architecture Audit (Backend Release Candidate)
- Backend uçtan uca "bitirme kontrolü"nden geçti: **PASS**. Gerçek P0 bug yok,
  gerçek sözleşme/runtime/TS drift yok, kritik test boşluğu yok. **Sıfır runtime
  diff** — kod değiştirilmedi (görev kuralı: P0 yoksa kod yazma, docs + RC işaretle).
  PAPER_SAFE / NO_EXECUTION her katmanda doğrulandı.
- **Module boundaries**: temiz. packages→apps importu yok; provider→decision/risk/
  paper importu yok; risk→decision importu yok; wildcard import yok; service logic
  api router import etmiyor. LLM katmanı (`agent/llm`) decision/paper state'i
  yalnızca OKUR (`paper_state.load`, `decide_matrix`/`matrix_view` salt-okur
  yeniden hesap; tek `.record()` çağrıları token budget'ı — paper/decision değil).
- **Decision/Risk order**: RiskGate hard gate'leri ÖNCE (KILL_SWITCH→blocked,
  NO_POSITION_INCREASE/RISK_REDUCE→hold); sonraki tüm gate'ler (mistake/correlation/
  derivatives/volatility/catalyst/options/timeframe) yalnızca kısıtlayıcı —
  `size *= factor` (factor ≤1.0, clamp ≤1.5) ya da block; hiçbiri size artırmaz.
  1w paper_execution=false (doğrudan trade açmaz). candidate vs final ayrımı
  korunuyor. `risk/engine.py` max-priority candidate havuzu → bypass yapısal
  olarak imkânsız; DQS<55 → KILL_SWITCH veto.
- **Provider/DQS/mock**: DATA_POLICY uygulanıyor — `get_quote` runtime'da mock'a
  düşmez (`DATA_UNAVAILABLE` döner); SIMULATION damgası görünür. Paper fiyat yoksa
  fake kapanış yok (`EXPIRED_PENDING_PRICE`). Learning yalnızca verified veri.
- **Paper/Learning/Replay/Worker**: tek açılış yolu `attempt_open` (entry_price
  None/≤0 → açmaz); append-only audit; backtest look-ahead yok (`_future_price`
  ilk `epoch ≥ karar+horizon`, cherry-pick yok), live refetch yok, emir yok;
  trainer yalnızca PROPOSAL, weights yalnızca owner `approve_current` ile; heartbeat
  atomik.
- **Contract/API/TS**: `test_openapi_contract` her dokümante GET'i şemaya doğruluyor
  + path drift guard; `test_codegen_drift` openapi şema/enum ↔ TS api.ts. 11 kritik
  endpoint kayıtlı + dokümante. (Notlar: codegen drift tek yönlü/gevşek enum eşleme
  — el-senkron için yeterli.)
- **State stores**: hepsinde missing/corrupt → güvenli default. Atomik `os.replace`
  4 yüksek-churn store'da (snapshot/paper/run/heartbeat); 5 düşük-churn store
  (risk/halt, rebalance, calibration, llm budget, llm cache) doğrudan write_text
  (P1 hardening — güvenlik açığı değil). `schema_version` snapshot+paper'da.
- **PAPER_SAFE**: broker/order/execute/ccxt yürütme tokeni HİÇBİR yerde yok (tek
  "broker" = llm guard blocklist). RiskGate/DQS/KillSwitch/halt yalnızca kısıtlayıcı.
- **Validation**: pytest **419/419**, ruff CI-scope temiz, tsc temiz, next build ✓
  (`/` 333 kB). In-process smoke (offline): 10 kritik GET 200; /system/health
  paper_safe=true; /replay empty+insufficient_snapshots (dürüst); POST /chat bypass
  probe → guard refusal.
- **Bulgular (P1, opsiyonel, freeze sonrası)**: H1 5 store atomik değil; H2
  schema_version dağınık; H3 ARCHITECTURE.md çok-agent yapısı aspirasyonel (kod
  sade consensus+llm); H4 codegen drift tek yönlü; H5 `decide_all` test-only.
- Commit: `docs(backend): mark backend release candidate after final audit`.

## 2026-06-13 — O1 7/24 Worker Reliability
- Clean E-yAy artık endpoint koleksiyonu değil, gözlemlenebilir 7/24 agent
  servisi: worker heartbeat + stale tespiti + crash raporlama + system health.
  Yeni data source / dashboard redesign / intelligence / trading logic YOK;
  RiskGate/DQS/KillSwitch/halt sıfır diff. PAPER_SAFE/NO_EXECUTION; worker
  reliability hiçbir şekilde trade iznini artırmaz.
- Yeni `packages/ops/heartbeat.py`: file-backed `worker_heartbeats.json` (atomik
  write, corrupt→default, missing→default). `record()` cycle_count'u terminal
  statüde artırır; last_success_at OK/DEGRADED/NO_DATA'da güncellenir, FAILED/
  RUNNING'de korunur.
- Yeni `packages/ops/system_health.py`: network-free ViewModel — worker view
  (STALE/UNKNOWN türetilir; eşik TICK_STALE_SEC=120/LEARNING_STALE_SEC=3600),
  provider_summary, dqs_status, snapshot_store_status, risk_halt_status +
  owner warning'leri (worker_stale/provider_degraded/dqs_blocked/
  snapshot_store_empty/learning_worker_no_data/paper_audit_errors/active_halt/
  stale_dashboard_state).
- Yeni endpoint `GET /api/v1/system/health` (`apps/api/routers/system.py`); mevcut
  `/health` korundu.
- `apps/tick_worker/main.py`: her cycle heartbeat (RUNNING→OK/DEGRADED;
  istisnada FAILED, loop ölmez). snapshots_written/decisions_generated/
  paper_actions sayılır. Worker gerçek emir üretmez.
- `apps/learning_worker/main.py`: L1 run metadata'sı heartbeat'e bağlandı
  (COMPLETED→OK / COMPLETED_WITH_ERRORS→DEGRADED / NO_DATA→NO_DATA).
- Sözleşme additive: openapi `SystemHealth` + `WorkerHealth` + `/system/health`;
  TS api.ts senkron. SystemHealthBar worker status + stale + last tick/learning +
  snapshot count + warning rozetleri + NO_EXECUTION badge gösterir.
- 419 pytest (+11 + 1 contract param: heartbeat atomic/missing/corrupt/cycle,
  stale detection, tick OK + tick exception→FAILED, learning empty→NO_DATA,
  endpoint). ruff CI-scope + tsc + pnpm build yeşil. Live smoke (izole API 8023 +
  web 3102): /system/health workers DEGRADED+NO_DATA fresh, provider 8ok/3deg,
  snapshot_count 1, halt yok, warnings provider_degraded+learning_worker_no_data;
  cockpit/learning 200; web SSR 200 "Sistem Sağlığı". PAPER_SAFE; RiskGate bypass yok.

## 2026-06-13 — L1 Learning Loop Finalization
- Learning loop kapalı paper trade outcome'larından **doğru + timeframe-aware +
  gate-aware + owner-approval-safe** öğreniyor. Yeni veri kaynağı / dashboard
  redesign / trading logic YOK; RiskGate/DQS/KillSwitch/halt sıfır diff.
  PAPER_SAFE/NO_EXECUTION; active weights owner approval olmadan değişmez.
- **BUG FIX** `packages/learning/auto_weight_trainer.py`: `_parse_dominant_module`
  artık `fingerprint.dominant_module` kullanıyor — v2 (parts[7]) ve legacy
  (parts[5]) ayrımı. Eski kod hep parts[5] döndürüp v2'de score_bucket'ı module
  sanıyordu (yanlış attribution). Canlı doğrulandı: by_dominant_module = touche
  (S55 değil).
- `packages/learning/fingerprint.py`: `parse()` (v2/legacy/malformed-safe) +
  `dominant_module()`.
- Yeni `packages/learning/outcomes.py`: `CanonicalOutcome` (trade_id/symbol/
  timeframe/opened/closed/duration/direction/prices/pnl/pnl_pct/open+close_reason/
  fingerprint/regime/dominant_module/candidate+final_action/blocked_by/
  gates_applied/snapshot+decision_id/data_verified/source_quality/paper_only) +
  `build_outcome` (legacy default'lar, asla patlamaz) + timeframe-aware
  `breakdowns`/`bucketize`/`distribution`.
- `packages/learning/summary.py` additive: outcomes_total/verified_outcomes/
  by_timeframe/by_symbol/by_regime/by_dominant_module/by_close_reason/
  worker_last_run/proposal_status. Global metrikler korundu; 15m outcome 1d
  bucket'ını etkilemez.
- Yeni `packages/learning/run_store.py` + `apps/learning_worker/main.py`: run
  metadata (run_id/started_at/completed_at/status/skipped_reason/outcomes_seen/
  proposals_generated/calibration_status/errors). Boş veri → NO_DATA, hata →
  COMPLETED_WITH_ERRORS (worker ASLA patlamaz).
- auto-weight trainer proposal evidence'ına timeframe/regime/module dağılımı eklendi.
- Sözleşme additive: openapi LearningSummary L1 alanları; TS api.ts senkron
  (+OutcomeBucket/LearningWorkerRun). codegen drift + contract yeşil. LearningPanel
  additive: timeframe ayrımı + worker last run + proposal status.
- 407 pytest (+14: dominant_module v2/legacy/malformed, canonical outcome legacy+
  P1-enriched+garbage, 15m≠1d bucket, trainer v2 attribution, mistake memory by
  tf, worker empty NO_DATA + metadata, summary breakdowns). ruff CI-scope + tsc +
  pnpm build yeşil. Live smoke (izole API 8021 + web 3101): health/learning-summary/
  rebalance-proposal/cockpit-brief 200; by_timeframe 15m≠1d; module=touche;
  active_version 1.0.0 (owner gate); web SSR 200. PAPER_SAFE; RiskGate bypass yok.

## 2026-06-13 — P1 Paper Lifecycle Finalization
- Paper lifecycle backend'de net + güvenli + audit edilebilir + öğrenmeye hazır.
  Yeni veri/dashboard/intelligence/mimari YOK. PAPER_SAFE/NO_EXECUTION sıfır diff;
  fiyat yoksa fake kapanış yok; RiskGate/DQS/KillSwitch/halt bypass yok.
- `packages/paper/state.py`: Position lifecycle alanları (lifecycle_status,
  time_stop_expired, pending_exit_reason, open_reason, snapshot_id, scale_in);
  Trade (lifecycle_status, open_reason, snapshot_id); schema_version; atomik
  yazım; corrupt → yedek + temiz default (crash yok); legacy/forward-uyumlu load.
- `packages/paper/lifecycle.py`: state machine (OPEN → EXPIRED_PENDING_PRICE /
  EXIT_PENDING / ERROR_STATE → CLOSED / FORCE_CLOSED); time-stop fiyat varsa
  TIME_STOP_EXIT, yoksa EXPIRED_PENDING_PRICE (sonra fiyatla kapanır); tek açılış
  yolu `attempt_open` + duplicate/scale-in politikası (aynı symbol+tf yön fark
  etmeksizin bloklu, farklı TF serbest, scale_in explicit); her olay audit.
- Yeni `packages/paper/audit.py`: append-only data/runtime/paper_audit.jsonl
  (OPEN_ATTEMPT/OPENED/OPEN_BLOCKED/TIME_STOP_EXPIRED/EXIT_PENDING/CLOSED/
  KILL_SWITCH_EXIT/RISK_REDUCE_EXIT/STATE_REPAIRED/ERROR); best-effort, bozuk
  satır okumada atlanır.
- `apps/api/routers/paper_trading.py` + `apps/tick_worker/main.py`: açılış
  attempt_open'a taşındı (drift yok). /paper-trading/state additive:
  new_entries_disabled, duplicate_warning, audit_summary, recent_audit_events.
- Sözleşme additive: openapi PaperLifecycleStatus + PaperAuditEvent + Position/
  Trade/PaperTradingState alanları; TS api.ts senkron (codegen drift yeşil).
  PaperActionPanel: EXPIRED/EXIT_PENDING "fiyat bekleniyor" + duplicate uyarısı.
- 393 pytest (+18), ruff CI-scope + tsc + pnpm build yeşil, live smoke (health/
  tick/paper-state/dashboard/cockpit + web SSR 200) OK.

## 2026-06-13 — R2 Deterministic Rolling Backtest Runner
- Kayıtlı snapshot serisi üzerinde deterministik replay/backtest. Live refetch
  YOK, sahte geçmiş YOK, look-ahead YOK (outcome yalnızca GERÇEK gelecek
  snapshot'larla, karar zamanından sonraki İLK gözlemle ölçülür). PAPER_SAFE /
  NO_EXECUTION: paper açmaz, RiskGate bypass yok, decide_matrix yeniden çalışmaz.
- `packages/data/snapshot_store.py`: `all_docs()` kronolojik okuma helper'ı.
- Yeni `packages/data/backtest.py` (saf fonksiyon `run_backtest()`): 15m/1h/4h/1d
  horizon; metrikler hit_rate / false_positive / false_negative / avg_return /
  max_drawdown / blocked_decision_accuracy + per_timeframe / per_symbol /
  per_horizon; bloklanmış aday-açılışlar counterfactual; yetersiz örnekte oran
  null. `run_id` = snapshot kümesi + horizon + algo versiyonu SHA-256.
- Yeni endpoint `GET /api/v1/replay/backtest` + `GET /api/v1/replay/backtest/{run_id}`
  (apps/api/routers/replay.py); literal route `{snapshot_id}` catch-all'undan
  ÖNCE. Boş store → insufficient_snapshots, gelecek yok → insufficient_future_data
  (ikisi de 200, dürüst). run_id eşleşmezse 404 + current_run_id.
- Sözleşme additive: openapi /replay/backtest(/{run_id}) + ReplayBacktest /
  ReplayBacktestMetrics; TS api.ts senkron (codegen drift yeşil).
- 375 pytest yeşil (+9), ruff CI-scope + tsc + pnpm build yeşil, live smoke OK.

## 2026-06-13 — UX1 Agent Operating Cockpit
- Dashboard "veri çöplüğü"nden operating cockpit'e: ilk ekranda agent'ın beyni
  (ne yapabilir / neden / ne izliyor). Yeni trading feature / data provider /
  intelligence YOK; RiskGate/DQS/KillSwitch/halt sıfır diff. Frontend hesap
  yapmaz — türetilmiş alanlar backend ViewModel'inden. PAPER_SAFE/NO_EXECUTION.
- Yeni `packages/decision/cockpit.py` (saf fonksiyonlar): compute_main_blocker
  (**TEK** ana engel, "veya" YOK; öncelik DQS/provider > halt > RiskGate),
  compute_data_mode (LIVE_VERIFIED/LIVE_DEGRADED/PARTIAL_FALLBACK/SIMULATION/
  BLOCKED), compute_status (ACTIONABLE/NO_ACTION/WATCHING/FROZEN/BLOCKED),
  agent_brief_view, decision_trace_view, next_watch_conditions (deterministik
  tetik koşulları).
- Yeni endpoint `GET /api/v1/cockpit/brief` (apps/api/routers/cockpit.py) →
  {agent_brief, decision_trace}; decide_matrix+matrix_view'i diğerleriyle aynı
  okur, yalnızca ÖZET üretir.
- report.py: no_actionable/change_mind artık tek ana engeli yazar ("DQS BLOCKED
  veya risk gate kısıtlayıcı" silindi). DecisionPanel risk tarafı tek main_blocker.
- paper_trading.py: `_time_stop_status` (NONE/ACTIVE/EXPIRED + remaining ≥0) —
  serileştirmeye additive; negatif geri sayım YOK (paper logic değişmedi).
- summary.py: MIN_RELIABLE_TRADES=20 + min_sample/sample_sufficient (additive) →
  LearningPanel INSUFFICIENT SAMPLE uyarısı.
- Sözleşme additive: openapi /cockpit/brief + CockpitBrief/AgentBrief/
  DecisionTrace/MainBlocker/WatchCondition + enum'lar; Position time_stop_*;
  LearningSummary min_sample/sample_sufficient. TS api.ts senkron (codegen drift
  + contract yeşil).
- Frontend: lib/selectors/cockpit.ts + useCockpitBrief + api/keys. Yeni paneller
  AgentBriefPanel (üstte tek ana kart, HeroScene üzerinde) / DecisionTracePanel /
  WatchConditionsPanel / PaperActionPanel; Ask the Agent = ChatPanel. page.tsx:
  Simple grid (AgentBrief→DecisionTrace+Watch→TimeframeMatrix→PaperAction+Chat) +
  "Uzman / Detaylar" `<details>` collapsed (diğer tüm paneller). Registry tier
  simple|expert + 4 yeni panel.
- Panel iyileştirmeleri: TimeframeMatrix global-suspended tek banner + sade
  hücre (gate tekrarı yok, candidate→final korunur); AgentVotes → evidence chain
  (verdict/reason/evidence_used/missing_data/actionability); CommandSignals →
  "Aday Sinyalleri" + NOT_ACTIONABLE rozeti; Replay → Uzman/Detaylar (ikinci plan).
- Testler +16 (`tests/unit/test_cockpit.py`): main_blocker tek-engel/no-veya/
  öncelik, data_mode/status eşleme, agent_brief DQS-OK+RiskGate, watch conditions,
  decision_trace, time-stop EXPIRED negatif değil, endpoint, all-suspended.
  pytest 366/366; CI-scope ruff + tsc + pnpm build yeşil. Live smoke (izole API
  8011 gerçek veri + web SSR 3100 prod): cockpit/brief WATCHING/RiskGate tek
  engel; ai-report no_actionable "veya" yok; learning INSUFFICIENT SAMPLE; matrix
  20/20 suspended; SSR 200 "Agent Brief" üstte + HeroScene + PAPER_ONLY + Uzman/
  Detaylar + 36 panel. RiskGate/DQS/KillSwitch/halt sıfır diff, bypass yok.

## 2026-06-13 — R1 Real Snapshot Replay / Backtest Foundation
- Replay `reserved_not_active`'ten gerçek disk snapshot store'a geçti. Sahte
  backtest / uydurma geçmiş YOK. PAPER_SAFE/NO_EXECUTION: replay emir/karar
  üretmez, paper açmaz, RiskGate bypass etmez, live provider çağırmaz.
- Yeni `packages/data/snapshot_store.py` (ARCHITECTURE §3'te tanımlı dosya):
  atomik write (temp + os.replace), bozuk dosya → crash yok, latest/get(id)/
  status/count, zaman-sıralı dosya adı, ring-buffer prune (SNAPSHOT_STORE_MAX),
  aynı id en güncelse duplicate yazmaz. Dir env SNAPSHOT_STORE_PATH
  (default data/runtime/snapshots/; testte temp).
- Producer: tick_worker run_once() her tick'te matrix_view + state'i store'a
  yazar (try/except + log; tick'i patlatmaz). Kayıt: schema_version/snapshot_id/
  generated_at/mode/dqs/provider_status/data_snapshot/decision_matrix/risk_state/
  paper_state_summary.
- Endpoint'ler (apps/api/routers/replay.py, live refetch YOK): /replay/status
  (active/empty + mode active_snapshot_replay/insufficient_snapshots/
  reserved_not_active + snapshot_count + latest), /replay/{id} (kayıtlı snapshot;
  yoksa 404), /replay/{id}/decision-trace (stored decision_matrix'ten karar izi:
  DQS/RiskGate/top candidates/final/blocked_by/paper actions/provider issues/
  catalyst+options+vol+türev özetleri). Yeni karar hesaplamaz.
- Sözleşme additive: openapi ReplayStatus güncellendi + ReplaySnapshot/
  ReplayDecisionTrace + decision-trace path; ReplaySnapshotStatus kaldırıldı.
  TS api.ts senkron (ReplayStoreStatus/ReplayMode/ReplayExecution + tipler).
  Contract/codegen drift yeşil (eski reserved testi → 404 not_found testi).
- Frontend: ReplayStatusPanel store status + mode rozeti + snapshot_count +
  latest id/zaman + "NO LIVE EXECUTION" rozeti + "Replay does not execute trades"
  notu. Selector lib/selectors/replay.ts; page.tsx büyümedi.
- Testler +15 (tests/unit/test_snapshot_replay.py + 2 contract 404): atomik/
  latest/by-id/missing/corrupted/dedup/prune/status, endpoint empty+active,
  found+404, decision-trace stored-matrix, replay live refetch yapmaz (pipeline
  boom guard), tick_worker producer offline. pytest 349/349; CI-scope ruff + tsc +
  pnpm build yeşil. Live smoke (izole API 8011 + 1 gerçek snapshot seed): replay
  status active/count=1, /replay/{id} + decision-trace 200, missing 404; web SSR
  (izole 3100) 200 / 32 panel + replay_status + HeroScene + PAPER_ONLY.
  RiskGate/DQS/KillSwitch/halt sıfır diff.

## 2026-06-13 — v2.6.1 LLM Persona deep-data derinleşme
- v2.6 persona/chat/AI-report katmanı, v2.6'dan SONRA eklenen deep-data
  dimensiyonlarına (D2 türev / D3 options / D4 volatilite / D5 catalyst half-life +
  event riski + rotation) state-grounded bağlandı. Kök neden: `matrix_view` bu
  özetleri üretiyordu ama `llm/context.py` kompakt bağlamı DROP ediyordu.
- `context.py`: yeni `_deep_data_summary(view, snap)` → kompakt `deep_data` bloğu
  (options regime/IV/skew+proxy, volatilite regime/state/z, türev squeeze/funding+
  proxy, catalyst event_type/actionability/half-life, event_risk level/restrictive,
  rotation status/score/dir/evidence). Digest stabil (cache güvenli).
- `report.py`: `_deep_evidence` + `_deep_concerns`. Risk Officer options/vol/türev/
  catalyst kapılarını kanıt+itiraz yapar; Macro Strategist rotation/vol/options'ı
  senaryoya katar. evidence_used HÂLÂ koddan (LLM uyduramaz); deep-data yoksa boş.
- `chat.py`: yeni intent handler'ları (options/volatility/türev-funding/rotation/
  catalyst); proxy dimensiyonları "proxy — gerçek değil" der; veri yoksa "kısıt
  üretmiyor". "RiskGate neyi engelledi?" hâlâ risk_gate'e gider (testli).
- Frontend additive (şema değişmedi): AIReportPanel persona evidence satırı +
  "Açıklayıcı katman · yürütme yetkisi yok" rozeti; ChatPanel deep-data öneri
  soruları. Persona/chat response şekli değişmedi → openapi/TS sıfır diff →
  codegen drift otomatik yeşil.
- Testler +11 (`tests/unit/test_llm_persona.py`): deep_data filtre/taşıma, persona
  fallback grounding, boş-state'te kanıt uydurmama, 5 chat intent + proxy disclaimer,
  risk_gate yanlış-yönlenme yok, endpoint state-grounded. Testlerde live network yok.
- pytest 334/334; CI-scope ruff + tsc + pnpm build yeşil. Live smoke (izole API
  8011, gerçek Deribit): risk_officer options:ETHUSD PUT_SKEW_STRESS + vol + catalyst;
  macro rotation:bearish 39.0; chat 5 intent gerçek değerlerle grounded; bypass →
  guard refusal. Web SSR (izole 3100) 200 / 32 panel + HeroScene + PAPER_ONLY.
  PAPER_SAFE/NO_EXECUTION; RiskGate/DQS/KillSwitch/halt sıfır diff, bypass yok.

## 2026-06-13 — v2.7 D3 Options IV / Skew / Term Structure Intelligence
- Yeni provider `packages/data/providers/options/` — `engine.py` (saf-python,
  deterministik: ATM IV, 25Δ skew **proxy** = OTM call IV − OTM put IV, put/call
  OI oranı, term structure front/next/long + slope, IV-RV spread, rejim NORMAL/
  RICH_VOL/CHEAP_VOL/PUT_SKEW_STRESS/CALL_SKEW_EUPHORIA/TERM_STRESS), `deribit.py`
  (public `get_book_summary_by_currency` adapter; instrument_name parse; fail →
  None), `fixtures.py` (offline, verified=false), `__init__.py` (orchestrator;
  crypto-only; live fail → DEGRADED, mock yok).
- `packages/risk/options_risk.py`: yalnızca kısıtlayıcı gate (verified+OK +
  BTC/ETH). PUT_SKEW/CALL_SKEW + long → CAUTION ×0.5; TERM_STRESS → block;
  RICH_VOL → CAUTION; CHEAP_VOL → WATCH (boost yok). size_factor ≤ 1.0. Timeframe
  ağırlıklı (4h/1d/1w tam; 15m/1h düşük → block yumuşar). RiskGate'ten SONRA.
- Pipeline `MarketSnapshot.options` (Deribit chain + D4 realized vol 1d). Decision
  engine options gate (catalyst'ten sonra) + `TradeDecision.options_report` +
  blocked_by `options_risk:*`; matrix_view `options` özeti (rejim ≠ NORMAL).
- API `/data/snapshot` + `/decision/matrix` options alanları. config thresholds
  `options:` bölümü (eşikler + timeframe_weight).
- Sözleşme additive: openapi `OptionsSnapshot`/`OptionsSummary` + `OptionsRegime`/
  `OptionsStatus` enum + DataSnapshot.options + DecisionMatrix.options; TS api.ts
  senkron (`OptionsSnapshot`/`OptionsSummary`/`OptionsRegime`/`OptionsStatus` +
  selectors `selectOptions`/`selectMatrixOptions`). Codegen drift yeşil.
- Frontend `OptionsVolPanel` (selector + registry; page.tsx tek GridCell) +
  TimeframeMatrixPanel options banner + hücre "OPTIONS" rozeti.
- Tests `tests/unit/test_options.py` (36): engine metrik/rejim, deribit parse,
  orchestrator DEGRADED + ağsız, gate kısıtlayıcı + timeframe, decide_matrix
  uçtan uca (TERM_STRESS block / CHEAP_VOL context / unverified no-block / DQS
  blocked → options bypass yok). pytest 323/323; CI-scope ruff + tsc + pnpm build
  yeşil. Live smoke gerçek Deribit verisiyle OK.

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
