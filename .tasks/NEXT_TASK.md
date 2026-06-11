# NEXT TASK — v2.6 LLM Persona (Groq, narrative-only)

AI yalnızca açıklar/eleştirir — karar vermez. Deterministic decision +
RiskGate tek karar otoritesidir.

## Scope

- `packages/agent/llm_client.py` (yeni): Groq client + token budget
  guard (`agent.groq_daily_token_budget`, file-backed günlük sayaç).
  `GROQ_API_KEY` yoksa veya budget aşıldıysa → mevcut deterministik
  narrative fallback (hata yok, degrade).
- Personas: `analyst`, `risk_officer`, `macro_strategist`
  (thresholds.yaml `agent.personas`); quorum_required=2 mevcut
  build_votes akışıyla uyumlu kalsın — LLM yalnızca narrative üretir,
  vote'ları değiştirmez.
- `/api/v1/ai-report/current` — LLM narrative (varsa) + persona
  yorumları; `mode` damgası (provenance) korunur; LLM çıktısı
  `llm_generated: true` ile işaretlenir.
- `POST /api/v1/chat` — dashboard ChatPanel'e bağlanır; yalnızca mevcut
  snapshot/decision/risk state'i üzerinden cevap verir; trade komutu
  almaz/uygulamaz.
- Dashboard: `AIReportPanel` LLM narrative + persona bölümü;
  `ChatPanel` gerçek POST'a bağlanır. Selector + registry mevcut.

## Rules

- `PAPER_SAFE / NO_EXECUTION` — LLM hiçbir aksiyon tetikleyemez.
- LLM karar vermez; RiskGate/DQS/halt mantığına dokunulmaz.
- Network yalnızca Groq API (kullanıcı onayladı: roadmap v2.6); key yoksa
  tamamen offline degrade.
- Token budget guard zorunlu; budget aşımı → fallback + uyarı.
- Test offline: mock LLM client (network yok), budget guard testi,
  fallback testi, chat endpoint 200, key'siz davranış.
