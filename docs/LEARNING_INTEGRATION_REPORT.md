# Öğrenme Katmanı — Entegrasyon & Otomasyon Raporu

**Tarih:** 2026-07-05 · **Kapsam:** `packages/learning/` (41 modül) + `packages/discovery/` + governor/watchdog/rollback makinesi
**Amaç:** Tüm öğrenme katmanını birbiriyle **entegre** ve **otomatik** hale getirmek; shadow ve toplanan verileri **gerektiğinde** döngüye dahil edebilmek.

---

## 0. Bir cümlede

Sistem öğrenme açısından **zengin ama adalar hâlinde**: 40+ öğrenici var, her biri iyi çalışıyor, ama hepsi **ayrı olgunluk katmanında** ve **ortak bir omurgaya bağlı değil**. Otomasyon var — ama her öğrenici kendi eşiğini, kendi kapısını, kendi dosyasını taşıyor. Bu rapor, hepsini tek bir **"kanıt → olgunluk kapısı → karar → izleme → geri-alma"** omurgasına bağlamayı ve shadow/backtest verisini bu omurgaya **fişe takılabilir kanıt** yapmayı öneriyor.

---

## 1. Bugünkü durum — öğrenme 4 farklı olgunlukta

Öğreniciler bugün dört ayrı olgunluk katmanında yaşıyor. Sorun teknik değil — **her katman ayrı mantıkla, ayrı elle bağlanmış**.

