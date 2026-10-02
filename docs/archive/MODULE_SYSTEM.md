# Modül Sistemi - Şu An vs Hedef

**Tarih:** 2026-07-05  
**Kapsam:** Modül oyları, rejim ağırlıkları, zaman dilimi etkisi, touche iç sinyalleri  
**Amaç:** Sistemin yön kararını nasıl ürettiğini ve hangi dönüşüm hattının izleneceğini kalıcı bir referans haline getirmek.

---

## 0. Tek cümlede

5 modül piyasaya bakıp birer yön oyu verir; oylar rejime göre ağırlıklanıp birleşir; tek yön kararı çıkar. Kök sorun, ağırlıkların bağlamı, özellikle zaman dilimini, yeterince görmemesidir. Bu yüzden en güçlü modüle yanlış yerde fazla güvenilebiliyor.

---

## 1. Beş modülün bugünkü rolü

| Modül | Ne okur | Yaklaşık ağırlık | Ayrışım | Puan | Ana sorun |
|---|---|---:|---:|---:|---|
| `touche` | RSI/MACD/EMA + fib/S-R/pattern/hacim | %40 | -1.03 | 4/10 | Yön sürücüsü ama kazananı ayıramıyor |
| `quantum` | Sektör rotasyonu / piyasa hali | %10-15 | -0.34 | 4/10 | Çıktısı neredeyse sabit, ölü yük |
| `sentinel` | VIX + vol + squeeze + opsiyon | %10-25 | +0.63 | 7/10 | Sağlam v2 sinyal |
| `fundamental` | Makro / değerleme | %15-20 | +0.61 | 7/10 | Sağlam v2 sinyal |
| `news` | 28 haber feed'i / sentiment | %15 | +0.33 | 5/10 | Sinyal cılız |

Birleşim modeli:

1. Her modül 0-100 yön skoru üretir; `50` nötrdür.
2. Skor, rejime özel ağırlıkla çarpılır. Örnek: `touche` OFFENSIVE rejimde yaklaşık %45, `sentinel` CRISIS rejimde yaklaşık %45 alır.
3. Modül oyları toplanır.
4. Ayrı bir TF ağırlığı swing/intraday/scalp bağlamında `d1`, `h4`, `h1`, `m15` sinyallerini harmanlar.

Bugünkü eksik: modül ağırlığı rejimi görür, ama modülün o zaman diliminde gerçekten iyi olup olmadığını görmez.

---

## 2. `touche` modülünün iç yapısı

`touche` tek parça değildir. İki eksenden oluşur:

```text
touche = momentum omurgası x tilt katmanı
```

### 2.1 Momentum omurgası

Momentum yönü belirler.

| Alt sinyal | Ağırlık | 15m | 1h | 4h | 1d |
|---|---:|---|---|---|---|
| `trend` / EMA | 0.40 | düz | düz | edge var | edge var |
| `rsi` | 0.30 | düz | düz | edge var | edge var |
| `macd` | 0.30 | düz | düz | düz | ölü |

Ölçüm sonucu: 4h/1d tarafında trend ve RSI daha anlamlı; 15m/1h tarafında aynı yön mantığı gürültü üretiyor. MACD ise mevcut haliyle her TF'de zayıf.

### 2.2 Tilt katmanı

Tilt yönü kurmaz; kanaati ve risk iştahını düzeltir. Temel görevi yanlış yerde pozisyon alma davranışını frenlemektir.

| Kanat | Ağırlık | Durum |
|---|---:|---|
| `location` = fibonacci + S/R | 0.60 | Fibonacci canlı; S/R rafinesi kapalı |
| `pattern` | 0.25 | canlı |
| `volume` | 0.15 | canlı |
| `elliott` | bağlı değil | kod var, panelde görünüyor, karara bağlı değil |

Tilt asimetriktir:

- Uyumluysa yaklaşık `+%15` katkı verir.
- Çelişkiliyse yaklaşık `-%40` ceza verir.

Bu asimetri özellikle dirençten yukarı alma gibi kötü konumlanmaları sert cezalandırmak içindir.

---

## 3. Ölçülmüş kök sorunlar

