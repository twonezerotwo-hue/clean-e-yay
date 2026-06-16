# Technical Architecture — İlerleme & Makineler-Arası Devir (HANDOFF)

> **Bu dosya "kaldığımız yer"in TEK doğruluk kaynağıdır.** Claude'un yerel hafızası
> (`~/.claude`) makineler/hesaplar arasında TAŞINMAZ — bu yüzden durum repoya yazılır.
> İki bilgisayar arasında (token bitince diğerine geçerek) kesintisiz devam etmek için
> aşağıdaki ritüeli izle. Spec/build incili: [`TECHNICAL_ANALYSIS_SPEC.md`](TECHNICAL_ANALYSIS_SPEC.md).

- **Repo:** `clean-e-yay` · **Branch:** `phase-3-dashboard-transplant`
- **Remote:** https://github.com/twonezerotwo-hue/clean-e-yay

---

## 🔖 ŞU AN NEREDEYİZ  (her oturum sonu burayı güncelle)

**Tamamlanan:** Spec adım **1–7 (tam)** + **8 (kalibrasyon + tf_weights auto-tune proposal)** +
**9 (controlled activation — kod-tam, gözlem fazı)** + **§4.5 (reversal + chart-pattern)**.
- **6** — `packages/risk/trade_economics.py`: cost + R:R kapısı (RiskGate-side, yalnız kısıtlayıcı).
  Guard'lar: `test_bad_rr_blocks_entry`, `test_scalp_below_cost_blocked`.
- **7** — `agent_pipeline.py` composer + `GET /technical/agent-matrix` + `AgentMatrixPanel` (browser-doğrulandı).
- **8** — `tf_calibration.py` (verified → per-TF hit-rate/expectancy + trust-gate) **artık learning_worker
  döngüsünde** çalışıp durable artifact (`data/runtime/tf_calibration.json`) yazıyor. `tf_weight_trainer.py`:
  trust-gated, entry-outcome tabanlı **tf_weights PROPOSAL** (CALIBRATED TF'ler nudge'lanır; negatif-expectancy
  asla up-weight; bucket renormalize; owner-onaylı, asla auto-apply). Tam signal-contribution attribution ertelendi.
- **9 (controlled activation)** — `packages/decision/shadow.py`: yeni pipeline her tick **gözlem modunda** çalışır,
  canlı-vs-shadow karşılaştırması JSONL'e yazılır (`affect_decision:false` → paper'a dokunmaz; trust verdict gömülü).
  `shadow_activation.py`: Faz B `activate()` → girişleri **yalnız manual_ready**'ye yönlendirir (asla auto-open;
  RiskGate owner onayında yeniden çalışır), `affects_paper` ile gated → **shipped config'te inert**.
  `GET /api/v1/decision/shadow` + **ShadowPanel** (browser-doğrulandı, gerçek veri: SHADOW_ONLY_ENTRY divergence).
- **§4.5** — `reversal.py` (RSI/MACD divergence + double bottom/top) + `patterns.py` (HH/HL swing yapısı);
  `build_timeframe_result`'a EVIDENCE-only bağlı (yetersiz veri → None, faking yok; decision/risk tüketmez — guard).
  Contract: openapi `ReversalSignal`/`TechnicalReversalSignals`/`ChartPattern`/`TechnicalChartPatterns` + api.ts.

**Sıradaki:**
1. **Adım 9 aktivasyon (owner kararı, kod değil)** — yeterince gözlemledikten sonra
   `config/thresholds_v1.0.yaml`'da `shadow.affect_decision: true` çevir → activate() devreye girer
   (yalnız manual_ready). "izle → SONRA aktive et" disiplini: önce ShadowPanel'i izle.
2. **Tam per-TF signal-contribution attribution** — tf_weights'i entry-outcome yerine sinyal-katkısından
   ayarlamak için zengin per-TF decision-logging gerekir (kasıtlı ertelendi, faking yok).
