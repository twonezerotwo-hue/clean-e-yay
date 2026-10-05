# ROADMAP — sıradaki iş

Tek ileriye dönük plan. Eski yol haritaları (`AUDIT_ROADMAP`, `ROADMAP_10_10`,
Haziran `ROADMAP`) `docs/archive/` altında; yalnız tarihçe içindir.

## Şu an: büyük temizlik (2026-10)

Tek kural: **sistemin çalışması bozulmaz.** Her PR tek tema; silme PR'ları golden
replay'de bayt-aynı olmak zorunda; mantık düzeltmeleri farkı PR açıklamasında
listeler. Temizlik boyunca yeni özellik, yeni flag, yeni veri kaynağı eklenmez.

| Faz | İçerik | Durum |
| --- | --- | --- |
| 0 | Golden replay, sözleşme ratchet'i, CI drift + tsc, sabit `--basetemp` | Hazır |
| 1 | Veriyi bozan hatalar: H5/H6 atıf + keşif etiketi, H1 bayat/önceki bar stopu, H2 2R acil fren, H3 tick bekçisi, H11 zarar frenleri | Hazır |
| 2 | Ölü kod: hiç açılmamış 4 özellik, meta_gate, 0-2 karnesi, governor görev üreticisi söküldü; doküman arşivi | Hazır |
| 3 | Owner kararları (K1–K8) + ağırlıklar git'te (H8/K5) + test izolasyonu (H17) + hata kayıpları öğrenmeden ayrıldı (H7) | Hazır |
| 4 | Yapıldı: tek atomik store yardımcısı (B6), sondan okuma (B12), strateji backtest'i canlı stop kuralıyla (B4), kaynak seçici söküldü (G6), tek çalıştırma girişi (B3), env defteri + ratchet (B9), 13 ölü adres (B1), Conscious sekmeleri (K8). Kalan: 28 sözleşme-dışı adres (ratchet ile yalnız azalır; dokunuldukça sözleşmeye alınır). YAML bölme (B8) yapılmadı: flag'ler bölümlerinin parametreleriyle yan yana kalınca daha okunur; env defteri flag listesini zaten tek yerde veriyor | Hazır |
| 5 | Tek çalışma şekli (K6), GET'ler rejim hafızasına yazmıyor (H10), karar motorunda ortak hold yardımcısı (B11 adım 1). Kalan: kapıların ayrı fonksiyonlara bölünmesi (B11 adım 2) | Sürüyor |

## Verilmiş owner kararları (2026-10-02)

- **K1** Paper keşif açılışları açık kalır; pozisyonlar `exploration=true` damgalanır.
- **H2** Acil fren 2 birimde (`disaster_mult: 2.0`).
- **H11** Günlük %2 → yeni pozisyon yok, gün sonu kalkar; %8 DD → kapat + owner reset.
- **H12** BRENT verisindeki kontrat-geçişi sıçramalarına dokunulmaz.
- **K9** Teknik üçlü (`elliott_confluence`, `sr_strength`, `candle_confirm`) açık. Ölçüm
  (27 seri, 1h/4h/1d, 1055 işlem, canlı stop kuralı): açık/kapalı farkı +5R toplam,
  işlem başına +0.005R — zararsız, kayda değer fayda yok. Canlı teknik oy v4'ten
  geldiği için yalnız yedek teknik motoru ve rejim kripto katmanını etkiler.
- Fırtına kuralı (`gates.regime_manual_ready`) ve kaynak politikası
  (`consensus.enforce_decision_usage`) kalır; açma kararı ayrı.

- **K1b** Keşif trade'leri yalnız güven kalibrasyonuna girer (EXPLORATION kohortu).
- **K2** tf_scoring v4 canlıda (`consensus.touche_v4: true`).
- **K3** `meta_gate` silindi; `learning_advisor` kalır.
- **K4** 0-2 karnesi silindi, 0-2 stratejisi donduruldu; bölge önerici kalır;
  governor görev üreticisi silindi, öneri/onay defteri kalır.
- **K6** Tek çalışma şekli: her yerde `apps.supervisor` (tick/learning thread'de, API donmaz).
- **K7** Telefon erişimi (ngrok, şifresiz) olduğu gibi kalır.
- **K8** Ekran sadeleşir: ana ekranda yalnız owner'ın karar verdiği/her gün baktığı
  paneller; diğer state'ler tek "Detaylar" sayfasında (docs/DASHBOARD_RULES.md).
- **K8b** Heart (Katman 1) aynı kalır; yalnız Conscious'taki tekrar eden kutular sekmeli
  tek kutuya birleşir (owner her gün haber/dünya özetine bakıyor).
- **K5** Ağırlıklar git'te (`config/weights_active.json`), owner onayıyla değişir;
  oto-uygulama kapalı.

## Verilmiş owner kararları (2026-10-03, olay-sonrası takipten)

- **E1** Event kapısı olayın gerçek saatini kullanır (takvim `time`/`expectation`)
  ve yüksek etkili veri açıklandıktan sonra 30 dk daha yeni pozisyon açılmaz
  (`event_risk.post_release_cooldown_minutes`).
- **E2** Makro başlıkta yön duygudan değil sürprizden (zayıf/güvercin → DXY↓) ve
  başlığın açıkça söylediği hareketten ("Dollar falls", "stock futures jump") gelir.
- **E3** Beklenen tepki faiz kanalıyla okunur; takvim etki metinleri buna göre.
- **2a** Lokal yazma anahtarı panelde bir kez sorulur (tarayıcıda saklanır).

## Verilmiş owner kararları (2026-10-05, Fikir Panosu)

- Keşif makinesi haber öngörüsü + teknik analiz + YZ değerlendirmesiyle birleşir
  (docs/STATE.md "Keşif & Fikir Panosu"); her şey salt-gözlem.
- YZ = yerel `qwen3:8b` (Ollama, düşünme kapalı). AWS'te yerel model yok →
  deterministik değerlendirme.
- Evrene emtia eklenir (bakır, doğalgaz, WTI, platin, paladyum, tarım, uranyum,
  lityum); haberden ayrıca aday üretilmez.
- Fikirler Heart'ta "Fikirler" sekmesinde; adaya özel web haber araması sınırlı.

## Açık owner kararları

- **E4 Olay sonucunu karara bağlamak:** CP5 kırmızı çizgi — yeterli olay birikip
  kanıt çıkmadan yapılmaz; yalnız owner onayıyla. Kanıt: Olay Takvimi paneli /
  `GET /api/v1/calendar/event-outcomes` (aile × sonuç × ufuk isabet oranı).
- Haber eşlemesinde kayıt defteri terimleri alt-dize olarak aranıyor ("Sep**tem**ber"
  → TEM, "N**eth**ermind" → ETHUSD); kelime-sınırı düzeltmesi owner onayı bekliyor.

- **Fikir → paper işlem bağlantısı:** CP5 kırmızı çizgi — fikir skoru ve haber
  öngörü karnesi (Fikirler sekmesi alt satırı) kanıt biriktirmeden karar yoluna
  bağlanmaz; yalnız owner onayıyla.

## Temizlikten sonra (ölçüm işleri)

- Temiz veriyle (H1–H3 sonrası) 30 gün paper → strateji kararı: işlemlerin
  çoğu konsensüs skoru 40–60 bandında açılıyor; alt sinyallerden yalnız
  `vwap_fade` ölçülebilir avantaj taşıyor.
- Dünya durumu / nedensellik gölgesi: 60 gün veri birikmeden karar yoluna bağlanmaz.