1. Ağırlıklar sadece rejime göre değişiyor; zaman dilimine göre yetkinlik görmüyor. `touche` 15m'de de yüksek ağırlık alıyor, ama bu bağlamda gürültülü. Ölçülen `-$869` kaybın ana sebebi bu.
2. `macd` mevcut formuyla her TF'de ölü ya da çok zayıf. Sabit `%30` momentum payı boşa gidiyor.
3. `quantum` neredeyse sabit çıktı üretiyor. Esas ayrıştığı yer DEFENSIVE rejim; canlıda çoğu zaman OFFENSIVE rejimde ölü yük gibi davranıyor.
4. Tilt katmanı, yani fib/S-R/pattern/volume, henüz aynı disiplinle ölçülmedi. Değeri bilinmiyor.
5. Elliott sinyali yazılı ama karar hattına bağlı değil. Potansiyeli var, ancak önce ölçülmeli.

---

## 4. Hedef dönüşüm

| Bugün | Hedef |
|---|---|
| Ağırlık rejime duyarlı ama TF-kör | Ağırlık rejim x TF x kanıtlanmış yetkinlik ile belirlenir |
| `touche` her TF'de aynı trend mantığını kullanır | 4h/1d trend motoru; 15m/1h ortalamaya dönüş ve üst-TF zamanlama katmanı olur |
| RSI her TF'de yön-lean üretir | RSI yüksek TF'de yön teyidi, düşük TF'de aşırılık/dönüş sinyali olarak kullanılır |
| MACD sabit `%30` alır | MACD ölçülür; gerekirse kısılır, onarılır veya divergence tabanlı kullanıma döner |
| `quantum` her zaman konuşur | Yetkinlik kapısı gelir; sadece ayrıştığı bağlamda oy verir, yoksa susar |
| Fib/S-R/pattern ölçülmemiştir | Her TF'de edge'i ölçülür; değer verenler tutulur, vermeyenler kısılır |
| Elliott raftadır | Ölçülür; 4h/1d'de değer veriyorsa flag ile açılır |
| Sabit el ayarı ağırlıklar vardır | Backtest ve canlı shadow verisinden öğrenilen ağırlıklar kullanılır |

---

## 5. Temel ilke

Her modül ve alt sinyal, ağırlığını bulunduğu bağlamda, yani TF + rejim kesişiminde ölçülmüş edge'iyle hak etmelidir.

Bu dönüşümde sabit sayı ve lore yoktur:

- Önce backtest ile ölçülür.
- Sonra flag-OFF ve shadow modunda denenir.
- Kanıt varsa owner onayıyla açılır.
- Rollback yolu olmadan canlı davranış değiştirilmez.

Kırmızı çizgi: modüllerin beyni yeniden yazılmaz. İlk dönüşüm sadece hangi modülün, hangi bağlamda, ne kadar dinleneceğini öğrenir.

---

## 6. Yolculukta mevcut konum

Tamamlanan:

- Faz A ölçüm motoru kuruldu.
- `touche` momentum'u TF bazında ölçüldü.
- Canlı karar hattına sıfır dokunuş yapıldı.
- 1572 test yeşil kaldı.

Sıradaki:

1. Tilt katmanı ölçülecek: fib, S/R, pattern, volume.
2. `quantum` aynı yetkinlik mantığıyla ölçülecek.
3. TF bazında öğrenilen ağırlık modeli flag-OFF ve shadow-önce şekilde hazırlanacak.

Korunan güvenlik çizgisi:

- Additive ilerleme.
- Kanıtsız canlı davranış değişikliği yok.
- Flag-OFF varsayılanı.
- Shadow-önce deneme.
- Owner onayı.
- Rollback hazır olmadan aktivasyon yok.

---

## 7. Karar hattı için çalışma hipotezleri

Bu referans, sonraki ölçümlerde test edilecek hipotezleri de sabitler:

1. `touche` yüksek TF'de trend motoru olarak değer üretiyor.
2. `touche` düşük TF'de aynı trend yaklaşımıyla gürültü üretiyor; burada ortalamaya dönüş veya üst-TF zamanlama daha uygun olabilir.
3. `macd` mevcut formuyla momentum omurgasından kısılmalı veya yeniden tanımlanmalı.
4. `quantum` sadece ayrışabildiği rejimde oy vermeli.
5. Tilt katmanı gerçekten para koruyorsa, özellikle kötü lokasyonda girişleri azaltarak değer üretmelidir.
6. Elliott karara bağlanmadan önce 4h/1d bağlamında shadow ölçümden geçmelidir.

