# TASK RESULT

Date: 2026-06-13
Task: UX1 — Agent Operating Cockpit
Status: completed

## Prensip

Dashboard "veri çöplüğü" olmaktan çıktı, **operating cockpit** oldu: ilk
ekranda agent'ın beyni okunur (ne yapabilir, neden, ne izliyor). Yeni trading
feature / data provider / intelligence module **EKLENMEDİ**; RiskGate / DQS /
KillSwitch / halt davranışına **DOKUNULMADI** (sıfır diff). Sadece mevcut
backend state'i daha doğru, sade ve kullanıcı dostu gösterdik. Frontend hesap
yapmaz — tüm türetilmiş alanlar backend ViewModel'inden gelir (DASHBOARD_RULES).

PAPER_SAFE / NO_EXECUTION: cockpit yalnızca state'i özetler; emir/karar üretmez,
paper açmaz, RiskGate'i bypass etmez, LLM karar vermez, live çağrı eklemez.

## IMPLEMENTED

### 1. Backend ViewModel (yeni `packages/decision/cockpit.py`, saf fonksiyonlar)
- `compute_main_blocker(...)` — **TEK** ana engel ("veya" YOK). Öncelik:
  DQS_BLOCKED/PROVIDER_DOWN > HALT/kill-switch > RISK_GATE > NONE. DQS BLOCKED
  iken DQS-kaynaklı kill-switch'i ezmez (kök neden = veri).
- `compute_data_mode(prov, dqs)` → LIVE_VERIFIED / LIVE_DEGRADED /
  PARTIAL_FALLBACK / SIMULATION / BLOCKED.
- `compute_status(blocker, can_act)` → ACTIONABLE / NO_ACTION / WATCHING /
  FROZEN / BLOCKED.
- `agent_brief_view(view, snap, ps, prov, halt_active)` → status, can_act,
  main_blocker, plain-language summary, data_mode, dqs/risk özet, açık pozisyon,
  top_blockers, top_candidates (candidate→final), next_watch_conditions,
  recommended_stance, paper_state_summary (open/expired_time_stops/frozen/
  new_entries_disabled/current_paper_actions).
- `decision_trace_view(view, snap)` → candidate_decisions, final_decisions,
  blocked_by, risk_gate, restrictive_gates, paper_action, evidence_refs.
- `next_watch_conditions(...)` — deterministik tetik koşulları: position_count,
  cluster_exposure, time_stop_resolved, provider_restored, catalyst_halflife,
  dqs_verified, risk_gate_clear.

### 2. Endpoint (yeni `apps/api/routers/cockpit.py`)
- `GET /api/v1/cockpit/brief` → `{generated_at, mode, agent_brief, decision_trace}`.
  decide_matrix + matrix_view'i diğer endpoint'lerle aynı şekilde okur; yalnızca
  ÖZET üretir. main.py'de prefix ile register edildi.

### 3. Tek ana engel (item 2) — "veya" kaldırıldı
- `packages/agent/llm/report.py`: `_main_blocker(ctx)` (cockpit ile aynı mantık);
  `no_actionable_decision` actionability + change_mind artık tek ana engeli
  yazar ("DQS BLOCKED veya risk gate kısıtlayıcı" SİLİNDİ).
- DecisionPanel risk tarafı: `brief.main_blocker` → "NO NEW POSITION — main
  blocker: RiskGate NO_POSITION_INCREASE, reason: …".

### 4. Paper time-stop (item 4) — negatif geri sayım YOK
- `apps/api/routers/paper_trading.py::_time_stop_status` → NONE / ACTIVE /
  EXPIRED + `time_stop_seconds_remaining` (≥0; EXPIRED'da 0). Serileştirmeye
  additive eklendi (paper logic değişmedi). PaperActionPanel + TradingPanel
  EXPIRED'ı "TIME_STOP_EXPIRED · exit pending" gösterir.

### 5. Learning insufficient sample (item 9)
- `packages/learning/summary.py`: `MIN_RELIABLE_TRADES=20`, `min_sample` +
  `sample_sufficient` alanları (additive). LearningPanel yetersizse Sharpe/
  WinRate'i büyük göstermez, "INSUFFICIENT SAMPLE" uyarısı basar.

### 6. Sözleşme (additive + drift-safe)
- openapi: `/cockpit/brief` path + `CockpitBrief`/`AgentBrief`/`DecisionTrace`/
  `MainBlocker`/`WatchCondition` şemaları + enum'lar (AgentStatus / MainBlocker
  code / DataMode); Position'a `time_stop_status`/`time_stop_seconds_remaining`;
  LearningSummary'ye `min_sample`/`sample_sufficient`.
