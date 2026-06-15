# Technical Architecture — İlerleme & Makineler-Arası Devir (HANDOFF)

> **Bu dosya "kaldığımız yer"in TEK doğruluk kaynağıdır.** Claude'un yerel hafızası
> (`~/.claude`) makineler/hesaplar arasında TAŞINMAZ — bu yüzden durum repoya yazılır.
> İki bilgisayar arasında (token bitince diğerine geçerek) kesintisiz devam etmek için
> aşağıdaki ritüeli izle. Spec/build incili: [`TECHNICAL_ANALYSIS_SPEC.md`](TECHNICAL_ANALYSIS_SPEC.md).

- **Repo:** `clean-e-yay` · **Branch:** `phase-3-dashboard-transplant`
- **Remote:** https://github.com/twonezerotwo-hue/clean-e-yay

---

## 🔖 ŞU AN NEREDEYİZ  (her oturum sonu burayı güncelle)

**Tamamlanan:** Spec adım **1–6 (tam)** + **7 (backend + contract + frontend)** + **8 (kalibrasyon temeli)**.
- **6** — `packages/risk/trade_economics.py`: cost + R:R kapısı (RiskGate-side, yalnız kısıtlayıcı;
  `trade_economics` config bloğu). Guard'lar: `test_bad_rr_blocks_entry`, `test_scalp_below_cost_blocked`.
- **7 (backend+contract)** — `packages/decision/agent_pipeline.py` composer (adım 1–6'yı birleştirir;
  economics FINAL overlay) + `GET /api/v1/technical/agent-matrix` (`apps/api/routers/technical.py`) +
  contract: openapi `AgentMatrix`/`AgentMatrixRow`/`TradeEconomics`, `schema.ts` (üretildi), `api.ts` (el).
- **7 (frontend)** — `AgentMatrixPanel` (`apps/web/components/panels/AgentMatrixPanel`) `/technical/agent-matrix`'e
  bağlı: `api.agentMatrix` + `useAgentMatrix` hook + `lib/selectors/agent-matrix.ts` + panel-registry (decision grubu) +
  `app/page.tsx` mount. Frontend hesap yapmaz; selector ViewModel'i map eder. Browser-doğrulandı (:4000 → :8001:
  KILL_SWITCH banner + ETHUSD COUNTERTREND/CT). `tsc --noEmit` temiz (latent duplicate `Timeframe` api.ts fix).
- **8 (temel)** — `packages/learning/tf_calibration.py`: verified outcome → per-TF hit-rate/expectancy +
  tf_weights **trust-gate** (kalibrasyon doğrulayana kadar PRIOR) + `tf_weights` PRIOR (`weights_v1.0.yaml`).
- **Tooling** — codegen artık **her OS'ta** çalışıyor (`node cli.js` + satır-sonu duyarsız karşılaştırma);
  riskgate guard'ları OS-portable (`as_posix`). **Makine ayrımı YOK.**

**Sıradaki:**
1. **Adım 9** — controlled activation: `shadow_mode` → `affect_decision: false` (izle) → sonra `true`,
   `manual_ready_only`. Yeni agent pipeline'ı (agent-matrix) gözlem moduna al; kararı henüz paper'a yazma.
2. **Adım 8 tam tf_weights auto-tune** — per-TF sinyal-katkısı attribution'ı için zengin decision-logging
   gerekir (kasıtlı ertelendi, faking yok). Not: `auto_weight_trainer` önerileri tf_weights'i taşımıyor.
3. **Reversal_signals + chart_pattern_analysis** stateful katmanları (kasıtlı ertelendi, faking yok).

**Son durum:** **644 test geçiyor** · 0 hata · ruff temiz · `tsc --noEmit` temiz · codegen senkron (Windows **ve** Mac) · agent matrix paneli **browser-doğrulandı**.
**Windows test komutu:** `python -m pytest -q -p no:cacheprovider --basetemp=".pytest_tmp/basetemp"`
(varsayılan temp `pytest-of-twone` erişim reddediyor → basetemp şart).
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

- **6 (T2) — risk genişlet:** cost (taker/spread/slippage) + net edge + R:R kapısı +
  tf cap. RiskGate final. Test: `test_bad_rr_blocks_entry`, `test_scalp_below_cost_blocked`.
- **7 — wiring + dashboard:** TechnicalTimeframeResult/TechnicalAgentOutput/
  ConsensusSnapshot/AgentDecision'ı bir API endpoint'e + `TimeframeMatrixPanel`'e bağla.
- **8 — learning:** replay → outcomes → calibration → tf_weights auto-tune.
- **9 — controlled activation:** shadow_mode → affect_decision false→izle→true.
- **Ertelenen (kasıtlı, faking yok):** reversal_signals + chart_pattern_analysis stateful katmanları.

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
