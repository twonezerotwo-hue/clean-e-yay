# Agent Context — Clean E-yAy

Clean E-yAy = tam agent sistemi (paper-trading karar-destek).

## Ana akış

```
Goal → Plan → Fetch → Validate → Analyze → Decide → RiskGate → Paper → Learn → Owner Approval
```

## Paketler

- `packages/data` — provider, DQS, snapshot
- `packages/agent` — planner, specialist agents, evidence
- `packages/regime` — market regime sınıflandırıcı
- `packages/consensus` — agent/signal aggregation
- `packages/decision` — deterministic decision
- `packages/risk` — risk gate, kill switch, sizing
- `packages/paper` — paper trading lifecycle
- `packages/learning` — calibration, mistake memory, rebalance
- `apps/api` — FastAPI endpoints (sadece HTTP yönlendirici)
- `apps/tick_worker` — 30sn döngü, paper trading tick
- `apps/learning_worker` — kalibrasyon / walk-forward
- `apps/web` — Next.js 3D cockpit dashboard

## Final hedef

Kendi verisini bulan, doğrulayan, agent'lara dağıtan, karar üreten,
riskten geçiren, paper trade deneyen ve sonuçtan öğrenen sistem.

## Detay

Tam mimari için → [ARCHITECTURE.md](../ARCHITECTURE.md) (sadece derin
mimari/tasarım sorularında oku — günlük görevler için gerekmez).