- TS api.ts senkron: AgentStatus/MainBlockerCode/DataMode/MainBlocker/
  WatchCondition/AgentBrief/DecisionTrace/CockpitBrief + Position/LearningSummary
  additive alanlar. Codegen drift + contract testleri yeşil.

### 7. Frontend cockpit (selector + hook + paneller; mevcut pattern)
- `lib/selectors/cockpit.ts`, `useCockpitBrief` hook, api client + query key.
- Yeni paneller: **AgentBriefPanel** (üstte tek ana kart, HeroScene üzerinde),
  **DecisionTracePanel**, **WatchConditionsPanel**, **PaperActionPanel**.
- Ask the Agent = mevcut ChatPanel (başlık güncellendi).

### 8. Panel grouping (item 6) — Simple / Expert
- page.tsx yeniden düzenlendi: hero = AgentBrief; Simple grid = DecisionTrace +
  WatchConditions + TimeframeMatrix + PaperAction + Chat; **Uzman / Detaylar**
  `<details>` (varsayılan KAPALI) = diğer tüm uzman panelleri (providers, data,
  learning, replay, system health, …). Registry'ye `tier: simple|expert` + 4
  yeni panel; command_signals → "Aday Sinyalleri" başlığı.

### 9. Mevcut panel iyileştirmeleri
- TimeframeMatrixPanel (item 3): global suspended iken tek banner ("All
  timeframes suspended by …"); hücreler ham aday skoru/aksiyonu sade gösterir
  (gate'i tekrar yazmaz), candidate→final ayrımı korunur.
- AgentVotesPanel (item 7): evidence chain — her agent için verdict + summary +
  actionability + evidence_used + missing_data.
- CommandSignalsPanel (item 8): "Aday Sinyalleri" — ham candidate vurgusu +
  agent act edemiyorsa NOT_ACTIONABLE rozeti.
- Replay (item 10): ReplayStatusPanel artık Uzman/Detaylar altında (ikinci plan).

## TESTS RUN
- `pytest -q` (TEST_USE_MOCK=true)
- `ruff check packages apps/api apps/tick_worker apps/learning_worker tests/contract`
- `cd apps/web && tsc --noEmit && pnpm build`

## RESULTS
- **pytest: 366/366 passed** (350 baseline + 16 yeni cockpit; live network yok).
- **ruff (CI-scope): temiz**. **tsc --noEmit: temiz**; **pnpm build: ✓ Compiled**
  (SSR prerender 4/4).
- Yeni testler (`tests/unit/test_cockpit.py`, +16): main_blocker tek-engel/no-veya/
  öncelik, data_mode eşleme, status eşleme, agent_brief DQS-OK+RiskGate (DQS
  BLOCKED yazmaz), actionable, watch conditions (expired time-stop + position
  count), decision_trace şekli, time-stop EXPIRED negatif değil/ACTIVE pozitif/
  NONE, endpoint 200, all-cells-suspended.

## LIVE DASHBOARD SMOKE (izole API 8011 gerçek veri + web SSR 3100 prod build)
- API: /health /cockpit/brief /data/snapshot /decision/matrix /dashboard/state
  /learning/summary /replay/status /ai-report/current → 200.
- cockpit/brief: status WATCHING · main_blocker RISK_GATE "RiskGate
  NO_POSITION_INCREASE" (tek engel, "veya" yok) · data_mode SIMULATION ·
  can_act false · 8 watch · 6 candidate · trace gates [RiskGate].
- ai-report no_actionable: 3 persona da "ana engel: RiskGate
  NO_POSITION_INCREASE" (no "veya").
- learning: total 3 / min 20 / sufficient false → INSUFFICIENT SAMPLE.
- matrix: suspended true, 20/20 hücre SUSPENDED → compact banner şartı.
- Web SSR 200: "Agent Brief" üstte (timeframe_matrix'ten ÖNCE), HeroScene canvas
  + PAPER_ONLY korunuyor, "Uzman / Detaylar" collapsed bölüm mevcut, 36 panel
  (32 + 4 yeni cockpit). İzole server'lar kapatıldı.

## PAPER_SAFE CHECK
- broker: none · real order: none · live execution: none · LLM karar: none
- RiskGate/DQS/KillSwitch/halt: sıfır diff, bypass yok (cockpit yalnızca okur)

## SKIPPED / NEXT
- Frontend component test runner repo'da yok → "panel renders" tsc + build +
  SSR smoke ile kanıtlandı (mevcut konvansiyon).
- NEXT: R2 deterministic rolling replay/backtest runner VEYA cockpit cilası
  (drag-drop panel düzeni, panel görünürlük tercih kalıcılığı).

## COMMITS
- `feat(web): add agent operating cockpit`