### Katman A — Otomatik kapalı-döngü (kendi kendine uyguluyor + bozulursa geri alıyor)
Bunlar gerçekten otomatik: öner → dar bantta uygula → sonucu izle → kötüleşirse geri al.
- **Ağırlık dengeleme** (`auto_weight_trainer` → `rebalance_store` → `weight_rollback`)
- **SL/TP geometri** (`tf_target_trainer` → `tf_target_store` → `tf_target_rollback`)
- **Eşik ayarı** (`threshold_trainer`, içsel edge-gate'li)
- **Trailing mesafesi** (TF-aware, `TF_TARGET_TRAIL_AUTOTUNE`)

> Ortak yanları: hepsi **dar bant + edge-gate + outcome-rollback** ile korunuyor. **AMA** her biri kapı/eşik mantığını **kendi içinde** taşıyor — ortak değil.

### Katman B — Öneri-only (owner onayı şart; kırmızı çizgi)
Kriter tutunca canlıya dokunmaz, **governor defterine owner paketi** düşürür:
- **`promotion_criteria`** (F5-2) — gölge karar hattı champion'ı geçti mi
- **`challenger_promotion`** (B-4) — backtest aday ağırlık champion'ı geçti mi
- **`discovery_promotion`** (K-4) — keşif adayı listeye eklenmeli mi

> Üçü de **aynı deseni** kullanıyor (Wilson alt sınırı + eşleşme + governor.submit) ama **üç ayrı kopya** — ortak bir "terfi motoru" yok.

### Katman C — Salt-ölçüm (ölçüyor ama karara bağlı değil)
Kanıt üretiyor, panele yazıyor, ama hiçbir karara/ağırlığa bağlı değil:
- **`signal_quality`** (FAZ-4, yeni) — hangi sinyal hangi piyasada ayırt ediyor
- **`edge_report`** — edge stabil mi (`safe_to_autotune`)
- **`exit_forensics`** — çıkış nerede para kaybettiriyor
- **`entry_exit_quality`** — giriş/çıkış kalite dersleri
- **`empirical_pwin`** (flag OFF) — gerçekleşen isabet tablosu
- **`book_audit`**, **`tf_contribution`**, **`historical_edge`**, **`calibration_audit`**

> Bunlar **kanıt fabrikaları** ama üretilen kanıt çoğunlukla **bir karara akmıyor** — dosyada/panelde kalıyor.

### Katman D — Shadow / veri kanalları (topluyor, ama döngüye girmiyor)
Veri biriktiriyor, ama bir öğrenici "gerektiğinde" bunlara **kendiliğinden uzanmıyor**:
- **`backtest_challenger`** (B-2/B-3) — geçmiş-prova kayıtları + quantum karnesi
- **`discovery_shadow`** (K-2) — keşif "açılırdı" hükümlerinin karnesi
- **`missed_opportunity`** — bloklanan kararların karşı-olgusu
- **`partial_tp_shadow`** — kısmi kâr-al senaryosu

> Bu veriyi B-3 ve FAZ-4'e **elle bağladım**. Otomatik değil — her yeni ihtiyaçta yeni köprü yazmak gerekiyor.

### Güvenlik makinesi (zaten var, ama kapsama eksik)
- **`governor/proposals`** — owner onay defteri (tek kanal, denetlenebilir)
- **`activation_watchdog`** — 15 owner-flag'in OFF→ON geçişini izler, bozulursa **öneri** verir
- **`guard_safety`** — yön guard'larını izler, bozulursa **oto-kapatır**
- **rollback modülleri** — weight / tf_target / threshold için ayrı ayrı

> Bunlar sağlam ama **her terfiye otomatik takılı değil** — bazısına elle bağlanmış.

---

## 2. Asıl sorun — neden "entegre değil"

Dört kök sorun var:

1. **Kanıt dağınık.** Her ölçüm ayrı dosyaya/panele yazıyor. Ortak bir "kanıt yüzeyi" yok → bir öğrenici başka bir öğrenicinin kanıtını kolayca kullanamıyor. (FAZ-4 ve B-3 aynı bulguyu iki ayrı yerde ölçtü.)

2. **Kapı dağınık.** "Bu öğreniciye güvenilir mi?" sorusuna her modül **kendi cevabını** taşıyor: kimi `edge_report`'a bakıyor, kimi Wilson'a, kimi min-örnek eşiğine. **Ortak olgunluk kapısı yok** → tutarsızlık + her yeni öğrenicide tekrar yazım.

3. **Shadow "gerektiğinde dahil" değil.** Backtest challenger, discovery shadow, missed_opp ayrı silolar. Bir trainer canlı verisi ince olunca bunlara **otomatik uzanmıyor** — elle köprü kuruldu (B-3, F5-1 cf-kanalı).

4. **Otomasyon merdiveni örtük.** Her flag'in "ölç → gölge → öner → oto-uygula" yolculuğu **elle + tarihli owner kararıyla** ilerliyor. Standart bir terfi hattı yok → 15+ flag, her biri ayrı takip.

---

## 3. Hedef mimari — tek omurga

Bütün öğreniciler tek bir hatta bağlanmalı:

```
  KANIT OTOBÜSÜ  →  OLGUNLUK KAPISI  →  KARAR  →  İZLEME  →  ROLLBACK
   (ne biliyoruz)   (güvenilir mi?)   (öner/  (bozuldu   (geri al)
                                       uygula)   mu?)
        ↑                  ↑
   shadow/backtest    kaynak seçici
   (fişe takılır)     (live yetmezse shadow)
```

### Bileşen 1 — Kanıt Otobüsü (Evidence Bus)
Tüm ölçümler **tek ortak şemayla** ortak bir kanıt kaydına yazsın. Her kayıt:
> `{ konu (hangi sinyal/ağırlık/geometri), rejim, TF, örnek sayısı, ayrım/istatistik, kaynak: live|shadow|backtest, olgunluk basamağı }`

**Ne çözer:** tek sorgu = "sistem şu an neyi biliyor". FAZ-4, edge_report, signal_quality, backtest karnesi, discovery shadow — hepsi aynı otobüse yazar. Tek panelden okunur.

### Bileşen 2 — Olgunluk Kapısı (Maturity Gate)
**Tek ortak fonksiyon** üç şeyi birlikte sorar (bugün dağınık olanı toplar):
1. Yeterli örnek var mı? (min-sample)
2. Edge stabil mi? (`edge_report.safe_to_autotune`)
3. İstatistiksel anlamlı mı? (Wilson alt sınırı / ayrım eşiği)

Her trainer bu kapıyı **çağırır**, kendi eşiğini taşımaz. Tutarlı + yeni öğrenicide sıfır tekrar.

### Bileşen 3 — Terfi Hattı (Promotion Rail)
Katman B'deki üç kopya (`promotion_criteria`/`challenger_promotion`/`discovery_promotion`) **tek motora** iner: "kanıt → Wilson kapısı → governor paketi → dedupe". Yeni bir terfi eklemek = birkaç satır config.

### Bileşen 4 — İzleme + Rollback (standartlaştır)
`activation_watchdog` + `guard_safety` + rollback **her** terfiye otomatik takılsın (bugün bazısına takılı). Kural: **canlıya dokunan hiçbir şey izlemesiz olmaz.**

---

## 4. Shadow/veri "gerektiğinde dahil" mekanizması (senin asıl isteğin)

Kalbi **Kaynak Seçici**. Her öğrenici karar anında şunu sorar:

> "Bu rejim/TF için yeterli **CANLI** kanıtım var mı?"

- **Evet** → canlı veriyle öğren (bugünkü davranış, bayt-aynı).
- **Hayır (ince veri)** → sırayla **shadow → backtest challenger → discovery shadow**'dan **AYRI KANALDA** kanıt çek. Kaynak damgalı (`kaynak: backtest` / `tf_blend_cf`), **gerçek ölçüm hücreleri KİRLENMEZ** (F5-1 `cf_by_tf` ilkesi — zaten kanıtlanmış desen).

**Tek owner switch'i:** `LEARNING_INCLUDE_SHADOW` (default OFF). Kapalıyken sistem bugünkü gibi yalnız canlı öğrenir; açıkken ince-veri boşluklarını shadow/backtest ile doldurur — **ama her zaman damgalı ve ayrı kanalda**, owner istediğinde kapatır.

**Bu tam da B-3/FAZ-4'te elle yaptığımın genellenmişi:** backtest quantum karnesi canlı FAZ-4'ün boş rejimlerini doldurabilir — ama kontrollü, damgalı, geri-alınabilir.

**Örnek senaryo:** FAZ-4 diyor ki "DEFENSIVE rejiminde canlı örnek yetersiz". Kaynak seçici backtest challenger'a uzanır (orada DEFENSIVE'de quantum DISCRIMINATES kanıtı VAR), bunu **damgalı destekleyici kanıt** olarak katar → olgunluk kapısı "artık yeterli" der → challenger ağırlık önerisi governor'a düşer. Owner onaylar. Hiçbir adım kör değil.

