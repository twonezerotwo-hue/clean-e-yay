# Denetim Yol Haritası — Kodlama Süreci

> 2026-07-02 tam-repo denetiminin bulgularını sıralı, güvenli bir kodlama
> sürecine çevirir. **Yaşayan belge** — her slice tamamlanınca durum sütunu
> güncellenir. Kaynak denetim raporu: PR #48 açıklaması + oturum kaydı.

## Devir notu (son güncelleme: 2026-07-02)

Bu belge farklı bir asistan/oturum tarafından SIFIR bağlamla devralınabilir
şekilde yazılmıştır. Mevcut durum:

- **Branch:** `main` (PR #48 merge edildi). Main'e merge = AWS'e otomatik
  deploy (systemd worker restart dahil). Lokal keep-alive watchdog
  worker'ları lokal koddan çalıştırır.
- **Tamamlanan:** KODLAMA BİTTİ — F0, F1, F2, F3 (F3-1 owner iptali), F4,
  F5, M serisi ve R2-3'ün TAMAMI main'de (PR kuyruğu #49–#53 owner
  talimatıyla 2026-07-02 merge edildi; birleşik main'de tam suite
  1291/1291 yeşil, ruff'ta yeni hata yok — tests/ altında 45 eski baseline
  bulgusu var, dokunulmadı; AWS deploy yeşil). F2-1 gate-bağlama owner
  kararı bekliyor.
- **Sıradaki iş — AKTİVASYON FAZI:** Yeni kod yazılmıyor; aşağıdaki
  bekleyen flag'ler kanıt eşliğinde TEK TEK açılır (sıra ve yöntem owner'la
  planlanır). F5-3 aktivasyon watchdog'u canlıda: her OFF→ON geçişini
  otomatik izler, bozulmada DEGRADED önerir (oto-kapatmaz).
