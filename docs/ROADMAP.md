# Roadmap — Clean E-yAy

## Current

- Mock veriyle uçtan uca yeşil.
- CI: `python` + `web` jobs yeşil.
- Dashboard 17 panel ile bağlı (mock data).
- Paper trading mock veriyle çalışıyor (open → tick → SL/TP close → PnL).

## Next

- **G1** — gerçek provider + DQS + snapshot + dashboard visibility
  (bkz. `.tasks/NEXT_TASK.md`)

## Then (sıra ile)

- ~~**G2** — auto-weight trainer~~ ✓
- ~~**G6** — confidence calibration~~ ✓
- ~~**G3** — mistake memory gate~~ ✓
- ~~**G4** — correlation-aware sizing~~ ✓
- ~~**G5** — daily-loss / max-DD halt~~ ✓
- ~~**T0** — timeframe contracts + schema seeding~~ ✓
- ~~**T1** — OHLCV provider + gerçek multi-timeframe technicals~~ ✓
- ~~**T2** — timeframe consensus + decision + paper (time-stop) +
  TimeframeMatrixPanel~~ ✓
- ~~**v2.6** — LLM persona (Groq, narrative-only)~~ ✓
- **OPS** — contract/replay testleri + operasyonel sağlamlaştırma
  (öneri: v2.7'den önce — TS tipleri elle senkron, drift riski)
- **v2.7** — deep data (funding rate, options IV, realized vol, gerçek
  haber feed'i + **T3 catalyst half-life motoru**)
- **operations** — runbook, monitoring, alerting

Bir görev başlamadan önceki görev tamamlanmadan bir sonrakine geçilmez,
aksi NEXT_TASK.md'de açıkça belirtilmedikçe.

---

## Adaptif Kendini-Eğitme Yol Haritası (CP1–CP7)

> Bu bölüm, sistemin **kendini eğiten / adaptif** hâle gelmesi için fazlı plandır.
> Başka bir AI/oturum bu repo'dan devam edebilsin diye **kendine-yeterli** yazılmıştır.
> **Amaç:** yeni veri toplamak değil — zaten biriken ama **atıl** öğrenme/shadow
> verisini **güvenle** karar döngüsüne sokmak. **Execution (gerçek emir) EN SON.**

### Değişmez yasalar (her PR'da kabul kapısı — ASLA çiğneme)
1. **Additive** — imza değiştirme; mevcut testler yeşil kalır (`pytest tests/unit`).
2. **Flag-default-OFF = bayt-aynı** — yeni davranış `*.enabled` arkasında, kapalıyken
   çıktı birebir bugünkü. Monkeypatch-seam deseni: `engine._ev_gate_cfg`,
   `_self_conflict_cfg` (config'i fonksiyondan oku ki test override edebilsin).
3. **Shadow-önce** — hep hesapla, sadece açıkken uygula; shadow değeri logla.
4. **Rollback'li** — açılan her şey otomatik (expectancy düşerse) veya tek-flag ile geri alınır.
5. **Off-tick + örnek-kapılı** — ağır iş `apps/learning_worker`'da / on-demand; `tick_worker`
   sıcak yoluna SIFIR ek yük. Tetik `tf_target`'taki "≥N yeni outcome" deseni.
   `LEARNING_BUDGET_MS` perf bütçesi (CP1) ağırlaşmayı izler.
6. **Ölü kod yok** — her modül aynı PR'da panel/endpoint/trainer ile **tüketilir**.
7. **Mimari/bakım** — `apps/api` ince HTTP (mantık `packages/`'ta); runtime'da mock yok;
   mevcut store/desen yeniden kullan; küçük tek-sorumluluklu modül + test + docstring.

**Kırmızı çizgi:** yön motorunu (consensus→aday→yön) **CP2(kanıt)+CP3(rollback) OLMADAN**
öğrenmeye/oto-ayara açma. Öğrenme otomasyonu bugün yalnız ağırlık/kalibrasyon/target/
mistake'i ayarlar — yön mantığını DEĞİL (bkz. ARCHITECTURE.md güvenlik notu).

### Fazlar + durum
- **CP1 — Veri omurgası + perf bütçesi ✅ DONE (PR #24).**
  `packages/learning/dataset_health.py` (kapsama + öğrenici-hazırlık) + `GET /api/v1/learning/dataset-health`
  + `learning_worker` perf bütçesi (`LEARNING_BUDGET_MS`, run meta `duration_ms`/`over_budget`)
  + `DatasetHealthPanel` (Conscious "Öğrenme Özeti"). Observe-only.
- **CP2 — Edge kanıt/stabilite katmanı ✅ DONE (PR #25).**
  `packages/learning/edge_report.py` (çok-katlı walk-forward stabilite + missed_opp
  counterfactual + verdict STABLE/UNSTABLE/INSUFFICIENT + `safe_to_autotune`)
  + `GET /api/v1/learning/edge-report` + `EdgeReportPanel`. Observe-only.
- **CP3 — Yön güvenlik kasası ✅ DONE (slice 1).**
  `weight_rollback` deseni guard-agnostik kasaya genellendi: `packages/learning/guard_safety.py`
  (owner bir guard'ı OFF→ON aldığında izlemeye alır → eşleştirilmiş baseline; yeterli yeni
  outcome'da post-enable expectancy < baseline ise **oto-kapat**) + `guard_monitor_store.py`
  (guard başına izleme/geçmiş ledger'i) + `packages/data/registry/guard_overrides.py`
  (runtime kill-switch; engine seam'leri `_self_conflict_cfg`/`timeframe.load_config` OFF'a
  zorlar, override yokken bayt-aynı, mtime-cache'li → sıcak yol sıfır yük). Bağlı guard'lar:
  `chop`/`exhaustion`/`reversion`/`self_conflict`. `weight_rollback.post_open_expectancy`
  public yapıldı (eşleştirilmiş-pencere mantığı tek yerde). Worker `run()` çağırır
  (off-tick) + `GET /api/v1/learning/guard-safety` + `GuardSafetyPanel` (Conscious).
  Oto-kapat default AÇIK; `GUARD_AUTO_DISABLE=0` → yalnız öneri (ROLLBACK_RECOMMENDED).
  **Owner-niyeti farkı:** ağırlık rollback'i no-evidence'ta geri alırdı; kasa kanıtsız süre
  dolunca INCONCLUSIVE kapanır, guard CANLI kalır (guard enable = owner kararı). **CP4/CP5'in
  ön-koşulu artık hazır.** Not: önceden-canlı guard'lar geriye dönük izlenmez (yalnız gelecek
  geçişler); mevcut canlı `self_conflict`'i kasaya almak için owner OFF→ON toggle eder.
- **CP4 — Adaptif öz-ayar.**
  - **Slice 1 ✅ DONE — giriş/çıkış kalitesi öğrenicisi (observe-only).**
    `packages/learning/entry_exit_quality.py`: biriken verified outcome'ların MAE/MFE
    excursion'ından, **dominant_module × timeframe** kovaları bazında üç ders çıkarır:
    EXIT_EARLY (yakalama=pnl_pct/mfe_pct düşük + bırakılan kâr yüksek → trailing sıkı),
    STOP_TOO_TIGHT (SL_HIT oranı yüksek + stop adverse < kazanan MFE → gürültü stop'u),
    ENTER_EARLY (kazananlar lehe dönmeden önce MFE'lerinin büyük kısmı kadar aleyhte
    dalıyor). Her ders bir `nudge` ipucu taşır (slice 2 için: trailing/sl_atr/entry_timing).
    `GET /api/v1/learning/entry-exit-quality` + `EntryExitQualityPanel` (Conscious grup 03).
    On-demand (worker'a yük yok), karar zincirine SIFIR dokunuş. **Neden gerekliydi:**
    `tf_target_trainer` SL/TP'yi yalnız **TF** bazında öğrenir; "hangi MODÜLÜN çıkışı/girişi/
    stop'u bozuk" granülerliği yoktu. İlk canlı bulgu: **touche × 4h/1h asıl sorun dar stop
    DEĞİL, EXIT_EARLY** (hareketin ~%28'i yakalanıyor, işlem başı ~%2.5 kâr masada).
  - **Slice 2 ✅ DONE — otonom geometri uygulama: edge-gate + rollback net.**
    Mevcut `tf_target_trainer`/`tf_target_store` geometriyi (SL×ATR, rr) ±%15 bantta zaten
    otonom uyguluyordu AMA **gate'siz + rollback'siz** (kırmızı çizgi ihlali). Slice 2 bunu
    güvenli-otonom yaptı: (1) **edge-gate** — `tf_target_store.submit_proposal(auto_apply_
    allowed=)`; worker `TF_TARGET_EDGE_GATE` flag açıkken `edge_report.safe_to_autotune`
    STABLE değilse band-içi nudge bile `gated_pending` olur (auto-apply YOK). (2) **outcome-
    rollback** — `tf_target_rollback.py` (ağırlık G3 ikizi; `weight_rollback.{pre_apply,
    post_open}_expectancy` REUSE): auto-apply izlenir, post-apply expectancy baseline'ın
    altına düşerse `tf_target_store.revert_overrides()` ile geometri önceki değerine döner.
    `submit_proposal` artık `applied_changes` (prev snapshot) taşır. `/learning/tf-targets`
    endpoint'i + `TfTargetsPanel`'de `edge_gate` bloğu (durum + izleme + son rollback).
    **Flag default OFF = bayt-aynı** (gate'siz eski davranış). Owner `TF_TARGET_EDGE_GATE=1`
    ile güvenli-otonom modu açar. Tek-değişiklik-tek-doğrulama (aynı anda 1 aktif izleme).
  - **Slice 3 ✅ DONE — touche erken-çıkış (trailing) düzeltmesi.** Bulgu: trailing açılışta
    konviksiyon **tier**'ından geliyordu (`tier.trail_distance`, global; per-TF/modül değil).
    Global gevşetmek yanlış olurdu (touche 15m %100 yakalıyor). Çözüm: trailing'i **TF-aware**
    yaptık — tf_targets yüzeyine yeni param **`trail_mult`** eklendi (GUARDRAIL [0.5,2.0]).
    Açılış (`lifecycle._open`): `trail_distance = tier.trail_distance × te.tf_trail_mult(tf)`.
    `tf_trail_mult` flag `TF_TARGET_TRAIL_AUTOTUNE` OFF iken **1.0 → bayt-aynı**. Trainer
    Rule 4: bir TF'de trailing-çıkış oranı yüksek + yakalama (realize/MFE) düşükse
    `trail_mult ↑` önerir (TfStats'a `trailing_rate`/`avg_capture` eklendi). trail_mult,
    slice 2'nin store+edge-gate+rollback'inden GEÇER (otomatik güvenli). `/learning/tf-targets`
    `trail_autotune` bloğu + `TfTargetsPanel`. **NOT:** uygulama TF-aware (modül değil); touche
    4h/1h'i hedefler çünkü touche o TF'lerde baskın. Owner `TF_TARGET_TRAIL_AUTOTUNE=1` +
    `TF_TARGET_EDGE_GATE=1` ile güvenli-otonom trailing'i açar.
  - **Slice 4 ✅ DONE — config-injection seam + A/B backtest (deferred prereq).**
    `load_thresholds` `@lru_cache`'i A/B'yi engelliyordu (CP2'de ertelenmişti). Çözüm:
    `loader.py` cache'li `_load_thresholds_base()` + `threshold_override()` contextmanager
    (contextvar, deep-merge). `load_thresholds` override yokken base'i **BİREBİR (zero-copy)**
    döner → sıcak yol (decision engine ~11 çağrı) bayt-aynı. Tüketici: `threshold_ab.sweep()`
    — bir eşiğin farklı değerlerini MEVCUT `run_signal_backtest` ile geçmiş barlarda dener,
    win_rate/avg_return/PF karşılaştırır + baseline'dan iyiyse öneri. `GET /learning/threshold-ab`.
    Observe-only (override yalnız backtest scope'unda; canlı config değişmez). Bu = CP4'ün
    "trainer öner → **backtest doğrula**" adımının altyapısı.
  - **Slice 5 ✅ DONE — otonom eşik trainer (CP4 KAPANDI).** Tüm CP4 parçalarını birleştirir:
    `threshold_trainer.train()` (off-tick) → allowlist eşiği (ilk: `paper_trading.tp_rr_ratio`,
    skaler + backtest-ölçülebilir) için ±%10 aday üret → `threshold_ab.sweep` ile backtest-
    doğrula → baseline'ı MIN_IMPROVEMENT geçerse VE `edge_report.safe_to_autotune` STABLE ise
    → `threshold_overrides` (file-backed, mtime-cache) ile CANLIYA uygula → `check_rollback()`
    outcome-rollback (post-apply expectancy düşerse `threshold_overrides.revert`). `load_thresholds`
    runtime override'ı **yalnız `THRESHOLD_AUTOTUNE` açıkken** merge eder → flag OFF = bayt-aynı
    (dosya bile okunmaz). `GET /learning/threshold-autotune`. weight_rollback expectancy REUSE;
    tek-değişiklik-tek-doğrulama. **NOT:** allowlist şimdilik yalnız run_signal_backtest'in
    ÖLÇTÜĞÜ skaler eşik(ler); consensus/regime eşikleri için o eşikleri exercise eden bir
    backtest gerekir (sonraki iş — CP4 harness'ı hazır, genişletme allowlist + backtest meselesi).
    Owner `THRESHOLD_AUTOTUNE=1` ile açar.
  - **Deadlock bilgisi (devam eden AI bilsin):** otonom ağırlık akışı "tek-değişiklik-tek-
    doğrulama" diskiplininde; bir auto-apply, `REBALANCE_ROLLBACK_MIN_OUTCOMES` (default 15)
    yeni post-apply outcome birikene kadar MONITORING'de kalır ve TÜM yeni önerileri PENDING→
    `REJECTED(superseded)`'e iter. Düşük işlem hacminde bu "15 red" görüntüsü **owner veto'su
    DEĞİL**, sadece kuyruk churn'ü. Akışı hızlandırmak için eşiği düşür (env: 15→8) — kod değil.
- **CP5 — Keşif + motor birleşmesi.** `discovery.py` (sınırlı hipotez üret→backtest→CP4 terfi);
  shadow zekâyı (market_regime/trend_strength/setup_classifier/conflict_resolver/agent_pipeline)
  **tek tek** flag'li yön otoritesine terfi (= eski F6, güvenle).
- **CP6 — Online adaptasyon (opsiyonel).** Batch arası küçük bounded nudge, rollback'li, off-tick.
- **CP7 — Execution EN SON (kilitli).** Yalnız CP2–CP6 kanıtlanınca + owner + küçük pilot.

**Sıra:** CP1→CP2→CP3→CP4→CP5→CP6. CP4/CP5, CP2+CP3 olmadan başlamaz. Her CP = 1–3 küçük dikey slice (PR).

### Kritik bulgular (devam eden AI bunları varsaymasın, bilsin)
- **Backtest motoru ZATEN VAR:** `packages/data/strategy_backtest.py` canlı `build_timeframe_result`'ı
  geçmiş barlarda SL/TP'li çalıştırır; `packages/data/backtest.py` R2 rolling. Endpoint'ler:
  `/replay/backtest`, `/replay/strategy-backtest[/all]`. **Yeni motor yazma — bunları kullan.**
- **Veri yeterli** (CP1 canlı): ~81 eğitilebilir outcome, öğreniciler HAZIR → darboğaz toplama değil **tüketim**.
- **Edge UNSTABLE** (CP2 canlı): 2/4 dilim pozitif → `safe_to_autotune=False`. Oto-ayar (CP4) bu
  kapıdan geçmeli; bugün açmak yanlış olurdu.

### Yeni öğrenme paneli/endpoint eklerken izlenecek desen (bakım kolaylığı)
1. `packages/learning/<modül>.py` (saf fonksiyon, mevcut `outcomes`/`missed_opportunity`/store reuse).
2. `apps/api/routers/learning.py`: import (isort sırası) + `@router.get("/learning/<x>")`.
3. Frontend: `apps/web/types/generated/api.ts` (tip — ELLE bakımlı), `lib/api/client.ts`,
   `lib/queries/keys.ts`, `lib/queries/hooks.ts`, `components/panels/<X>Panel/index.tsx`,
   `components/cockpit/CockpitView.tsx` (Conscious grubuna bağla).
4. `tests/unit/test_<modül>.py`. Windows: `pytest --basetemp=<yazılabilir dizin>` (kilitli Temp workaround).
5. FE değişince stabil sunucu için `.next-prod` rebuild (`NEXT_DIST_DIR=.next-prod next build`)
   → `scripts/start-dashboard.ps1` (next start). Dev/önizleme `next dev` (ayrı `.next`).
