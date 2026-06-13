# TASK RESULT

Date: 2026-06-13
Task: v2.6.1 — LLM Persona / Agent Brain Explainability (deep-data derinleşme)
Status: completed

## Prensip

v2.6 LLM persona katmanı (off|mock|groq client, budget guard, 2 saat cache,
injection guard, 3 persona, state-grounded chat) zaten mevcuttu. Ancak v2.6'dan
SONRA eklenen v2.7 deep-data dimensiyonları (D2 türev / D3 options / D4 volatilite
/ D5 catalyst half-life + event riski + rotation) LLM kompakt bağlamına
GİRMİYORDU — persona ve chat bunları açıklayamıyordu. Bu görev o boşluğu kapattı:
persona/chat/AI-report artık tüm karar zinciri özetini state-grounded okur.

LLM hâlâ karar VERMEZ; yalnızca mevcut deterministic state'i açıklar. evidence_used
HER ZAMAN koddan gelir (LLM kanıt uyduramaz); state'te olmayan dimensiyon için
"kısıt üretmiyor / state'te yok" denir, uydurma yapılmaz. RiskGate / DQS /
KillSwitch / halt sıfır diff; PAPER_SAFE / NO_EXECUTION korunur.

## Kök neden

`packages/decision/engine.py::matrix_view` derivatives/volatility/options/catalysts/
event_risk özetlerini zaten üretiyor (yalnızca dikkat-çeken, status OK + kısıtlayıcı
rejim filtreli). Fakat `packages/agent/llm/context.py::build_compact_context`
yalnızca matrix top cells / risk_gate / eski `snap.catalysts` (scheduled calendar)
+ news okuyordu; deep-data DROP ediliyordu. v2.6 bu dimensiyonlardan önce yazılmıştı.

## Ne yapıldı

### 1. Kompakt bağlam (`packages/agent/llm/context.py`)
- Yeni `_deep_data_summary(view, snap)` → kompakt `deep_data` bloğu: options
  (symbol/regime/atm_iv/iv_rv_spread/skew_25d/is_proxy), volatility (symbol/tf/
  regime/vol_state/vol_zscore), derivatives (symbol/squeeze_level/funding_bias/
  is_proxy), catalysts (event_type/actionability/affected_assets+tf/half_life/
  surprise), event_risk (level/action/restrictive/triggers≤3), rotation (status/
  score/direction/evidence≤2). `build_compact_context` çıktısına eklendi.
- Digest stabil tutuldu: yalnızca snapshot_id/generated_at volatil; deep_data'da
  hours_until gibi sürekli değişen alan YOK → 2 saat cache güvenli.

### 2. Persona (`packages/agent/llm/report.py`)
- `_deep_evidence(persona, ctx)` + `_deep_concerns(persona, ctx)` (her ikisi
  deterministik). Risk Officer: options stresi (PUT_SKEW/CALL_SKEW/TERM_STRESS/
  RICH_VOL), volatilite (ELEVATED/EXTREME/shock/expansion), türev squeeze (HIGH/
  ELEVATED), catalyst (NO_POSITION_INCREASE/CAUTION) kanıt+itiraz. Macro Strategist:
  rotation + volatilite rejimi + options downside stresi + event riski senaryo.
- `_evidence_for` deep evidence'ı ekler; `_fallback_concerns` deep concerns'i ekler;
  macro fallback summary'sine volatilite + rotation eklendi. Persona briefleri
  deep-data'ya atıf yapar (LLM yolu da bağlamı görür). evidence_used HÂLÂ koddan.

### 3. Chat (`packages/agent/llm/chat.py`)
- Yeni grounded handler'lar: `_options_answer` / `_volatility_answer` /
  `_derivatives_answer` / `_rotation_answer` / `_catalyst_answer`. proxy
  dimensiyonları (skew_25d, squeeze) açıkça "proxy — gerçek greeks/liquidation
  değil" der. Veri yoksa "kısıt üretmiyor", uydurma yok.
- `_grounded_answer` intent sırası: missing → deep-data (options/vol/türev/
  rotation/catalyst) → risk_gate → symbol-why → waiting → overview. "RiskGate neyi
  engelledi?" deep-data değil risk_gate'e gider (yanlış yönlenme testli).

### 4. Frontend (additive, şema değişmedi)
- `AIReportPanel`: persona blokunda `evidence_used` satırı (≤6) + "Açıklayıcı
  katman · yürütme yetkisi yok — final karar deterministik engine + RiskGate" rozeti.
- `ChatPanel`: öneri sorularına "Options risk ne diyor?", "Volatility neden
  kısıtladı?", "Funding / türev ne diyor?" eklendi.
- Persona/chat response şekli değişmedi → openapi/TS api.ts SIFIR diff → codegen
  drift testi otomatik yeşil.

### 5. Tests (`tests/unit/test_llm_persona.py`, +11)
- deep_data summary filtre/taşıma; persona fallback deep-data grounding (RO kanıt+
  itiraz, macro rotation/vol); boş-state'te kanıt UYDURMAMA; 5 chat intent grounded
  + proxy disclaimer; "RiskGate neyi engelledi?" yanlış yönlenme yok; endpoint
  state-grounded. Testlerde live network yok (urlopen bekçi korunur).

## Sonuç

- **pytest: 334/334** (323 baseline + 11 yeni); live network yok.
- **ruff (CI-scope): temiz**; **tsc --noEmit: temiz**; **pnpm build: yeşil**
  (✓ Compiled successfully, SSR prerender 4/4).
- **Live smoke** (izole API 127.0.0.1:8011, gerçek Deribit, LLM_MODE=off):
  - `/ai-report/current`: risk_officer deep-evidence `options:BTCUSD CHEAP_VOL`,
    `options:ETHUSD PUT_SKEW_STRESS`, `volatility:*`, `derivatives:*`, `catalyst:*`;
    concern "options stresi ETHUSD: PUT_SKEW_STRESS (skew proxy)". macro
    `rotation:bearish 39.0` + volatilite + options.
  - `/chat`: 5 deep-data intent gerçek değerlerle grounded (BTC ATM IV 0.4096
    CHEAP_VOL, proxy uyarısı); rotation/catalyst gerçek; bypass → guard refusal.
  - Web SSR (izole 127.0.0.1:3100): 200, 32 panel + HeroScene canvas + PAPER_ONLY.
  - İzole smoke server'ları (8011/3100) sonra kapatıldı; kullanıcının 3000/8000
    ortamı bozulmadı (eski E_YAY CODEX launch agent'ları ayrı dizinde).

## PAPER_SAFE check
- broker: none · real order: none · live execution: none
- LLM karar vermez; decision/risk/paper akışına geri yazım yok
- RiskGate/DQS/KillSwitch/halt: sıfır diff, bypass yok (injection guard değişmedi)
- deep-data persona/chat'te yalnızca AÇIKLANIR; karar zincirinde yalnızca kısıtlayıcı
