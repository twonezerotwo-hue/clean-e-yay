# NEXT TASK — v2.6 LLM Persona (Groq, narrative-only)

Önerilen sıra (T2 sonrası): **v2.6 önce**, T3 sonra.
Gerekçe: TimeframeMatrix + risk evidence zinciri artık zengin — LLM
personaların anlatacağı gerçek state var. T3 catalyst half-life motoru
gerçek haber feed'i gerektirir → **v2.7 deep data ile birlikte** yapılır
(CatalystImpact contract'ı T0'dan beri hazır bekliyor).

## Scope

- `packages/agent/llm/` — Groq client (env `GROQ_API_KEY`; anahtar yoksa
  graceful degrade: panel "LLM yok" gösterir, sistem çalışmaya devam eder).
- Token budget guard: günlük bütçe dosyası (`data/runtime/llm_budget.json`),
  aşılırsa LLM çağrısı yapılmaz (deterministik fallback narrative).
- Personalar: analyst / risk_officer / macro_strategist — girdi olarak
  YALNIZCA doğrulanmış snapshot + decision matrix + risk evidence alır;
  çıktı narrative-only.
- `/api/v1/ai-report/current` gerçek LLM narrative'i (cache'li, bütçeli);
  `/api/v1/chat` basit soru-cevap (aynı evidence bağlamı).
- AIReportPanel/ChatPanel mevcut — backend'i gerçek kaynağa bağla;
  provenance damgası (LLM_GENERATED + model adı) ekle.
- Timeframe bağlamı: rapor DecisionMatrix'ten TF özetini anlatır
  (örn. "1d swing long, 15m scout suspended").

## Hard rules (SAFETY_RULES + ARCHITECTURE §2)

- **LLM karar vermez** — hiçbir LLM çıktısı decision/risk/paper akışına
  geri yazılmaz; sadece açıklar/eleştirir/raporlar.
- RiskGate / DQS / KillSwitch / halt / timeframe politikası sıfır diff.
- API anahtarı yokken ve testlerde network ÇAĞRISI YOK (client mock'lanır);
  CI'da live LLM yok.
- PAPER_SAFE / NO_EXECUTION.

## Tests

- LLM client mock'lu: rapor üretimi, bütçe aşımı → fallback, anahtar yok →
  graceful degrade.
- LLM çıktısının decision path'ine yazılmadığının testi (decision matrix
  LLM'siz/LLM'li birebir aynı).
- pytest + ruff + tsc + pnpm build yeşil; live network yok.

## Sonra

- **v2.7 deep data** + **T3 catalyst half-life motoru** (funding, OI,
  options IV, gerçek haber feed'i + CatalystImpact engine).
