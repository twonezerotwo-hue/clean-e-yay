# Clean E-yAy — Tam Mimari

> Bu belge **Clean E-yAy**'in tam agent sistemi + paralel 3D dashboard'a
> geçiş için **nihai temiz plan**'dır. Yeni iş başlamadan önce bu belge
> okunur. Sapma gerekirse PR açıklamasında nedeni yazılır.
>
> Felsefe: *eski sistemin zekâsını taşı, dağınıklığını taşıma.*

```text
Clean E-yAy
│
├─ contracts/                 # OpenAPI / schema tek doğruluk kaynağı
│
├─ packages/
│  ├─ data/                    # veri toplama + DQS + snapshot
│  ├─ regime/                  # piyasa rejimi
│  ├─ consensus/               # sinyal/agent birleşimi
│  ├─ decision/                # deterministik karar motoru
│  ├─ risk/                    # risk gate / kill switch / sizing
│  ├─ paper/                   # paper trading lifecycle
│  ├─ learning/                # calibration / mistake memory / rebalance
│  ├─ agent/                   # planner / specialist agents / orchestrator
│  └─ shared/                  # ortak enum, util, constants
│
├─ apps/
│  ├─ api/                     # FastAPI backend
│  ├─ tick_worker/             # periyodik market scan + paper tick
│  ├─ learning_worker/         # günlük review + rebalance proposal
│  └─ web/                     # 3D dashboard cockpit
│
├─ config/
│  ├─ source_registry.yaml
│  ├─ feature_registry.yaml
│  ├─ thresholds.yaml
│  ├─ weights_v1.yaml
│  └─ risk_policy.yaml
│
├─ data/
│  ├─ snapshots/
│  ├─ decisions/
│  ├─ paper/
│  ├─ learning/
│  └─ audit/
│
└─ tests/
```

---

## 1. Ana çalışma akışı

```text
Goal
  ↓
Planner
  ↓
Data Hunter
  ↓
Data Validator
  ↓
Market Snapshot
  ↓
Feature Builder
  ↓
Specialist Agents
  ↓
Decision Orchestrator
  ↓
Risk Gate
  ↓
Paper Trading Agent
  ↓
Monitoring
  ↓
Learning Agent
  ↓
Rebalance Proposal
  ↓
Owner Approval
```

E-yAy artık şöyle çalışacak:

```text
Sen veri vermezsin.
Sistem görevi alır.
Hangi veriye ihtiyacı olduğunu çıkarır.
Veriyi kendi bulur.
Doğrular.
Agent'lara dağıtır.
Karar üretir.
Riskten geçirir.
Paper trade dener.
Sonucu izler.
Hatalarından öğrenir.
Sana rebalance önerisi verir.
```

---

## 2. Ana güvenlik ilkesi

```text
PAPER_SAFE / NO_EXECUTION
```

Mutlak kurallar:

```text
Gerçek broker yok.
Gerçek emir yok.
Live execution yok.
Paper trading dışında işlem yok.
LLM karar vermez.
AI sadece açıklar, eleştirir, raporlar.
Final karar deterministic decision + risk gate üzerinden çıkar.
Owner onayı olmadan gerçek aksiyon yok.
```

---

## 3. `packages/data` — Data Hunter + Validator

```text
packages/data/
├─ __init__.py
├─ models.py
├─ normalization.py
├─ registry.py
├─ providers.py
├─ quality.py
├─ ingestion.py
├─ snapshot_store.py
├─ technicals.py
├─ news.py
├─ calendar.py
└─ fixtures.py
```

### Görevi

```text
Fiyatları toplar.
OHLCV toplar.
Makro veri toplar.
Haber/takvim/funding/flow verisini çeker.
Veriyi normalize eder.
Timestamp ve source ekler.
DQS hesaplar.
Snapshot üretir.
Diske yazar.
```

### Ana modeller

```python
MarketObservation:
    observation_id
    code
    value
    unit
    source
    timestamp
    freshness_seconds
    verified
    fallback_used
    data_quality_score
    error
```

