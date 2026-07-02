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
- **Sıradaki iş:** M3 (fundamental v2 — BTC çifte sayımını kaldır, flag'li)
  → M4 → M5/M6. F2-2 bu seriden bağımsız, araya alınabilir.
- **Bekleyen owner aktivasyonları:** (1) `news.sentiment_v2` (M1 kodu
  canlıda, flag OFF — regime-report'taki v1/v2 ayrışması izlenip açılır);
  (2) `regime.drop_unavailable_layers` (F2-3 kodu canlıda, flag OFF —
  `macro_data_missing` uyarısı + `dropped_layers` izlenip açılır);
  (3) F2-1 gate-bağlama (snapshot store'daki
  `paper_state_summary.mtm_equity_usd` bandı izlenip RiskInput'a flag'le
  bağlanır); (4) `EXPECTANCY_R_MODE` (R-damgalı outcome birikince).
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
| F2-2 | Korelasyonu fiyat getirisinden hesapla (OHLCV cache; kaynak önceliği computed_price > baseline > neutral) | 1.5, 3.7 | ⬜ | 🟡 | F2 |
| F2-3 | Regime layer'ları veri yokken düşür+redistribute (quantum deseni; default-sabit sahte skor yok) | 2 (classifier) | ✅ (2026-07-02) flag `regime.drop_unavailable_layers` DEFAULT OFF (eski davranış bayt-aynı). Açıkken: veri olmayan katman düşer (`RegimeOutput.dropped` → regime-report `dropped_layers`), fundamental/sentinel katmansız kalırsa consensus modülü de düşer+redistribute. Canlı kanıt (FRED'siz ortam): OFF Likidite=96.6 sahte → ON katman düştü, konsensüs 51.2→47.0 (~4.2p sahte şişme). AKTİVASYON BEKLİYOR (owner: `true` + tarihli yorum) | 🟡 | F2 |
| F3-1 | Wilson/bootstrap CI + üç-durumlu rollback kararı (geri al / onayla / izlemeye devam) | 1.6d, 4.1 | ⬜ | 🟡 | F3 |
| F3-2 | Ağırlık trainer'ına rejim filtresi + 4 rejimin ayrı eğitimi | 1.2 | ⬜ | 🟡 | F3 |
| F3-3 | Mistake memory: decision_log kaynağı + hiyerarşik fingerprint fallback + Wilson alt sınırı | 1.4, 4.4 | ⬜ | 🟡 | F3 |
| F4-1 | TF-bazlı Platt kalibrasyonu (tf_calibration altyapısı üstüne) | 3.1 | ⬜ | 🟡 | F4 |
| F4-2 | EV/Kelly p(win)'ini ampirik TF+rejim hit-rate'ine bağla | 3.3 | ⬜ | 🟡 | F4 |
| F4-3 | Partial-TP + breakeven stop (1R'de %50 kapat; önce shadow yan-yana ölçüm) | 3.6 | ⬜ | 🔴 | F4 |
| F5-1 | Counterfactual (missed_opportunity) verisini kalibrasyon/eşik kanıtına bağla | 4.3 | ⬜ | 🟡 | F5 |
| F5-2 | Champion/challenger terfi kriteri formalize (N eşleşmiş karar + CI ayrık → owner paketi) | 4.5 | ⬜ | 🟡 | F5 |
| F5-3 | Outcome-watchdog'u (guard_safety deseni) tüm canlı davranış değişikliklerine standart sarmalayıcı yap | 4.6 | ⬜ | 🟢 | F5 |
| F5-4 | Üretilen weights YAML'larını `data/runtime/weights/`e taşı (loader çift-yol okur; config=insan, data=makine) | 4.7 | ⬜ | 🟡 | F5 |
| R2-3 | `test_rotation` yuvarlama kırığı (weights 4-ondalık redistribute, 1e-6 tolerans) | suite | ✅ (tolerans 1e-3; invariant yuvarlama-öncesi korunuyor) | 🟢 | F1 |
| M1 | News sentiment morfoloji düzeltmesi: tam-kelime eşleşmesi çekimli halleri kaçırıyor ("rebounds"/"surges"/"plunges" → neutral); "escalat"/"retaliat" kök girdileri hiç eşleşemiyor. Token kök-normalizasyonu (EN -s/-es/-ed/-ing) + flag `news.sentiment_v2` (default OFF) + v1/v2 yan yana gözlem logu | 2026-07-02 modül denetimi §1 | ✅ (2026-07-02) `classify_sentiment_v2` + `classify_sentiment_active` (flag OFF → v1 bayt-aynı, 67 canlı başlıkta doğrulandı); her headline `sentiment_v2` gözlem alanı taşır (regime-report + sözleşme). Canlı kanıt: 67 başlığın 17'si v2'de yön kazandı. AKTİVASYON BEKLİYOR: owner regime-report'ta v1/v2 ayrışmasını izleyip `news.sentiment_v2: true` yapar (tarihli yorum) | 🟡 | M |
| M2 | Makro veri kaybında görünürlük: FRED quote'ları düşünce warnings'e `macro_data_missing` yaz (bugün sessiz default'a düşüyor; canlıda FRED çalışıyor ama kesinti sessiz kalıyor) — F2-3 ile aynı PR'da gider | 2026-07-02 modül denetimi §2 | ✅ (2026-07-02) `pipeline._regime_macro_missing` → snapshot warnings (flag'siz, her zaman); canlı doğrulandı | 🟢 | M |
| M3 | Fundamental v2: Kripto Momentum'u fundamental'den çıkar (BTC teknikleri touche'ta zaten var — çifte sayım); fundamental = likidite+rotasyon. Flag `consensus.fundamental_v2` (default OFF), shadow'da v1/v2 skoru yan yana | 2026-07-02 modül denetimi §3 | ⬜ | 🟡 | M |
| M4 | Sentinel v2: tek-gösterge VIX yerine çok-girdili stres kompoziti (VIX + realized-vol z + funding extreme + options stress; eksik girdi → redistribute). Flag'li, shadow-önce (CRISIS'te ağırlığı 0.45 — tek sayı taşımasın) | 2026-07-02 modül denetimi §4 | ⬜ | 🟡 | M |
| M5 | chart_pattern ölü slotunu KALDIR (owner kararı 2026-07-02): gerçek formasyon tespiti zaten touche içinde çalışıyor (`technical/timeframe.py` `patterns.detect` + `_pattern_alignment`, direction_tilt %25) — ayrı konsensüs modülü aynı kanıtı İKİ KEZ sayardı (M3'teki çifte-sayım hatasının aynısı). Stub provider (`providers/patterns/`) + MODULE_ORDER + weights şablonlarındaki `chart_pattern` girdileri silinir; redistribute davranışı bayt-aynı kalır (slot zaten hep boştu) | 2026-07-02 modül denetimi §5 | ⬜ | 🟢 | M |
| M6 | Ölü config temizliği: `position_cap_per_asset_pct` (%25) enforce-veya-kaldır (thresholds yorumunda "ölü config" itirafı); regime classifier docstring'indeki bayat "mock veriyle" ifadesi F2-3'te güncellenir | 2026-07-02 modül denetimi §6 | ⬜ | 🟢 | M |

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
