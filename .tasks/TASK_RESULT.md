# TASK RESULT

Date: 2026-06-12
Task: v2.6 — LLM persona (Groq, narrative-only)
Status: completed

## Ne yapıldı

LLM, karar vermeyen bir anlatı/persona katmanı olarak eklendi: agent'ın
beynini açıklar, eleştirir, özetler ve kullanıcı sorularını mevcut state'e
göre yanıtlar. Hiçbir LLM çıktısı decision/risk/paper akışına geri yazılmaz.

### `packages/agent/llm/` (yeni paket)

- **client.py** — `LLM_MODE=off|mock|groq` (set değilse: anahtar varsa groq,
  yoksa off). Groq OpenAI-uyumlu chat completions adapter'ı (urllib);
  **anahtar yoksa network çağrısı YAPMADAN None** döner; network/API
  hatasında exception kaçırılmaz → None → deterministik fallback.
- **budget.py** — günlük token bütçesi `data/runtime/llm_budget.json`
  (env `LLM_DAILY_TOKEN_BUDGET`, default 100k; `LLM_MAX_TOKENS_PER_REQUEST`
  default 600). Bütçe aşılırsa LLM çağrısı yapılmaz.
- **cache.py** — 2 saatlik file-backed yanıt cache'i
  (`data/runtime/llm_cache.json`, env `LLM_CACHE_TTL_SEC`). Anahtar İÇERİK
  bazlı (context digest — snapshot_id/generated_at hariç) → state aynı
  kaldıkça cache vurur.
- **context.py** — prompt'a giren KOMPAKT state bağlamı: snapshot_id, DQS
  özeti, provider sorunları, decision matrix top hücreleri, candidate vs
  final farkları, blocked_by nedenleri, RiskGate, halt, korelasyon
  cluster'ları, paper state, learning uyarıları, haber/katalizör başlıkları.
  **Full raw market data prompt'a gömülmez.**
- **guard.py** — prompt injection / bypass kalıpları (TR+EN) LLM'e
  ulaşmadan güvenli ret; LLM sistem prompt'u sert kurallar taşır
  (karar verme yok, bağlam dışı uydurma yok, PAPER_SAFE).
- **report.py** — 3 persona: Market Analyst / Risk Officer / Macro
  Strategist. Çıktı: summary, concerns, **evidence_used (her zaman
  backend'de deterministik üretilir — LLM kanıt uyduramaz)**, missing_data,
  actionability, what_would_change_my_mind. LLM yoksa/bütçe dolu/hata →
  deterministik fallback bölümleri.
- **chat.py** — state-grounded soru-cevap: guard → deterministik grounded
  yanıt (her zaman üretilir; sembol/TF/intent algılama: "neden açmadın",
  "riskgate", "hangi veri eksik", "ne bekliyor") → LLM varsa aynı bağlam +
  grounded yanıtla anlatımı akıcılaştırır.

### API

- `GET /api/v1/ai-report/current` additive zenginleşti: `personas[]`,
  `llm` meta (mode/model/source/fallback_reason/cached/tokens), 
  `timeframe_summary` (TF satırları, candidate vs final diffs, blocked_by,
  paper_actions), `no_actionable_decision`. DQS BLOCKED veya kısıtlayıcı
  risk gate → verdict `no_trade` + "NO ACTIONABLE DECISION" narrative modu.
- **Yeni `POST /api/v1/chat`** (`apps/api/routers/chat.py`) — ChatRequest
  {message ≤2000}; yanıt: answer, refused, evidence_used, snapshot_id,
  llm meta, provenance mode bloğu.
- OpenAPI: `/chat` path + PersonaSection/TimeframeSummary/LLMMeta/
  ChatRequest/ChatResponse şemaları; AIReport additive alanlar.

### Dashboard

- **AIReportPanel** — persona bölümleri (başlık + summary + concerns +
  actionability + "fikrimi değiştirir" + eksik veri), `LLM_GENERATED ·
  <model>` / `DETERMINISTIC` provenance rozeti, NO ACTIONABLE DECISION
  banner'ı, timeframe özeti satırları.
- **ChatPanel** — gerçek `/api/v1/chat`'e bağlı: öneri soruları, mesaj
  geçmişi, kanıt satırı (evidence_used), GUARD/DETERMINISTIC/LLM_GENERATED
  damgası. Registry'de `chat` artık defaultVisible.
- Selector'lar `lib/selectors/ai.ts`; hook `useChat`; client `api.chat`;
  tipler `types/generated/api.ts`. page.tsx büyümedi (ChatPanel zaten
  GridCell'deydi).

## Güvenlik garantileri

- **LLM karar vermez** — `packages/agent/llm` hiçbir decision/risk/paper
  modülüne yazmaz; decision matrix LLM'li/LLM'siz birebir aynı (testli).
- RiskGate / DQS veto / KillSwitch / halt / timeframe politikası sıfır diff.
- DQS BLOCKED → "no actionable decision" modu (testli).
- "RiskGate'i bypass et" → güvenli ret (testli, TR+EN kalıplar).
- Anahtar yokken ve testlerde network çağrısı yok (urlopen bekçi fixture).
- PAPER_SAFE / NO_EXECUTION — broker/emir/live execution yok.

## Tests run

- `pytest -q` → **150/150 passed** (18 yeni: mode off→fallback, groq
  anahtarsız→network'süz degrade, Groq adapter mock parse + network error,
  budget guard + bütçe aşımı→fallback, persona fallback bölümleri, mock LLM
  + cache (2. çağrı cached, bütçe harcamaz), evidence backend'den, AI report
  endpoint personas+tf_summary, DQS BLOCKED→no_actionable, decision matrix
  LLM'li/LLM'siz aynı, chat BTC blocked_by + riskgate + missing data +
  injection refusal ×3 + LLM hata→grounded fallback, cache TTL).
- `ruff check packages apps/api apps/tick_worker apps/learning_worker` → yeşil.
- `pnpm exec tsc --noEmit` + `pnpm build` → yeşil.

## Live smoke

- API: `/api/v1/health` 200, `/api/v1/ai-report/current` 200 (3 persona +
  timeframe_summary + llm meta), `POST /api/v1/chat` 200 ("Neden BTC
  açmadın?" → risk gate gerekçeli grounded yanıt; bypass → refused=true).
- Web: SSR 200, **28 panel**, ChatPanel yeni UI ("state-grounded · LLM
  karar vermez" + öneri soruları), HeroScene + PAPER_ONLY korunuyor.
- LLM mode `off` (GROQ_API_KEY yok) → deterministik fallback ile tam
  fonksiyonel; anahtar eklenince ek deploy gerekmez.

## Result

passed

## Next (öneri)

**OPS — contract/replay testleri + operasyonel sağlamlaştırma** (v2.7'den
ÖNCE öneriyorum): 16 endpoint'in TS tipleri elle senkronize ediliyor
(codegen "not yet implemented") ve OpenAPI drift'ini hiçbir test yakalamıyor.
v2.7 deep data (funding/OI/options IV + gerçek haber feed'i + T3 catalyst
half-life motoru) provider yüzeyini büyütmeden önce sözleşme testleri +
snapshot replay + telemetry hattı riski düşürür. v2.7 ondan sonra.