3. **Onaylanan tf_weights'i canlı consensus'a uygulama** — strateji-çözümleme kararına bağlı (ertelendi);
   yeni consensus şu an bilinçli strateji-agnostik (eşit ağırlık).

**Son durum:** **700 test geçiyor** · 0 hata · ruff temiz · `tsc --noEmit` temiz · codegen senkron · ShadowPanel **browser-doğrulandı**.
**Windows test komutu:** `python -m pytest -q -p no:cacheprovider --basetemp=".pytest_tmp/basetemp"`
(varsayılan temp `pytest-of-twone` erişim reddediyor → basetemp şart). Web tsc: `node apps/web/node_modules/typescript/bin/tsc --noEmit`.
**Push edildi mi:** ✅ phase-3-dashboard-transplant (bu oturumda push edildi)

---

## Makineler-arası RİTÜEL

### Oturum SONU (hangi makinede çalışıyorsan)
Claude'a şunu de: **"kaydet ve devret"** (handoff). Claude şunları yapar:
1. Biten işi commit'ler (desen: `feat → chore(contract) → test`).
2. Yukarıdaki **ŞU AN NEREDEYİZ** bloğunu günceller + commit'ler.
3. `git push` eder.

### Oturum BAŞI (diğer makinede)
1. `git pull` (veya ilk sefer `git clone` + `git checkout phase-3-dashboard-transplant`).
2. Claude'a şunu de:
   > **kaldığımız yerden devam — `docs/TECHNICAL_ARCHITECTURE_PROGRESS.md` oku, sonra ŞU AN NEREDEYİZ bölümündeki sıradaki adımdan devam et. Spec: `docs/TECHNICAL_ANALYSIS_SPEC.md`. Kurallar: contract-first (openapi→codegen), additive, her adım guard testli, RiskGate tek otorite, üst TF yalnız scale-down, onay olmadan push yok.**
3. Claude bu iki dosyayı okuyup kaldığı adımdan devam eder.

> Not: Her makinede ortam farklı olabilir (node yolu, python). "Kurulum" bölümüne bak.

---

## Tamamlanan adımlar (detay)

> Commit hash'leri referanstır; gerçek tarih için `git log --oneline`.

**Adım 1 — Indicators (T1):** `packages/data/providers/technical/indicators.py`'a
`adx`(+DI), `atr_percent`, `swing_pivots`, `vwap` (intraday-only), `bollinger_width`
eklendi (saf, yetersiz veride None). `fibonacci.py` zaten vardı. Test: `tests/unit/test_indicators.py`.

**Adım 2 — TechnicalTimeframeResult (T1):** modeller `packages/data/types.py`;
builder `packages/data/providers/technical/timeframe.py` (`build_timeframe_result`);
config `technical:` bloğu `config/thresholds_v1.0.yaml`. Ayrı direction/strength
ekseni, key_levels, ADX trend strength, per-TF volatility regime, per-TF confluence,
indicator warm-up quality. Eksik veri = diagnostic. Test: `tests/unit/test_timeframe_result.py`.