```python
MarketSnapshot:
    snapshot_id
    generated_at
    observations
    asset_quality
    snapshot_quality
    provider_meta
    warnings
```

### Veri kaynakları

Başlangıç:

```text
MockProvider
YFinanceProvider
CoinGeckoProvider
FREDProvider
NewsProvider placeholder
CalendarProvider placeholder
```

Sonra:

```text
Binance / Bybit funding
Deribit options IV/skew/OI
ETF flow
economic calendar real API
geo-news
chart patterns
```

### DQS seviyeleri

```text
Observation DQS
Asset DQS
Snapshot DQS
```

Kurallar:

```text
timestamp yoksa → verified=false
value yoksa → BLOCKED
freshness eskiyse → DEGRADED
fallback varsa → score düşer
source error varsa → score düşer
cross-source sapma yüksekse → score düşer
```

---

## 4. `packages/agent` — Planner + Specialist Agents

```text
packages/agent/
├─ __init__.py
├─ models.py
├─ planner.py
├─ evidence.py
├─ orchestrator.py
├─ macro_agent.py
├─ technical_agent.py
├─ news_agent.py
├─ flow_agent.py
├─ risk_agent.py
├─ strategist_agent.py
└─ persona.py
```

### Planner

Kullanıcı/scheduler goal verir:

```text
BTC için trade fırsatı var mı?
Piyasayı tara.
Risk durumunu kontrol et.
Bugün paper trading açılır mı?
```

Planner bunu veri ihtiyacına çevirir:

```python
AgentPlan:
    required_observations
    required_providers
    agents_to_run
    missing_data_policy
```

Örnek BTC review:

```text
BTC price
BTC OHLCV
DXY
VIX
HYG
QQQ
funding
OI
BTC ETF flow
crypto headlines
```

### Specialist Agent çıktısı

Her agent standart çıktı verir:

```python
AgentFinding:
    finding_id
    agent_name
    asset
    vote: ALLOW / CAUTION / BLOCK / ABSTAIN
    direction
    confidence
    summary
    evidence
    used_observations
    invalidation
    missing_data
```

### Agent'lar

```text
TechnicalAgent
MacroAgent
RiskAgent
NewsAgent
FlowAgent
StrategistAgent
LearningAgent
```

Kural:

```text
Agent doğrudan internetten rastgele veri çekmez.
Data Hunter tarafından doğrulanmış snapshot'ı kullanır.
Eksik veri varsa ABSTAIN/DEGRADED verir.
```

---

## 5. `packages/regime`

```text
packages/regime/
├─ __init__.py
├─ models.py
├─ classifier.py
└─ rules.py
```

### Görevi

Piyasa rejimini belirler:

```text
RISK_ON
TRANSITIONING
DEFENSIVE
CRISIS
```

Girdi:

```text
DXY
VIX
HYG/LQD
US10Y/US2Y
Gold
Brent
BTC
QQQ/SPY
news risk
```

Çıktı:

```python
RegimeSnapshot:
    regime
    confidence
    drivers
    blockers
    warnings
```

---

## 6. `packages/consensus`

```text
packages/consensus/
├─ __init__.py
├─ models.py
├─ scoring.py
└─ aggregator.py
```

### Görevi

Agent ve sinyal çıktısını birleştirir.

```python
ConsensusSnapshot:
    asset
    direction_score
    strength_score
    agreement_score
    confirmed_count
    pending_count
    blocking_count
    evidence
```

Önemli ayrım:

```text
direction_score = yön
strength_score = sinyal gücü
agreement_score = agent uyumu
```

Tek `score` ile her şeyi ölçmeye çalışma.

---

## 7. `packages/decision`

```text
packages/decision/
├─ __init__.py
├─ models.py
├─ policy.py
├─ orchestrator.py
└─ scenarios.py
```

### Görevi

Deterministik karar üretir.

