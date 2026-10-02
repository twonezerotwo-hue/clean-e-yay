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
| 3 | Owner kararları (K1–K5 verildi) + ağırlıklar git'te (H8/K5) + test izolasyonu (H17); temiz veriyle yeniden eğitim (H7) | Sürüyor |
| 4 | Birleştirmeler: kanıt katmanı, 7 backtest motoru → 1, 7 kalibrasyon modülü → 1, tek store yardımcısı, flag defteri, sözleşme borcu, panel birleştirme | Bekliyor |
| 5 | Tek çalışma topolojisi (AWS'de de ayrı süreçler), karar motorunun bölünmesi | Bekliyor |

## Verilmiş owner kararları (2026-10-02)

- **K1** Paper keşif açılışları açık kalır; pozisyonlar `exploration=true` damgalanır.
- **H2** Acil fren 2 birimde (`disaster_mult: 2.0`).
- **H11** Günlük %2 → yeni pozisyon yok, gün sonu kalkar; %8 DD → kapat + owner reset.
- **H12** BRENT verisindeki kontrat-geçişi sıçramalarına dokunulmaz.
- Teknik üçlü (`elliott_confluence`, `sr_strength`, `candle_confirm`) silinmez;
  temizlikten sonra geçmiş veride açık/kapalı ölçülüp karar verilir.
- Fırtına kuralı (`gates.regime_manual_ready`) ve kaynak politikası
  (`consensus.enforce_decision_usage`) kalır; açma kararı ayrı.

- **K1b** Keşif trade'leri yalnız güven kalibrasyonuna girer (EXPLORATION kohortu).
- **K2** tf_scoring v4 canlıda (`consensus.touche_v4: true`).
- **K3** `meta_gate` silindi; `learning_advisor` kalır.
- **K4** 0-2 karnesi silindi, 0-2 stratejisi donduruldu; bölge önerici kalır;
  governor görev üreticisi silindi, öneri/onay defteri kalır.
- **K5** Ağırlıklar git'te (`config/weights_active.json`), owner onayıyla değişir;
  oto-uygulama kapalı.

## Açık owner kararları

1. Çalışma topolojisi: her yerde ayrı süreç mi, her yerde supervisor mı?
2. Telefon erişimi: ngrok'a kimlik doğrulama mı, yalnız LAN/VPN mi?
3. Dashboard kuralı: "backend yeni state üretirse panel eklenir" kuralı çok panele yol açtı;
   yalnız owner'ın karar verdiği konular panel alsın mı?

## Temizlikten sonra (ölçüm işleri)

- Teknik üçlünün geçmiş veride açık/kapalı karşılaştırması.
- Temiz veriyle (H1–H3 sonrası) 30 gün paper → strateji kararı: işlemlerin
  çoğu konsensüs skoru 40–60 bandında açılıyor; alt sinyallerden yalnız
  `vwap_fade` ölçülebilir avantaj taşıyor.
- Dünya durumu / nedensellik gölgesi: 60 gün veri birikmeden karar yoluna bağlanmaz.