**Adım 3 — TechnicalAgent (T2):** `packages/agent/technical_agent.py` (`evaluate` →
`TechnicalAgentOutput`, stance ALLOW/CAUTION/ABSTAIN/DEGRADED, invalidation, missing_data).
Test: `tests/unit/test_technical_agent.py`.
(Adım 1–3 commit'leri: feat `0a8c8d5`, contract `a9c7053`, test `82f073d`; ayrıca dev `e9b4052`.)

**Adım 4 — Consensus cross-TF (T2):** `packages/consensus/timeframe.py`
(`build_consensus` → `ConsensusSnapshot`). Ayrı direction/strength/agreement/alignment
eksenleri, NEUTRAL dilution, alignment_status {ALIGNED,PARTIAL,COUNTERTREND,CONFLICTED},
koşullu countertrend, cross-TF confluence, confirmed/pending/blocking. Mevcut
modül-ağırlıklı `engine.py` (`ConsensusResult`) DOKUNULMADI. Test: `tests/unit/test_consensus_timeframe.py`.
(Commit'ler: feat `483e656`, contract `fc200a9`, test `835115b`.)

**Adım 5 — AgentDecision (T2):** `packages/decision/agent_decision.py` (`decide` →
`AgentDecision`). Aksiyon enum NO_TRADE/WATCH/SCOUT_ALLOWED/CONFIRMATION_REQUIRED/
RISK_REDUCE/KILL_SWITCH + entry_timeframe; RiskGate final + TF-agnostik; üst TF yalnız
scale-down (size_multiplier ≤1.0); 1w giriş üretmez; countertrend asla auto full entry.
Mevcut `decide_matrix` engine DOKUNULMADI. config `decision:` bloğu. Test: `tests/unit/test_agent_decision.py`.
(Commit'ler: feat `b2e9c84`, contract `d1fa018`, test `7ff1fb9`.)

---

## Kalan adımlar (spec §9)

Spec §9 build sırası **1–9 tamamlandı** (+ §4.5). Geriye yalnız kod-dışı / kasıtlı-ertelenmiş kalemler:

- **Adım 9 aktivasyon — owner kararı (kod değil):** ShadowPanel'i yeterince izledikten sonra
  `shadow.affect_decision: true` çevir → `shadow_activation.activate()` devreye girer (yalnız manual_ready).
- **Tam per-TF signal-contribution attribution (ertelendi, faking yok):** tf_weights'i entry-outcome yerine
  sinyal-katkısından ayarlamak zengin per-TF decision-logging ister. Mevcut: trust-gated entry-outcome proposal.
- **Onaylanan tf_weights → canlı consensus:** strateji-çözümleme kararına bağlı (yeni consensus şu an
  bilinçli strateji-agnostik / eşit ağırlık).

---

## Değişmez kurallar (ASLA bozma)
contract-first (openapi → `make codegen`) · additive (mevcut paketleri bozma) ·
closed-candle only · tek aggregate skor yok (direction/strength/agreement ayrı) ·
eksik veri = diagnostic (fake neutral yok) · RiskGate tek nihai otorite · üst TF
yalnız scale-down · teknik modül trade açmaz / size artırmaz · 1w giriş üretmez ·
her adım guard testli · **onay olmadan push yok**.

---

## Kurulum & komutlar

**Çalıştırma (clean-e-yay, eski repo ile çakışmasın diye 4000/8001):**
```bash
# node/pnpm bu Mac'te PATH'te değil; gerekirse: export PATH="$HOME/.local/node/bin:$PATH"
cd <repo>
API_PORT=8001 WEB_PORT=4000 PYTHON=python3 ./scripts/dev.sh
# web → http://localhost:4000 · api → http://127.0.0.1:8001/api/v1/health
```

**Test / lint / codegen:**
```bash
PYTHONPATH="$PWD" python3 -m pytest -q          # tüm paket
python3 -m ruff check packages apps/api apps/tick_worker apps/learning_worker
python3 scripts/codegen.py        # openapi → apps/web/types/generated/schema.ts
python3 scripts/codegen.py --check
```
> Yeni şema eklerken: `contracts/openapi.yaml` + **el-bakımlı** `apps/web/types/generated/api.ts`
> (codegen-drift guard her şema/enum'u burada ister) + `make codegen` (schema.ts).

**Bu Mac'e özel (diğer makinede farklı olabilir):**
- `node` v20 `~/.local/node/bin`'de; `python3` 3.14, backend deps sistemde kurulu.
- `uvicorn --reload` py3.14'te çalışması için homebrew `python@3.14` opt-symlink onarıldı
  (`/usr/local/opt/python@3.14` → Cellar). `dev.sh` ayrıca `API_RELOAD=false` destekler.