```python
AgentDecision:
    decision_id
    action:
        NO_TRADE
        WATCH
        SCOUT_ALLOWED
        CONFIRMATION_REQUIRED
        RISK_REDUCE
        KILL_SWITCH
    confidence
    reason
    supporting_agents
    blocking_agents
    required_confirmations
    risk_gate_required
```

Kural:

```text
RiskAgent BLOCK ise trade yok.
DQS düşükse trade yok.
Çoğunluk ABSTAIN ise WATCH.
Technical ALLOW ama macro CAUTION ise sadece SCOUT.
```

---

## 8. `packages/risk`

```text
packages/risk/
├─ __init__.py
├─ models.py
├─ gate.py
├─ sizing.py
├─ correlation.py
├─ drawdown.py
└─ kill_switch.py
```

### Görevi

Kararın işlem planına dönüşüp dönüşemeyeceğini belirler.

```python
RiskGate:
    status: PASS / CAUTION / BLOCK
    risk_action:
        HOLD
        KILL_SWITCH
        RISK_REDUCE
        NO_POSITION_INCREASE
    hard_blockers
    soft_warnings
    dqs_score
    rr_valid
    position_size_valid
    correlation_valid
    drawdown_valid
```

Hard gate kuralları:

```text
DQS düşük → BLOCK
Kill switch active → BLOCK
RR geçersiz → BLOCK
Max DD aşıldı → BLOCK
Daily loss aşıldı → BLOCK
Korelasyon exposure yüksek → CAUTION/BLOCK
Event risk yüksek → CAUTION
```

---

## 9. `packages/paper`

```text
packages/paper/
├─ __init__.py
├─ models.py
├─ simulator.py
├─ position_manager.py
├─ lifecycle.py
├─ execution_sim.py
└─ state_store.py
```

### Görevi

Sadece paper trading.

```python
PaperTradePlan:
    plan_id
    decision_id
    asset
    side
    lifecycle:
        SCOUT_ENTRY
        CONFIRMATION_ENTRY
        MOMENTUM_ADD
        RISK_REDUCE
        KILL_SWITCH_EXIT
        TIME_STOP_EXIT
        REGIME_FLIP_EXIT
        WATCH_ONLY
        NO_TRADE
    entry_price
    stop_loss
    take_profit_1
    take_profit_2
    risk_pct
    requires_owner_approval
    reason
```

Paper simulation gerçekçi olmalı:

```text
spread
slippage
fee
latency
partial fill
time stop
regime flip exit
news shock exit
```

---

## 10. `packages/learning`

```text
packages/learning/
├─ __init__.py
├─ models.py
├─ decision_log.py
├─ prediction_review.py
├─ calibration.py
├─ mistake_memory.py
├─ auto_weight_trainer.py
├─ rebalance.py
└─ owner_feedback.py
```

### Görevi

Sistem kendi sonuçlarını izler.

```text
Hangi karar tuttu?
Hangi agent yanıldı?
Hangi confidence gerçek çıktı?
Hangi hata tekrarlandı?
Owner hangi öneriyi reddetti?
Owner haklı çıktı mı?
```

### Çıktı

```python
RebalanceProposal:
    proposal_id
    based_on_period
    agent_weight_changes
    feature_weight_changes
    threshold_suggestions
    reasons
    requires_owner_approval = True
```

Kural:

```text
Sistem otomatik weight değiştirmez.
Proposal üretir.
Owner onaylarsa weights_v1.x.yaml yazılır.
```

---

## 11. `apps/api`

```text
apps/api/
├─ main.py
├─ routers/
│  ├─ health.py
│  ├─ data.py
│  ├─ agent.py
│  ├─ regime.py
│  ├─ decision.py
│  ├─ risk.py
│  ├─ paper.py
│  ├─ learning.py
│  ├─ dashboard.py
│  ├─ ai_report.py
│  ├─ chat.py
│  ├─ replay.py
│  └─ telemetry.py
└─ dependencies.py
```

### Ana endpointler

