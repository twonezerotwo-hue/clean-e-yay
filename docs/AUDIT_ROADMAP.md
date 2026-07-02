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
- **Tamamlanan:** F0-1, F0-2, F1-1…F1-5, R2-3 + F2-1 gözlem fazı
  (aşağıdaki tabloda ✅/🔶 ve ayrıntılar). Suite 1189/1189 yeşil, ruff'ta
  yeni hata yok (tests/ altında ~45 eski baseline bulgusu var, dokunulmadı).
- **Sıradaki iş:** F4-3 (partial-TP + breakeven stop — 🔴 sınıfı: önce
  shadow yan-yana ölçüm zorunlu). F3 serisi kapandı: F3-1 owner kararıyla
  YAPILMAYACAK, F3-2+F3-3 kodlandı (flag OFF). F2-1 gate-bağlama owner
  kararı bekliyor.
- **Bekleyen owner aktivasyonları:** (1) `news.sentiment_v2` (M1 kodu
  canlıda, flag OFF — regime-report'taki v1/v2 ayrışması izlenip açılır);
  (2) `regime.drop_unavailable_layers` (F2-3 kodu canlıda, flag OFF —
  `macro_data_missing` uyarısı + `dropped_layers` izlenip açılır);
  (3) `consensus.fundamental_v2` (M3 kodu canlıda, flag OFF — hücre
  warning'lerindeki `fundamental_v2_observe` ayrışması izlenip açılır);
  (4) `sentinel_v2.enabled` (M4 kodu canlıda, flag OFF — hücre
  warning'lerindeki `sentinel_v2_observe` ayrışması izlenip açılır);
  (5) `risk_gates.correlation_price_returns` (F2-2 kodu canlıda, flag OFF —
  /risk/correlation matrisindeki `rho_price` gözlemi izlenip açılır);
  (6) `WEIGHT_REGIME_FILTER` env (F3-2 — rejim başına INSUFFICIENT/proposal
  dağılımı izlenip açılır); (7) `MISTAKE_MEMORY_V2` env (F3-3 — verdict
  dağılımındaki `[L1]/[L2]` fallback + WARNING/AVOID oranı izlenip açılır);
  (8) F2-1 gate-bağlama (snapshot store'daki
  `paper_state_summary.mtm_equity_usd` bandı izlenip RiskInput'a flag'le
  bağlanır); (9) `EXPECTANCY_R_MODE` (R-damgalı outcome birikince);
  (10) `calibration.tf_platt` (F4-1 kodu canlıda, flag OFF —
  GET /learning/calibration `per_timeframe` örnek/fit ayrışması izlenip
  açılır); (11) `empirical_pwin.enabled` (F4-2 kodu canlıda, flag OFF —
  matrix hücrelerindeki `p_win_empirical`/`expected_value_empirical`
  gözlemi izlenip açılır; kanıt: 15m ampirik EV negatif).
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
| F4-1 | TF-bazlı Platt kalibrasyonu (tf_calibration altyapısı üstüne) | 3.1 | ✅ (2026-07-02) flag `calibration.tf_platt` DEFAULT OFF (global fit bayt-aynı). Trainer her koşuda TF başına fit yazar (`platt.json per_timeframe`, additive; MIN_SAMPLES altı TF → insufficient+identity, sahte fit yok); karar anında `predict_calibrated_tf` (OFF → global birebir; ON → TF fit'i, kaynak "fitted_tf", yoksa global fallback). Şişme guardrail'i fitted_tf'e de uygulanır ("fitted_tf_capped"); calibration_audit sayımları iki kaynağı da görür. Gözlem: GET /learning/calibration `per_timeframe`+`tf_platt_enabled` + worker log `tf_fitted`. Canlı kanıt (108 verified outcome): 4 TF'in 4'ü fit; raw 0.10 → global 0.39 ama 15m 0.29 / 4h 0.49 — global fit 15m'de aşırı iyimser. AKTİVASYON BEKLİYOR | 🟡 | F4 |
| F4-2 | EV/Kelly p(win)'ini ampirik TF+rejim hit-rate'ine bağla | 3.3 | ✅ (2026-07-02) `packages/learning/empirical_pwin.py`: learning worker her cycle verified outcome'lardan (tf\|rejim)+tf hit-rate tablosunu yazar (`data/runtime/empirical_pwin.json`; başabaş paydaya girmez/F1-2; min_samples=20 altı hücre lookup'ta DÖNMEZ). Karar motoru mtime-cache ile okur; flag `empirical_pwin.enabled` DEFAULT OFF → EV+Kelly cal_conf ile (bayt-aynı), ampirik değerler her hücrede SALT-GÖZLEM (`p_win_empirical`/`expected_value_empirical`). AÇIKKEN: yeterli hücrede EV+Kelly gerçekleşmiş isabetle; kanıt yoksa cal_conf fallback. Canlı kanıt: 15m\|NEUTRAL p=0.425 → EV −0.04R (NEGATİF — maliyet sonrası kaybettiriyor), 4h\|NEUTRAL p=0.548 → +0.55R; aktivasyon 15m'i bloklar, 4h'ı doğru boyutlar. Yan kazanım: conftest artık canlı platt.json/empirical tabloyu suite'ten izole ediyor. AKTİVASYON BEKLİYOR | 🟡 | F4 |
| F4-3 | Partial-TP + breakeven stop (1R'de %50 kapat; önce shadow yan-yana ölçüm) | 3.6 | ⬜ | 🔴 | F4 |
| F5-1 | Counterfactual (missed_opportunity) verisini kalibrasyon/eşik kanıtına bağla | 4.3 | ⬜ | 🟡 | F5 |
| F5-2 | Champion/challenger terfi kriteri formalize (N eşleşmiş karar + CI ayrık → owner paketi) | 4.5 | ⬜ | 🟡 | F5 |
| F5-3 | Outcome-watchdog'u (guard_safety deseni) tüm canlı davranış değişikliklerine standart sarmalayıcı yap | 4.6 | ⬜ | 🟢 | F5 |
| F5-4 | Üretilen weights YAML'larını `data/runtime/weights/`e taşı (loader çift-yol okur; config=insan, data=makine) | 4.7 | ⬜ | 🟡 | F5 |
| R2-3 | `test_rotation` yuvarlama kırığı (weights 4-ondalık redistribute, 1e-6 tolerans) | suite | ✅ (tolerans 1e-3; invariant yuvarlama-öncesi korunuyor) | 🟢 | F1 |
| M1 | News sentiment morfoloji düzeltmesi: tam-kelime eşleşmesi çekimli halleri kaçırıyor ("rebounds"/"surges"/"plunges" → neutral); "escalat"/"retaliat" kök girdileri hiç eşleşemiyor. Token kök-normalizasyonu (EN -s/-es/-ed/-ing) + flag `news.sentiment_v2` (default OFF) + v1/v2 yan yana gözlem logu | 2026-07-02 modül denetimi §1 | ✅ (2026-07-02) `classify_sentiment_v2` + `classify_sentiment_active` (flag OFF → v1 bayt-aynı, 67 canlı başlıkta doğrulandı); her headline `sentiment_v2` gözlem alanı taşır (regime-report + sözleşme). Canlı kanıt: 67 başlığın 17'si v2'de yön kazandı. AKTİVASYON BEKLİYOR: owner regime-report'ta v1/v2 ayrışmasını izleyip `news.sentiment_v2: true` yapar (tarihli yorum) | 🟡 | M |
| M2 | Makro veri kaybında görünürlük: FRED quote'ları düşünce warnings'e `macro_data_missing` yaz (bugün sessiz default'a düşüyor; canlıda FRED çalışıyor ama kesinti sessiz kalıyor) — F2-3 ile aynı PR'da gider | 2026-07-02 modül denetimi §2 | ✅ (2026-07-02) `pipeline._regime_macro_missing` → snapshot warnings (flag'siz, her zaman); canlı doğrulandı | 🟢 | M |
| M3 | Fundamental v2: Kripto Momentum'u fundamental'den çıkar (BTC teknikleri touche'ta zaten var — çifte sayım); fundamental = likidite+rotasyon. Flag `consensus.fundamental_v2` (default OFF), shadow'da v1/v2 skoru yan yana | 2026-07-02 modül denetimi §3 | ✅ (2026-07-02) `_fundamental_v2` + flag (OFF → v1 bayt-aynı); her hücrede `fundamental_v2_observe:v1=..:v2=..` warning satırı (dashboard cells). Canlı kanıt: v1=57.4 → v2=63.6 (BTC 45.0 çifte sayımı çıktı). AKTİVASYON BEKLİYOR | 🟡 | M |
| M4 | Sentinel v2: tek-gösterge VIX yerine çok-girdili stres kompoziti (VIX + realized-vol z + funding extreme + options stress; eksik girdi → redistribute). Flag'li, shadow-önce (CRISIS'te ağırlığı 0.45 — tek sayı taşımasın) | 2026-07-02 modül denetimi §4 | ✅ (2026-07-02) `_sentinel_v2` + flag `sentinel_v2.enabled` (OFF → v1 bayt-aynı). Kompozit: VIX 0.5 + realized-vol z-skoru 0.25 + kripto squeeze proxy 0.15 (funding extreme proxy bileşeni) + options stres rejimi 0.10 — hepsi snapshot'ta zaten hesaplanan girdiler (yeni ağ çağrısı yok), yalnız verified+OK sayılır (DATA_POLICY), eksik girdi redistribute (VIX yokken v2 kalan girdilerle YAŞAR — v1'in tek-nokta kırılganlığı böylece kapanır). Her hücrede `sentinel_v2_observe:v1=..:v2=..` warning satırı. AKTİVASYON BEKLİYOR | 🟡 | M |
| M5 | chart_pattern ölü slotunu KALDIR (owner kararı 2026-07-02): gerçek formasyon tespiti zaten touche içinde çalışıyor (`technical/timeframe.py` `patterns.detect` + `_pattern_alignment`, direction_tilt %25) — ayrı konsensüs modülü aynı kanıtı İKİ KEZ sayardı (M3'teki çifte-sayım hatasının aynısı). Stub provider (`providers/patterns/`) + MODULE_ORDER + weights şablonlarındaki `chart_pattern` girdileri silinir; redistribute davranışı bayt-aynı kalır (slot zaten hep boştu) | 2026-07-02 modül denetimi §5 | ✅ (2026-07-02) Silinen: stub `providers/patterns/`, MODULE_ORDER girdisi, weights v1.0/v1.1 anahtarları, ticket "Grafik desen" etiketi, hiç çağrılmayan `loader.load_weights()`. Bayt-aynı kanıtı: slot hiç `raw`'a girmediği için `_redistribute` zaten onu normalizasyon paydasına almıyordu. Trainer proposal'ı artık eski üretilmiş dosyalardan `chart_pattern`'i carry-forward ETMEZ (süzgeç; tüm aktif dosyalar temizlenince kaldırılabilir) | 🟢 | M |
| M6 | Ölü config temizliği: `position_cap_per_asset_pct` (%25) enforce-veya-kaldır (thresholds yorumunda "ölü config" itirafı); regime classifier docstring'indeki bayat "mock veriyle" ifadesi F2-3'te güncellenir | 2026-07-02 modül denetimi §6 | ✅ (2026-07-02) KALDIRILDI (enforce değil): anahtar hiçbir kod yolunda okunmuyordu; per-asset tavan zaten iki canlı mekanizmayla kapalı — `max_position_usd` (sizing enforce) + `concentration_guard.max_symbol_pct` (%5, daha sıkı). Üçüncü çakışan cap eklemek karmaşıklık olurdu. "Mock" docstring'i F2-3'te zaten güncellenmişti — ek iş çıkmadı. M SERİSİ TAMAM | 🟢 | M |

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
