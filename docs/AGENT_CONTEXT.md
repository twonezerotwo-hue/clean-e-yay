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

## Aktif yol haritası (devam eden iş)

**Adaptif kendini-eğitme (CP1–CP7)** → [ROADMAP.md](ROADMAP.md#adaptif-kendini-eğitme-yol-haritası-cp1cp7).
Atıl öğrenme/shadow verisini güvenle döngüye sokma planı + **değişmez yasalar**
(additive · flag-OFF=aynı · shadow-önce · rollback · off-tick · ölü-kod-yok).
Durum: CP1✅ CP2✅, **sırada CP3 (yön güvenlik kasası)**. Başka oturum/AI buradan
devam edebilir — fazlar, kırıdığı çizgiler ve geliştirme deseni orada yazılı.

## Detay

Tam mimari için → [ARCHITECTURE.md](../ARCHITECTURE.md) (sadece derin
mimari/tasarım sorularında oku — günlük görevler için gerekmez).