```text
GET  /api/v1/health
GET  /api/v1/data/snapshot/latest
POST /api/v1/agent/run
GET  /api/v1/regime-report/current
GET  /api/v1/dashboard/state
GET  /api/v1/ai-report/current
POST /api/v1/chat
GET  /api/v1/paper-trading/state
POST /api/v1/paper-trading/tick
POST /api/v1/owner-feedback
GET  /api/v1/learning/summary
POST /api/v1/learning/rebalance/propose
POST /api/v1/learning/rebalance/approve
GET  /api/v1/replay/{snapshot_id}
POST /api/v1/telemetry/panel-error
```

---

## 12. Worker mimarisi

### `apps/tick_worker`

```text
Periyodik çalışır.
Market scan yapar.
Snapshot üretir.
Agent run tetikler.
Risk gate kontrol eder.
Paper tick çalıştırır.
Halt varsa durur.
```

### `apps/learning_worker`

```text
Günlük çalışır.
Trade sonuçlarını inceler.
Agent hit-rate hesaplar.
Calibration günceller.
Mistake memory üretir.
Rebalance proposal yazar.
```

---

## 13. `apps/web` dashboard mimarisi

Dashboard backend ile paralel büyür.

```text
apps/web/
├─ app/
│  ├─ (dashboard)/page.tsx
│  ├─ api/
│  ├─ layout.tsx
│  ├─ error.tsx
│  ├─ loading.tsx
│  └─ not-found.tsx
│
├─ components/
│  ├─ shell/
│  │  ├─ ErrorBoundary.tsx
│  │  ├─ DashboardGrid.tsx
│  │  ├─ PanelFrame.tsx
│  │  ├─ PanelHeader.tsx
│  │  ├─ PanelToggle.tsx
│  │  ├─ EmptyState.tsx
│  │  ├─ LoadingState.tsx
│  │  └─ DataQualityBadge.tsx
│  │
│  ├─ panels/
│  │  ├─ DecisionPanel/
│  │  ├─ RiskGatePanel/
│  │  ├─ AgentVotesPanel/
│  │  ├─ PositionChecksPanel/
│  │  ├─ AIReportPanel/
│  │  ├─ ChatPanel/
│  │  ├─ CommandSignalsPanel/
│  │  ├─ EventCalendarPanel/
│  │  ├─ ScenarioPanel/
│  │  ├─ CapitalRotationPanel/
│  │  ├─ NewsPanel/
│  │  ├─ PatternsPanel/
│  │  ├─ LearningPanel/
│  │  ├─ TradingPanel/
│  │  ├─ ReplayStatusPanel/
│  │  ├─ PanelAuditPanel/
│  │  ├─ DataQualityPanel/
│  │  ├─ ProviderStatusPanel/
│  │  ├─ SnapshotPanel/
│  │  ├─ MarketDataPanel/
│  │  ├─ CalibrationPanel/
│  │  ├─ MistakeMemoryPanel/
│  │  ├─ CorrelationPanel/
│  │  ├─ DrawdownGuardPanel/
│  │  └─ SystemHealthBar/
│  │
│  ├─ charts/
│  ├─ tables/
│  └─ visuals/
│
├─ hooks/
│  ├─ useDashboardState.ts
│  ├─ useAgentRun.ts
│  ├─ usePanelAudit.ts
│  ├─ useOwnerFeedback.ts
│  ├─ useReplayStatus.ts
│  ├─ useRealtimeRefresh.ts
│  └─ usePanelVisibility.ts
│
├─ providers/
│  ├─ QueryProvider.tsx
│  ├─ I18nProvider.tsx
│  └─ ThemeProvider.tsx
│
├─ lib/
│  ├─ api/                       # generated only
│  ├─ queries/
│  ├─ selectors/
│  ├─ panel-registry.ts
│  ├─ format.ts
│  ├─ constants.ts
│  ├─ guards.ts
│  └─ telemetry.ts
│
├─ messages/
│  ├─ tr.json
│  └─ en.json
│
└─ types/
   ├─ generated/
   └─ ui.ts
```

