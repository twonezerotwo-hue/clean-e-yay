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
- **CP4 — Adaptif öz-ayar.** Kural-sabit eşikleri (rejim ADX/vol, consensus eşiği, guard
  eşikleri, tf_weights) trainer öner → CP2/backtest doğrula → CP3 harness'la **dar-bant oto**
  (G3 deseni; `rebalance_store`/`tf_target_store` reuse). **NOT:** A/B parametre-backtest için
  `load_thresholds` (`@lru_cache`) üstüne **temiz config-injection seam** gerekir (CP2'de
  bilinçli ertelendi — invazif olmasın diye). `edge_report.safe_to_autotune` False iken oto-uygulama YOK.
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