---

## 5. Otomasyon merdiveni — her öğrenici için 5 basamak

Her öğrenici standart bir merdivenden çıkar; hangi basamakta olduğu **kanıt otobüsünde görünür**:

| Basamak | Ne yapar | Güvenlik |
|---|---|---|
| **0 — Ölç** | kanıt üretir, karara bağlamaz | risksiz |
| **1 — Gölge** | canlıyla yan yana koşar, ayrımı ölçer | risksiz |
| **2 — Öner** | governor'a owner paketi | owner onayı |
| **3 — Dar-bant oto** | edge-gate + rollback ile küçük adım uygular | oto + geri-al |
| **4 — İzle** | watchdog + guard_safety; bozulursa geri al | oto-koruma |

**Kırmızı çizgiler (asla basamak 2'yi geçmez, owner şart):**
- **Yön motoru terfisi** (shadow zekânın canlı yönü belirlemesi — CP5)
- **Gerçek işlem/execution** (CP7)

Bu ikisi hariç her şey, kanıt olgunlaşınca **kendiliğinden** basamak çıkabilir — dar bant + rollback güvenlik ağıyla.

---

## 6. Somut yol haritası (fazlı, Anayasa'ya uygun)

Hepsi **additive · flag-OFF=bayt-aynı · shadow-önce · rollback'li · off-tick · ölü-kod-yok**.

| # | İş | Ne açar | Risk |
|---|---|---|---|
| **I1** | **Kanıt Otobüsü** — ortak kanıt kaydı + tek "Öğrenme Beyni" panel görünümü (mevcut ölçümleri tek şemaya topla) | "sistem neyi biliyor" tek yerden | 🟢 salt-gözlem |
| **I2** | **Olgunluk Kapısı** — edge+Wilson+min-örnek'i tek fonksiyona topla; trainer'lar buna geçsin | tutarlı kapı, tekrar yok | 🟢 refactor, bayt-aynı |
| **I3** | **Kaynak Seçici** — shadow/backtest blend kanalı (`LEARNING_INCLUDE_SHADOW`, damgalı, ayrı hücre) | **senin asıl isteğin** | 🟡 flag-OFF |
| **I4** | **Terfi Hattı** — 3 promotion kopyasını tek motora indir | yeni terfi = config | 🟢 refactor |
| **I5** | **İzleme kapsama** — her terfiye watchdog+rollback otomatik | izlemesiz canlı-dokunuş yok | 🟢 |
| **I6** | **Orkestrasyon paneli** — her öğrenici hangi basamakta, hangi kanıtla, sıradaki eşik ne | owner tek bakışta yönetir | 🟢 |

**Öneri sırası:** **I1 + I2 önce** (her şeyin altyapısı, ikisi de güvenli/gözlem-refactor). Sonra **I3** (shadow-dahil isteğini doğrudan verir). Sonra I4/I5/I6.

---

## 7. Riskler & pazarlıksız kurallar

- **Anayasa:** additive-only, flag-OFF bayt-aynı, shadow-önce ölç, her aktivasyona rollback, ölü kod yok, off-tick (tik ağırlaşmaz).
- **Kırmızı çizgiler:** yön motoru + execution owner onayı olmadan **asla** otomatik.
- **DATA_POLICY:** uydurma veri yok; shadow/backtest kanıtı **her zaman damgalı ve ayrı kanalda** — gerçek ölçüm hücrelerini kirletmez.
- **Geri-alınabilirlik:** her adım tek flag / tek revert ile geri alınır.

---

## 8. Sonuç — nereden başlamalı

Sistem parçalar hâlinde **zaten güçlü**; eksik olan **omurga**. En yüksek kaldıraç:

1. **I1 (Kanıt Otobüsü) + I2 (Olgunluk Kapısı)** — bunlar her öğreniciyi aynı dile getirir; ikisi de güvenli (gözlem + refactor, davranış değişmez).
2. **I3 (Kaynak Seçici)** — "shadow'u gerektiğinde dahil et" isteğini doğrudan, kontrollü ve geri-alınabilir biçimde karşılar.

Bundan sonrası (terfi hattı, izleme kapsama, orkestrasyon paneli) omurga kurulunca **hızlı ve düşük riskli** gelir.

> **Özet:** bugün 40+ ada var; hedef tek nehir. Nehir kurulunca her yeni öğrenici ve her shadow verisi otomatik akar — owner kırmızı çizgileri (yön + execution) sabit kalır.