---

## 14. Dashboard paralel büyüme kuralı

Her backend fazının dashboard karşılığı olacak.

```text
G1 gerçek provider → DataQualityPanel / ProviderStatusPanel / SnapshotPanel
G2 auto-weight trainer → LearningPanel / RebalanceProposal
G6 calibration → CalibrationPanel
G3 mistake memory → MistakeMemoryPanel
G4 correlation sizing → CorrelationPanel / ExposureCluster
G5 daily loss halt → DrawdownGuardPanel / KillSwitchTimeline
LLM persona → AIReportPanel / ChatPanel
```

Kural:

```text
Backend yeni state üretirse dashboardda görünür olacak.
Frontend hesap yapmayacak.
Selector kullanacak.
Panel registry'ye eklenecek.
page.tsx büyütülmeyecek.
```

---

## 15. OpenAPI / codegen kuralı

```text
contracts/openapi.yaml = tek doğruluk kaynağı
```

Akış:

```text
OpenAPI
  ↓
types/generated/api.ts
  ↓
lib/queries
  ↓
selectors
  ↓
panels
```

Manuel type yazma sadece `types/ui.ts` içinde olur.

---

## 16. Tam agent seviyesine geçiş için fazlar

### v2.1 — Data Hunter + Validator

```text
Gerçek provider
DQS
fallback
snapshot store
technicals
/data endpoints
dashboard data panels
```

### v2.2 — Planner + Agents + Decision

```text
AgentGoal
AgentPlan
Technical/Macro/Risk agents
Decision Orchestrator
AgentFindings
```

### v2.3 — Risk + Paper

```text
RiskGate
correlation-aware sizing
drawdown halt
paper lifecycle
position manager
```

### v2.4 — Learning

```text
auto-weight trainer
calibration
mistake memory
owner feedback
rebalance proposal
```

### v2.5 — Dashboard Cockpit

```text
All panels
3D hero
panel audit
replay
trading timeline
learning dashboard
```

### v2.6 — LLM Persona

```text
Groq/Claude client
token budget guard
AI report
ChatPanel
risk officer / analyst / strategist personas
```

### v2.7 — Deep Data

```text
funding
OI
options IV/skew
ETF flow
real calendar
geo-news
chart pattern
correlation universe
```

---

## 17. Operasyonel mimari

```text
docker-compose
.env.example
pnpm-lock.yaml
CI
contract tests
snapshot replay
telemetry
logging
audit
```

Gerekli operasyonel parçalar:

```text
api + tick_worker + learning_worker + web tek komutla kalkmalı
OpenAPI contract testleri olmalı
frontend panel-error telemetry backende akmalı
snapshot replay diskten çalışmalı
secrets .env.example ile yönetilmeli
```

---

## 18. En önemli 10 kural

```text
1. Eski sistemin zekasını taşı, dağınıklığını taşıma.
2. Veri doğrulanmadan karar yok.
3. AI karar vermez, açıklar.
4. Risk Gate final kapıdır.
5. Paper-safe dışına çıkma.
6. Frontend hesap yapmaz.
7. Her karar evidence taşır.
8. Her agent used_observations yazar.
9. Öğrenme proposal üretir, owner onaylar.
10. Dashboard backend ile paralel büyür.
```

---

## 19. Nihai hedef

Clean E-yAy sonunda şu olacak:

```text
Kendi verisini bulan,
veriyi doğrulayan,
piyasayı agent'lara okutan,
deterministik karar üreten,
riskten geçiren,
paper trade deneyen,
sonucu izleyen,
hatalarını hafızaya alan,
rebalance öneren,
3D cockpit dashboardda her şeyi kanıt zinciriyle gösteren
tam agent sistemi.
```

Kısa hali:

```text
Goal → Plan → Fetch → Validate → Analyze → Decide → RiskGate → Paper → Learn → Owner Approval
```