- **AÇILDI — Paket 1 girdi-düzeltmeleri (2026-07-02, owner kararı):**
  `news.sentiment_v2`, `regime.drop_unavailable_layers`,
  `consensus.fundamental_v2`, `sentinel_v2.enabled`,
  `risk_gates.correlation_price_returns` — beşi birlikte açıldı (her biri
  kendi v1/v2 yan-yana gözlem kaydını tutmaya devam eder; aktivasyon
  watchdog'u beşini birden izler). Owner talimatı: v1 kod yolları
  PARAŞÜT olarak YERİNDE kalır — silme, doğrulama penceresi sonrası ayrı
  owner onayı. Test suite'i canlı default'lardan bağımsızlaştırıldı
  (conftest `_package1_flags_off_by_default`: unit testler v1 baseline'ı
  pinler, v2 testleri threshold_override ile açar — sonraki aktivasyonlar
  test kırmaz).
- **Paket 2 — öğrenme, TEK TEK sırayla (bekleme penceresiyle):**
  (1) `calibration.tf_platt` — **AÇILDI (2026-07-02, owner kararı;
  F4-1). Bekleme penceresi açık — kanıt: GET /learning/calibration
  `per_timeframe` + activation-watchdog. Sıradaki (2) bu pencere temizse.**
  Sıradaki bekleyenler: (2) `empirical_pwin.enabled`
  (F4-2 — kanıt: 15m ampirik EV negatif); (3) `WEIGHT_REGIME_FILTER` env
  (F3-2 — rejim başına INSUFFICIENT/proposal dağılımı); (4)
  `MISTAKE_MEMORY_V2` env (F3-3 — `[L1]/[L2]` fallback + WARNING/AVOID
  oranı); (5) `EXPECTANCY_R_MODE` (R-damgalı outcome birikince).
- **T serisi — teknik analiz genişletmesi (owner onayı 2026-07-02, kodlama
  TAMAM, 4 flag DEFAULT OFF + shadow gözlemde):** T-1 üst-TF hiza filtresi
  (`technical.htf_alignment`), T-2 Elliott×Fib confluence
  (`technical.elliott_confluence`), T-3 S/R gücü (`technical.sr_strength`),
  T-4 kilit seviyede mum teyidi (`technical.candle_confirm`). Dördü de
  activation watchdog kayıtlı; aktivasyon shadow kanıtı birikince ayrı
  tarihli owner kararlarıyla (öneri sırası: T-1 önce — 15m negatif-EV
  kanıtıyla en doğrudan bağlantılı).
- **Bekleyen owner aktivasyonları (Paket 3 — davranış, kanıt şartlı):**
  (6) `partial_tp.enabled` (F4-3, 🔴 — GET /learning/partial-tp-shadow
  uplift kanıtı birikmeden AÇILMAZ); (7) `empirical_pwin.
  blend_counterfactual` (F5-1 — Paket 2/(2)'den SONRA anlamlı;
  /learning/missed-opportunities `by_timeframe` gözlemi); (8) F2-1
  gate-bağlama (`paper_state_summary.mtm_equity_usd` bandı izlenip
  RiskInput'a flag'le bağlanır — ayrı owner kararı).
- **Bekleyen owner kararları:** `EXPECTANCY_R_MODE` (R-bazlı expectancy)
  default KAPALI — R-damgalı outcome birikince açılacak (open_risk_pct
  yalnız YENİ kapanışlarda damgalanıyor; eski kayıtlarda yok).
- **Test komutu:** `.venv/Scripts/python -m pytest --basetemp=.pytest_tmp/run_X -q`
  (basetemp şart — Windows Temp kilit sorunu). Ruff: `.venv/Scripts/python -m ruff check packages apps tests`.
- **Kurallar:** commit/push'tan önce owner'a sor; işler ayrı commit'lerle
  gider; aşağıdaki Anayasa her slice için bağlayıcıdır.

## Anayasa (her slice için geçerli — pazarlıksız)

1. **Çalışan sistem ASLA bozulmaz** — davranış değiştiren her şey ya
   owner-flag (default KAPALI) ya measurement-only (gözlem) olarak girer.
   Aktivasyon ayrı, tarihli owner kararıdır (config yorumuna yazılır).
2. **Ölü kod yok** — eklenen her alan/fonksiyon aynı PR'da gerçekten
   okunur/kullanılır. "İleride lazım olur" diye alan eklenmez.
3. **Mimari bozulmaz** — RiskGate son otorite, no-AI-boost (öğrenme yalnız
   küçültür/bloklar), additive-only, DATA_POLICY (uydurma veri yok),
   shadow-önce, her aktivasyona outcome-rollback.
4. **Her slice bağımsız geri alınabilir** — tek flag / tek revert ile.
5. **Test:** tam suite yeşil (bilinen istisna: `test_rotation` yuvarlama,
   bkz. R2-3) + slice'a özgü yeni testler. Ruff'ta yeni hata yok.

## Durum Tablosu

Durum: ✅ tamam · 🔶 kısmen · ⬜ yapılmadı
Risk: 🟢 davranış değiştirmez (ölçüm/altyapı) · 🟡 flag'li davranış değişimi · 🔴 karar zincirini değiştirir (shadow şart)

| # | İş | Denetim ref | Durum | Risk | Faz |
|---|---|---|---|---|---|
| F0-1 | Kalibrasyon fit'i ham güvene (`raw_confidence`) çevir | 1.1 | ✅ PR #48 | 🟢 | F0 |
| F0-2 | News modülü sembol-ilişkili (`news_symbol_filter`) | 2, 3.2 | ✅ PR #48 | 🟡 açık | F0 |
| F1-1 | R-multiple standardı: `CanonicalOutcome.r_multiple` + expectancy'lerin R tabanına geçişi | 3.4, 1.6d | ✅ (flag `EXPECTANCY_R_MODE` default OFF — aktivasyon owner kararı, R-damgalı outcome birikince) | 🟢→🟡 | F1 |
| F1-2 | `bucketize`/mistake-memory'de pnl==0 başabaş ayrımı (loss sayılmasın) | 1.6c | ✅ | 🟢 | F1 |
| F1-3 | decision_log'a modül katkı vektörü (score×weight) yaz + edge/attribution raporunda oku | 4.2 | ✅ (learning summary `module_attribution`) | 🟢 | F1 |
| F1-4 | Gün çapası UTC fix (`date.today()` → UTC) | 1.6a | ✅ | 🟢 | F1 |
| F1-5 | Kısmi kapanışta trade id benzersizliği (leg suffix) + dedupe düzeltmesi | 1.6b | ✅ | 🟢 | F1 |
| F2-1 | Mark-to-market equity → RiskInput (önce gözlem alanı, sonra flag'li gate girdisi) | 1.3, 3.5 | 🔶 gözlem fazı tamam (2026-07-02): `PaperState.unrealized_pnl_usd`/`mtm_equity_usd` türetilmiş; snapshot `paper_state_summary` + tick heartbeat + system/health taşır. Gate girdisine bağlama = bant gözlemi sonrası ayrı owner kararı (flag ile) | 🔴 | F2 |
| F2-2 | Korelasyonu fiyat getirisinden hesapla (OHLCV cache; kaynak önceliği computed_price > baseline > neutral) | 1.5, 3.7 | ✅ (2026-07-02) `price_return_series` + `computed_price` kaynağı: 1d OHLCV disk cache'inden günlük getiri Pearson'ı (ağ çağrısı YOK, yalnız verified barlar). Flag `risk_gates.correlation_price_returns` DEFAULT OFF (aktif zincir bayt-aynı); fiyat-rho her girdide `rho_price`/`price_samples` SALT-GÖZLEM (API /risk/correlation matrisi + `price_returns_enabled`). Aktiflik eşiği `correlation_price_min_overlap_days` (20). Canlı kanıt: aktif zincirde 45 çiftin 43'ü neutral (risk motoru kör) iken fiyat-rho 38 çifti dolduruyor; iki baseline da gerçeği KÜÇÜMSÜYOR (BTC\|ETH 0.75→0.882, XAG\|XAU 0.80→0.868 — cluster riski olduğundan az görünüyor). AKTİVASYON BEKLİYOR | 🟡 | F2 |
| F2-3 | Regime layer'ları veri yokken düşür+redistribute (quantum deseni; default-sabit sahte skor yok) | 2 (classifier) | ✅ (2026-07-02) flag `regime.drop_unavailable_layers` DEFAULT OFF (eski davranış bayt-aynı). Açıkken: veri olmayan katman düşer (`RegimeOutput.dropped` → regime-report `dropped_layers`), fundamental/sentinel katmansız kalırsa consensus modülü de düşer+redistribute. Canlı kanıt (FRED'siz ortam): OFF Likidite=96.6 sahte → ON katman düştü, konsensüs 51.2→47.0 (~4.2p sahte şişme). AKTİVASYON BEKLİYOR (owner: `true` + tarihli yorum) | 🟡 | F2 |
| F3-1 | Wilson/bootstrap CI + üç-durumlu rollback kararı (geri al / onayla / izlemeye devam) | 1.6d, 4.1 | ❌ YAPILMAYACAK (owner kararı 2026-07-02: "aceleci karar freni olmasın"). Güvenlik ağı mevcut mekanizmalarda kalır: trainer minimum-örnek eşikleri (MIN_TOTAL_TRADES/MIN_TRADES_PER_MODULE), dar auto-apply bandı, G3 outcome-rollback. Wilson istatistiği F3-3 kapsamında mistake memory'ye YİNE girdi (o ayrı iş) | 🟡 | F3 |
| F3-2 | Ağırlık trainer'ına rejim filtresi + 4 rejimin ayrı eğitimi | 1.2 | ✅ (2026-07-02) flag `WEIGHT_REGIME_FILTER` (env, DEFAULT OFF = bayt-aynı: tüm rejimler tek torbada, yalnız NEUTRAL eğitilir). AÇIKKEN: dataset hedef rejimin KENDİ outcome'larına daralır; worker hedefi = en son kapanan verified outcome'un rejimi (verisi değişen rejim — saat değil veri sürer, deterministik); bilinmeyen rejim etiketi NEUTRAL'a düşer (weights'e sahte satır yok); MIN_TOTAL_TRADES/MIN_TRADES_PER_MODULE rejim başına doğal fren. INSUFFICIENT çıktıları + proposal audit'i rejim etiketli. AKTİVASYON BEKLİYOR | 🟡 | F3 |
| F3-3 | Mistake memory: decision_log kaynağı + hiyerarşik fingerprint fallback + Wilson alt sınırı | 1.4, 4.4 | ✅ (2026-07-02) flag `MISTAKE_MEMORY_V2` (env, DEFAULT OFF = bayt-aynı: recent_trades + exact-match + nokta tahmini). AÇIKKEN: (1) kalıcı kaynak `outcomes_from_state` (decision_log dahil — trainer deseni); (2) hiyerarşik fallback: exact imza yetersizse `~L1\|sym\|tf\|rejim\|yön` → `~L2\|sym\|yön` kovası (sentetik kayıtlar gerçek imzayla çakışamaz, verdict reason `[L1]/[L2]` etiketli); (3) AVOID yalnız Wilson ÜST sınır < eşik, BOOST yalnız ALT sınır > eşikse (1W/2L artık AVOID değil WARNING — aceleci blok yok; streak kuralı aynen). AKTİVASYON BEKLİYOR | 🟡 | F3 |
| F4-1 | TF-bazlı Platt kalibrasyonu (tf_calibration altyapısı üstüne) | 3.1 | ✅ (2026-07-02) flag `calibration.tf_platt` DEFAULT OFF (global fit bayt-aynı). Trainer her koşuda TF başına fit yazar (`platt.json per_timeframe`, additive; MIN_SAMPLES altı TF → insufficient+identity, sahte fit yok); karar anında `predict_calibrated_tf` (OFF → global birebir; ON → TF fit'i, kaynak "fitted_tf", yoksa global fallback). Şişme guardrail'i fitted_tf'e de uygulanır ("fitted_tf_capped"); calibration_audit sayımları iki kaynağı da görür. Gözlem: GET /learning/calibration `per_timeframe`+`tf_platt_enabled` + worker log `tf_fitted`. Canlı kanıt (108 verified outcome): 4 TF'in 4'ü fit; raw 0.10 → global 0.39 ama 15m 0.29 / 4h 0.49 — global fit 15m'de aşırı iyimser. **AKTİF (2026-07-02, owner kararı — Paket 2 / (1)): `calibration.tf_platt: true`.** Aktivasyon anı kanıtı (130 verified outcome): 4 TF'in 4'ü fit (15m=55, 1h=31, 4h=31, 1d=13 örnek), a-katsayıları global'den ayrık (15m=0.44 / 1h=0.33 / 4h=0.26 / 1d=0.11 vs global 0.32). v1 global-fit paraşüt yerinde; conftest OFF-pin eklendi. Bekleme penceresi açık: owner GET /learning/calibration + activation-watchdog izler | 🟡 | F4 |
| F4-2 | EV/Kelly p(win)'ini ampirik TF+rejim hit-rate'ine bağla | 3.3 | ✅ (2026-07-02) `packages/learning/empirical_pwin.py`: learning worker her cycle verified outcome'lardan (tf\|rejim)+tf hit-rate tablosunu yazar (`data/runtime/empirical_pwin.json`; başabaş paydaya girmez/F1-2; min_samples=20 altı hücre lookup'ta DÖNMEZ). Karar motoru mtime-cache ile okur; flag `empirical_pwin.enabled` DEFAULT OFF → EV+Kelly cal_conf ile (bayt-aynı), ampirik değerler her hücrede SALT-GÖZLEM (`p_win_empirical`/`expected_value_empirical`). AÇIKKEN: yeterli hücrede EV+Kelly gerçekleşmiş isabetle; kanıt yoksa cal_conf fallback. Canlı kanıt: 15m\|NEUTRAL p=0.425 → EV −0.04R (NEGATİF — maliyet sonrası kaybettiriyor), 4h\|NEUTRAL p=0.548 → +0.55R; aktivasyon 15m'i bloklar, 4h'ı doğru boyutlar. Yan kazanım: conftest artık canlı platt.json/empirical tabloyu suite'ten izole ediyor. AKTİVASYON BEKLİYOR | 🟡 | F4 |
| F4-3 | Partial-TP + breakeven stop (1R'de %50 kapat; önce shadow yan-yana ölçüm) | 3.6 | ✅ (2026-07-02, PR #49 merge): flag `partial_tp` DEFAULT OFF (davranış bayt-aynı). SHADOW her pozisyonda flag'siz işler: kâr ilk kez trigger_r×\|entry−SL\|'e değince damgalanır (tick-fiyat bazlı, gap'te uydurma yok), r-hit sonrası girişe dönüş breakeven senaryosu olarak işaretlenir, TAM kapanışta hipotetik strateji PnL'i `Trade.ptp_shadow_pnl_usd`. AÇIKKEN: tetikte close_fraction kısmi kapanış (PARTIAL_TP_EXIT, F1-5 leg id) + breakeven SL (yalnız sıkılaştırır); tam çıkışlar (SL/TP/trailing/time-stop) her zaman öncelikli. Gözlem: GET /learning/partial-tp-shadow (actual vs shadow + uplift). Ölü `paper_trading.partial_tp1_pct` kaldırıldı (bu bölüm yerini aldı). AKTİVASYON: önce shadow penceresi (🔴), owner uplift kanıtıyla açar | 🔴 | F4 |
| F5-1 | Counterfactual (missed_opportunity) verisini kalibrasyon/eşik kanıtına bağla | 4.3 | ✅ (2026-07-02, PR #51 merge): missed-opp çözümleri (`resolutions()`) ampirik p(win) tablosuna AYRI kanalda girer (`cf_by_tf`: win=missed_win, loss=avoided_loss, expired paydasız — gerçek ölçüm hücreleri KİRLENMEZ). Flag `empirical_pwin.blend_counterfactual` DEFAULT OFF (bayt-aynı); AÇIKKEN yalnız gerçek kanıtı yetersiz TF'lerde son-çare harman (kaynak "tf_blend_cf") — gerekçe: bloklanan TF gerçek outcome üretmez (geri-besleme kör noktası), counterfactual ölçmeye devam eder. Kanıt yüzeyi: /learning/missed-opportunities `by_timeframe` (cf_win_rate + n). AKTİVASYON BEKLİYOR | 🟡 | F5 |
| F5-2 | Champion/challenger terfi kriteri formalize (N eşleşmiş karar + CI ayrık → owner paketi) | 4.5 | ✅ (2026-07-02, PR #52 merge): `packages/learning/promotion_criteria.py` — 3 kriter: (1) shadow log'da ≥200 eşleşmiş karar, (2) ≥30 çözümlü ayrışma (missed-opp: missed_win=challenger haklı / avoided_loss=champion haklı), (3) challenger ayrışma isabetinin %95 Wilson ALT sınırı > 0.5. ÜÇÜ tutarsa learning worker governor defterine OWNER ONAY PAKETİ sunar (STRATEGY_ENABLE, submit-dedupe'lu → tek PENDING). KIRMIZI ÇİZGİ testle kilitli: READY olsa bile weights/rebalance'a hiçbir yazım yok; onay bile yalnız defteri günceller. Yüzey: GET /learning/promotion-criteria + worker run meta `promotion_status` | 🟡 | F5 |
| F5-3 | Outcome-watchdog'u (guard_safety deseni) tüm canlı davranış değişikliklerine standart sarmalayıcı yap | 4.6 | ✅ (2026-07-02, PR #50 merge): `packages/learning/activation_watchdog.py` — 11 owner-flag'lik kayıt (thresholds + env), OFF→ON geçişinde eşleştirilmiş baseline damgalanıp izleme açılır, yeterli outcome'da post-vs-baseline → CONFIRMED/DEGRADED. guard_safety'den bilinçli fark: YALNIZ-ÖNERİ — hiçbir flag'i oto-kapatmaz, override/config yazmaz (🟢 sınıf; oto-kapat her seam'e kill-switch ister = ayrı 🟡 iş). Yön guard'ları kayıtta YOK (çifte izleme olmaz; oto-kapatlı kasaları guard_safety'de). Yüzey: learning worker her cycle `activation_watchdog.run()` (run meta + log) + GET /learning/activation-watchdog. İlk görüşte zaten-ON flag izlenmez (owner-niyeti semantiği) | 🟢 | F5 |
| F5-4 | Üretilen weights YAML'larını `data/runtime/weights/`e taşı (loader çift-yol okur; config=insan, data=makine) | 4.7 | ✅ (2026-07-02, PR #53 merge) `_weights_output_dir()` default artık `data/runtime/weights/` (gitignore'lu — makine üretimi yaml'lar git status'u kirletmez); `WEIGHTS_OUTPUT_DIR` env override aynen. Loader çift-yol fallback: manifest'teki yol yoksa dosya adı önce data/runtime/weights/, sonra config/ altında aranır (eski manifest'ler + Windows backslash yolları kırılmaz); hiçbir yerde yoksa baseline v1.0. Mevcut config/ altındaki üretilmiş dosyalar YERİNDE bırakıldı (canlı worker eski kodla koşarken taşımak baseline'a düşürürdü) — merge+restart sonrası istenirse elle taşınabilir, fallback iki durumda da bulur. Davranış değişikliği yok: yalnız yeni yazımların dizini değişir | 🟡 | F5 |
| R2-3 | `test_rotation` yuvarlama kırığı (weights 4-ondalık redistribute, 1e-6 tolerans) | suite | ✅ (tolerans 1e-3; invariant yuvarlama-öncesi korunuyor) | 🟢 | F1 |
| M1 | News sentiment morfoloji düzeltmesi: tam-kelime eşleşmesi çekimli halleri kaçırıyor ("rebounds"/"surges"/"plunges" → neutral); "escalat"/"retaliat" kök girdileri hiç eşleşemiyor. Token kök-normalizasyonu (EN -s/-es/-ed/-ing) + flag `news.sentiment_v2` (default OFF) + v1/v2 yan yana gözlem logu | 2026-07-02 modül denetimi §1 | ✅ (2026-07-02) `classify_sentiment_v2` + `classify_sentiment_active` (flag OFF → v1 bayt-aynı, 67 canlı başlıkta doğrulandı); her headline `sentiment_v2` gözlem alanı taşır (regime-report + sözleşme). Canlı kanıt: 67 başlığın 17'si v2'de yön kazandı. AKTİVASYON BEKLİYOR: owner regime-report'ta v1/v2 ayrışmasını izleyip `news.sentiment_v2: true` yapar (tarihli yorum) | 🟡 | M |
| M2 | Makro veri kaybında görünürlük: FRED quote'ları düşünce warnings'e `macro_data_missing` yaz (bugün sessiz default'a düşüyor; canlıda FRED çalışıyor ama kesinti sessiz kalıyor) — F2-3 ile aynı PR'da gider | 2026-07-02 modül denetimi §2 | ✅ (2026-07-02) `pipeline._regime_macro_missing` → snapshot warnings (flag'siz, her zaman); canlı doğrulandı | 🟢 | M |
| M3 | Fundamental v2: Kripto Momentum'u fundamental'den çıkar (BTC teknikleri touche'ta zaten var — çifte sayım); fundamental = likidite+rotasyon. Flag `consensus.fundamental_v2` (default OFF), shadow'da v1/v2 skoru yan yana | 2026-07-02 modül denetimi §3 | ✅ (2026-07-02) `_fundamental_v2` + flag (OFF → v1 bayt-aynı); her hücrede `fundamental_v2_observe:v1=..:v2=..` warning satırı (dashboard cells). Canlı kanıt: v1=57.4 → v2=63.6 (BTC 45.0 çifte sayımı çıktı). AKTİVASYON BEKLİYOR | 🟡 | M |
| M4 | Sentinel v2: tek-gösterge VIX yerine çok-girdili stres kompoziti (VIX + realized-vol z + funding extreme + options stress; eksik girdi → redistribute). Flag'li, shadow-önce (CRISIS'te ağırlığı 0.45 — tek sayı taşımasın) | 2026-07-02 modül denetimi §4 | ✅ (2026-07-02) `_sentinel_v2` + flag `sentinel_v2.enabled` (OFF → v1 bayt-aynı). Kompozit: VIX 0.5 + realized-vol z-skoru 0.25 + kripto squeeze proxy 0.15 (funding extreme proxy bileşeni) + options stres rejimi 0.10 — hepsi snapshot'ta zaten hesaplanan girdiler (yeni ağ çağrısı yok), yalnız verified+OK sayılır (DATA_POLICY), eksik girdi redistribute (VIX yokken v2 kalan girdilerle YAŞAR — v1'in tek-nokta kırılganlığı böylece kapanır). Her hücrede `sentinel_v2_observe:v1=..:v2=..` warning satırı. AKTİVASYON BEKLİYOR | 🟡 | M |
| M5 | chart_pattern ölü slotunu KALDIR (owner kararı 2026-07-02): gerçek formasyon tespiti zaten touche içinde çalışıyor (`technical/timeframe.py` `patterns.detect` + `_pattern_alignment`, direction_tilt %25) — ayrı konsensüs modülü aynı kanıtı İKİ KEZ sayardı (M3'teki çifte-sayım hatasının aynısı). Stub provider (`providers/patterns/`) + MODULE_ORDER + weights şablonlarındaki `chart_pattern` girdileri silinir; redistribute davranışı bayt-aynı kalır (slot zaten hep boştu) | 2026-07-02 modül denetimi §5 | ✅ (2026-07-02) Silinen: stub `providers/patterns/`, MODULE_ORDER girdisi, weights v1.0/v1.1 anahtarları, ticket "Grafik desen" etiketi, hiç çağrılmayan `loader.load_weights()`. Bayt-aynı kanıtı: slot hiç `raw`'a girmediği için `_redistribute` zaten onu normalizasyon paydasına almıyordu. Trainer proposal'ı artık eski üretilmiş dosyalardan `chart_pattern`'i carry-forward ETMEZ (süzgeç; tüm aktif dosyalar temizlenince kaldırılabilir) | 🟢 | M |
| M6 | Ölü config temizliği: `position_cap_per_asset_pct` (%25) enforce-veya-kaldır (thresholds yorumunda "ölü config" itirafı); regime classifier docstring'indeki bayat "mock veriyle" ifadesi F2-3'te güncellenir | 2026-07-02 modül denetimi §6 | ✅ (2026-07-02) KALDIRILDI (enforce değil): anahtar hiçbir kod yolunda okunmuyordu; per-asset tavan zaten iki canlı mekanizmayla kapalı — `max_position_usd` (sizing enforce) + `concentration_guard.max_symbol_pct` (%5, daha sıkı). Üçüncü çakışan cap eklemek karmaşıklık olurdu. "Mock" docstring'i F2-3'te zaten güncellenmişti — ek iş çıkmadı. M SERİSİ TAMAM | 🟢 | M |
| T-1 | Üst-TF hiza filtresi: alt TF touche skoru üst basamağın (15m→1h→4h→1d, Elder oranı) yönüne TERSse 50'ye kısılır (yalnız küçültür; aynı yön boost YOK, üst TF nötr/verisiz → dokunmaz, yön asla çevrilmez) | 2026-07-02 owner onayı (TA genişletme); kanıt: 15m ampirik EV negatif + missed-opp %87 avoided_loss | ✅ (2026-07-02) flag `technical.htf_alignment` DEFAULT OFF (bayt-aynı); karşıtlıkta `htf_alignment[_shadow]` warning satırı her zaman (consensus warnings). Not: conflict resolver yalnız CONFLICTED'ı bloklar, COUNTERTREND skor seviyesinde işlenmiyordu — bu boşluğu kapatır; aktivasyon kanıtı conflict-gate'le bindirmeyi tartmalı. 9 test. AKTİVASYON BEKLİYOR | 🟡 | T |
| T-2 | Elliott × Fib confluence: GEÇERLİ Elliott sayımının (hard-rule + confidence≥60) invalidation/hedef seviyeleri confluence bölgelerine `elliott_*` bileşeni olarak girer (4h/1d); fib+elliott aynı bölgede → konum kanadı 0.6→0.8 (kapı tavanı +%15 DEĞİŞMEZ — Elliott tek başına yön üretemez/bölge kuramaz) | 2026-07-02 owner onayı (TA genişletme; owner fikri: "iki yöntem aynı seviyedeyse skor daha kaliteli") | ✅ (2026-07-02) flag `technical.elliott_confluence` DEFAULT OFF (bölgeler bayt-aynı); elliott'lu bölge farkı `elliott_confluence_shadow` evidence satırı. Elliott motoru İLK KEZ bir karar-yüzeyine bağlandı — yalnız kural-türevi seviyeler, senaryo/yön DEĞİL. 10 test. AKTİVASYON BEKLİYOR | 🟡 | T |
| T-3 | Destek/direnç gücü: seviye "var/yok" yerine pivot-geçmişi dokunma sayısı tartılır (1 dokunuş 0.5 / 2 → 0.6 / 3+ → 0.7; T-2 ile birlikte tavan 0.9) | 2026-07-02 owner onayı (TA genişletme) | ✅ (2026-07-02) flag `technical.sr_strength` DEFAULT OFF (0.6 sabit, bayt-aynı); dokunma sayıları `sr_strength[_shadow]` evidence satırında her zaman gözlemde. 6 test. AKTİVASYON BEKLİYOR | 🟡 | T |
| T-4 | Kilit seviyede mum teyidi: pin bar (hammer/shooting star) + engulfing dedektörü (`providers/technical/candles.py`, kapanmış barlar, uydurma yok); YALNIZ fiyat confluence bölgesindeyken formasyon kanadına ek bileşen (yön üretmez, momentumla uyum/çelişki tartar) | 2026-07-02 owner onayı (TA genişletme) | ✅ (2026-07-02) flag `technical.candle_confirm` DEFAULT OFF (skor bayt-aynı); tespit `candle_confirm[_shadow]:name:bias:at_zone=` evidence satırında her zaman gözlemde. 11 test. AKTİVASYON BEKLİYOR | 🟡 | T |

## Neden bu sıra?

**F1 (ölçüm standardı) her şeyden önce** — F3+ trainer'ları ve rollback'ler
"expectancy" sayısına göre karar veriyor. O sayı bugün USD-bazlı ve
başabaş-kirli. Ölçüm düzelmeden optimizasyon yapmak, bozuk cetvelle
marangozluk. F1 slice'ları davranış değiştirmez (🟢) → hızlı ve güvenli.

**F2 (risk gerçek-zamanlılığı) ikinci** — sermaye koruması, sonraki tüm
deneylerin sigortası. F2-1 kırmızı: önce MTM değerleri snapshot/heartbeat'e
sadece YAZILIR (gözlem), banttaki davranış görülünce flag'le gate'e bağlanır.

**F3 (öğrenme istatistiği) üçüncü** — F1'in R-metriği + CI'ları üstüne
oturur. Rejim-filtreli eğitim (F3-2) doğal olarak veri setini küçültür;
CI'lı karar mekanizması (F3-1) olmadan açılırsa gürültüyle ağırlık oynatır —
bu yüzden F3-1, F3-2'den önce.

**F4 (karar zinciri kalitesi) dördüncü** — kalibre p(win) zincirin her
halkasını sürüyor; F0-1+F4-1 ile girdi dürüstleşince EV/Kelly (F4-2) ve
exit geometrisi (F4-3) gerçek edge'e göre ayarlanabilir.

**F5 (otonomi) en son** — CP5 köprüsü. Terfi/counterfactual mekanizmaları
ancak güvenilir ölçüm (F1) + istatistik (F3) üzerinde anlamlı. Yön terfisi
KIRMIZI ÇİZGİ: hiçbir slice otomatik yön değişikliği yapmaz, owner onay
paketi üretir.

## Modül katmanı denetimi (2026-07-02) — M serisi

Canlı BTC simülasyonu + kod denetimiyle konsensüs modül katmanı incelendi
(kanıtlar oturum kaydında; sentiment sondası + FRED sondası + rotasyon
kanıt satırları). Hüküm özeti:

- **touche ✅ / quantum ✅ sağlıklı** — gerçek OHLCV/momentum, dürüst
  degradasyon, TF farklılaşması çalışıyor. Dokunma.
- **news ❌ fiilen kör (M1)**: `classify_sentiment` tam-kelime eşleşmesi;
  İngilizce başlıkların 3. tekil çekimi ("Bitcoin rebounds…") sistematik
  neutral kalıyor → news skoru neredeyse hep 50. F0-2'nin sembol filtresi
  ancak M1'den sonra gerçek sinyal taşır. Aynı sentiment catalyst/surprise
  motorlarını da besliyor — düzeltmenin etki alanı geniş, o yüzden flag'li.
- **fundamental ⚠️ (F2-3 + M2 + M3)**: FRED kesintisinde katman sessizce
  sahte default'la (US10Y=4.3) hesaplanıyor (sondayla kanıtlandı; katman
  96.2 üretti, konsensüsü ~4 puan oynatır — nötr/short sınırını değiştirir).
  Ayrıca Kripto Momentum katmanı BTC 1d teknik skorunun kopyası → BTC
  kararında çifte sayım.
- **sentinel ⚠️ (M4)**: hesap doğru, veri gerçek ama tek gösterge (VIX);
  CRISIS rejiminde ağırlığı 0.45 — tek sayıya aşırı güç.
- **chart_pattern ❌ (M5)**: hiç yazılmamış kalıcı boş slot. Gerçek
  formasyon tespiti touche'un direction_tilt kapısında zaten canlı
  (pattern %25 ağırlıkla güveni eğer, yön üretmez) — bu yüzden slot
  inşa edilmez, KALDIRILIR (ayrı modül = çifte sayım, bkz. M3).

**M sırası:** M1 → F2-3(+M2, tek PR) → M3 → M4 → M5 → M6. Gerekçe: en
yüksek sinyal/maliyet M1'de (kör modül görmeye başlar); sonra veri
dürüstlüğü (F2-3); yapısal değişiklikler (M3/M4) ağırlık trainer'ı (F3-2)
modüllere anlamlı ağırlık öğrenebilsin diye ondan ÖNCE bitmeli. Mevcut
F2-2 bu seriden bağımsız, paralel gidebilir.

## Slice şablonu (her iş bu adımlarla gider)

1. **Additive kod** + flag default-OFF (veya salt-gözlem alanı) — davranış bayt-aynı.
2. **Testler:** eski davranışın birebir korunduğu regresyon testi + yeni davranış testleri.
3. **Shadow/gözlem penceresi** (🔴 işler için zorunlu, 🟡 için önerilir).
4. **Owner aktivasyonu** — config'te tarihli yorum ("2026-XX-XX: AÇILDI, owner kararı").
5. **Rollback izleme** — mümkün olan her yerde outcome-bazlı otomatik geri alma.
6. Bu tabloda durum güncellemesi.
