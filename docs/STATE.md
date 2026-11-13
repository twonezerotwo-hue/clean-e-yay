# STATE — Clean E-yAy bugün nasıl çalışıyor

Bu dosya yalnız **bugün doğru olanı** anlatır. Tarihçe `docs/archive/` altında.
Kural: buraya flag değeri, test sayısı gibi kendiliğinden eskiyen rakamlar
**kopyalanmaz**; nereden okunacağı yazılır.

## Sistem ne yapar

Paper-trading **karar-destek** sistemi. Gerçek emir yok, broker yok
(`PAPER_ONLY` / `NO_EXECUTION` yapısal). Karar deterministik koddur; LLM yalnız
anlatır. Ayrıntılı kurallar: [SAFETY_RULES](SAFETY_RULES.md), [DATA_POLICY](DATA_POLICY.md).

## Karar akışı (tek tick)

```
snapshot (fiyat + OHLCV + makro + haber, DQS)
  → rejim → 5 modül konsensüs (touche, fundamental, news, sentinel, quantum)
  → decide_matrix: sembol × TF hücreleri (15m, 1h, 4h, 1d, 1w)
      RiskGate ÖNCE (KILL_SWITCH / RISK_REDUCE / NO_POSITION_INCREASE)
      → giriş kalitesi v2 (yön ≠ giriş zamanlaması; yalnız kısıtlar: WAIT / boyut ↓;
        `active`'de birincil motor, teknik hatada legacy zincire düşer)
      → güven tabanı → EV kapısı → boyut katmanları → korelasyon/konsantrasyon
  → gates (seans, conflict gate) → attempt_open (fiyat bekçisi, duplicate, reentry)
  → paper lifecycle (SL/TP, kapanış-bazlı stop + acil fren, trailing, time-stop)
  → kapanış → decision_log → learning worker
```

## Giriş kalitesi v2 (yön ≠ giriş zamanlaması)

Konsensüs yönü korunur; "şimdi girmek mantıklı mı" ayrıca ölçülür (aralık konumu, ATR-normalize
uzama, RSI bandı, Bollinger, yaşa göre sönümlü dönüş olayları). Kötü giriş WAIT olur, **asla**
zıt yöne çevrilmez; boyut artmaz. Modu nereden okuyacağın: `config/thresholds_v1.0.yaml →
entry_quality_v2.mode`:

- `off` — hiçbir şey hesaplanmaz, karar bayt-aynı.
- `shadow` — eski (legacy) motor uygulanır; yeni motor yan yana yazılır, karar değişmez.
- `active` — **yeni motor birincil**; eski motor aynı turda gölge karşılaştırma + **teknik
  fallback**. LONG / SHORT / WAIT üçü de geçerli karardır: yeni motorun WAIT'i fallback
  değildir, legacy'nin LONG/SHORT'uyla ezilmez. Yalnız teknik başarısızlıkta (istisna, NaN/inf,
  bozuk karar, eksik bağlam, geçersiz eylem, gecikme aşımı) legacy karar uygulanır; RiskGate
  iki yolda da İLK sırada.

Canlı izleme: `GET /api/v1/decision/matrix` → üst düzey `engine` bloğu (yeni/legacy LONG-SHORT-WAIT
sayıları, uyuşmazlık %, giriş-kalitesi / dönüş-riski veto sayıları, fallback sayısı + sebepleri,
gate gecikmesi) ve hücre başına `entry_quality` (`applied_engine`, `fallback_reason`,
`legacy_*` / `new_*`, `agreement`). Normal şartlarda fallback sayısı 0'dır. Tasarım, ölçüm ve
geri alma: [ENTRY_QUALITY_V2](ENTRY_QUALITY_V2.md); kanıt: `docs/evidence/entry_quality_v2/`.

## Süreçler (gerçek topoloji)

| Ortam | Nasıl kalkar | Süreçler |
| --- | --- | --- |
| Lokal (Windows) | `scripts/local-autostart.ps1` keeper (20 sn'de bir sağlık) | `apps.supervisor` (127.0.0.1:9000), web (`next start` :4000), Ollama; ngrok tüneli varsa |
| AWS (EC2) | `main`'e merge → GitHub Actions → `scripts/deploy-from-github.sh` | `eyay-supervisor.service` (`apps.supervisor`), `eyay-web.service` |

İki ortam aynı şekilde çalışır (owner kararı): API, tick ve learning tek
`apps.supervisor` sürecinde. Tick ve learning ayrı thread'de koşar; event loop
yalnız HTTP'ye kalır. Tick, `tick_worker.lock` tekil-süreç kilidini alır: başka
bir tick yazarı canlıysa tick atlanır (log'da "tick atlandı"), API sürer.
Runtime durumu (`data/runtime/`) ortamlar arasında **paylaşılmaz**.

Tick zamanlaması (owner kararı 2026-10-06): `TICK_INTERVAL_SEC` (30) döngü
hedefidir; tick ondan uzun sürerse ardından yine en az 10 sn dinlenilir (tick ~34 sn
→ kararlar ~44 sn'de bir). Aşama süreleri her tick'te loglanır ("tick aşama süreleri").

YZ bütçesi (`LLM_DAILY_TOKEN_BUDGET`) yalnız ÜCRETLİ sağlayıcıları sınırlar: cevabı
yerel Ollama verdiyse sayılmaz. Bütçe dolunca zincirden yalnız ücretli sağlayıcılar
çıkar; yerel model varsa sohbet ve raporlar onunla sürer (Ollama modunda sohbet önce
Groq/OpenRouter'a gider — o kullanım sayılır).

## Konfigürasyon — tek kaynaklar

| Ne | Nereden okunur |
| --- | --- |
| Eşikler ve YAML flag'leri | `config/thresholds_v1.0.yaml` (git ile iki ortama taşınır) |
| Env flag'leri (AWS) | `scripts/deploy-from-github.sh` içindeki `ensure_env` / `set_env` satırları |
| Env flag'leri (lokal) | `.env` (gitignored); sapma kontrolü `scripts/flag-sync-check.sh` |
| Kodun okuduğu tüm env adları + türü | `packages/ops/env_registry.py` (test kayıtsız okumayı yakalar) |
| Aktif ağırlıklar | `config/weights_active.json` (git; owner onaylı, iki ortamda aynı). Oto-uygulama kapalı (`REBALANCE_AUTO_APPLY=1` ile açılır); git manifest'te oto-geri-alma devre dışı |
| API sözleşmesi | `contracts/openapi.yaml` → `make codegen`; sözleşme dışı borç `tests/contract/contractless_routes.txt` |

Bir flag'in açık olup olmadığını söylemeden önce bu dosyalara bak; dataclass
default'u (`= False`) çoğu zaman config'te ezilir.

## Risk frenleri (2026-10-02 itibarıyla)

| Olay | Aksiyon | Ne zaman kalkar |
| --- | --- | --- |
| Günlük zarar ≥ equity'nin %2'si | RISK_REDUCE: yeni pozisyon yok, açıklar kalır | UTC gün dönümünde kendiliğinden |
| Peak'ten düşüş ≥ %8 (MTM dahil) | KILL_SWITCH: tüm pozisyonlar kapanır | Yalnız owner reset (`POST /api/v1/risk/halts/reset`) |
| DQS < 55 | KILL_SWITCH (karar yok) | DQS düzelince |
| Açık pozisyon ≥ limit | NO_POSITION_INCREASE | Pozisyon azalınca |

## Takvim olayları

- **Önce:** `config/event_calendar.yaml` (elle tutulur) → `packages/risk/event_risk.py`:
  yüksek etkili olaydan 24 saat önce yeni pozisyon durur; açıklandıktan sonra
  `event_risk.post_release_cooldown_minutes` kadar daha durur. Saat takvimin
  `time` / `expectation` alanından ("08:30 ET"); yoksa 12:00 UTC varsayılır.
- **Sonra (salt-gözlem):** `packages/learning/event_outcomes.py` her tick'te olayı
  izler: açıklama öncesi fiyat tabanı, açıklamadan sonra doğrulanmış başlıklardan
  sonuç (zayıf/güçlü, soğuk/sıcak, güvercin/şahin), beklenen yön (`event_outcomes.
  expected_low`, faiz kanalı varsayımı) ve 15dk/1sa/4sa/1g gerçekleşen hareket.
  Gerçek açıklama saati takvimdeki `time` / `expectation` ("08:30 ET") alanından
  okunur. Bildirim, Olay Takvimi paneli, Brain brifingi ve sohbet bağlamı buradan
  beslenir (`GET /api/v1/calendar/event-outcomes`). Karara dokunmaz.

## Yazma anahtarı

`API_AUTH_TOKEN` tanımlıysa API tüm yazma isteklerini (sohbet, ses, işlem
butonları) Bearer token ister. Bu bilgisayarda (`localhost:4000`) panel anahtarı
sunucudan alır (`/api/local-auth`, keeper `WEB_LOCAL_WRITE_AUTH=1` verir); başka
yerden açılınca ilk 401'de bir kez sorar ve tarayıcıda saklar
(`apps/web/lib/api/writeAuth.ts`). AWS'te Cloudflare Worker parola kapısından
geçen isteğe anahtarı kendisi ekler.

## Stop davranışı

- SL bar **kapanışıyla** tetiklenir (fitil avına karşı). Bar pozisyondan önce
  kapanmışsa veya 2 TF süresinden bayatsa fitil davranışına düşülür.
- **Acil fren:** kapanış beklenirken fiyat açılış riskinin
  `exit_close_based_stop.disaster_mult` katına (bugün 2) ulaşırsa anında çıkılır.
- Yönetim tick'i önceki tick'e göre >%8 sıçrar ve sembolün OHLCV kapanışından
  >%10 saparsa o tick yok sayılır.

## Paper keşif açılışları

Keşif yolu 2026-11-10'da koddan çıktı (owner kararı, 8 Kasım). 2–21 Ekim
arasında güven/EV yumuşak kapılarında kalan adaylar küçük boyutla açılmıştı; bu
geçmiş pozisyonlar `exploration=true` damgalı kalır ve EXPLORATION kohortuna
düşer: yalnız güven kalibrasyonu (`calibration_trainer`, `tf_calibration`) bunları
kullanır, diğer öğreniciler dışarıda bırakır. Yeni açılışlar damga almaz.

## 4h yalnız bias (2026-11-10)

`timeframe_risk."4h".paper_execution: false` (owner kararı). Canlı 4h oyunun
(touche + sentinel + haber) yön bilgisi ölçülemedi: 16 sembol, 7.594 sinyalli
bar, maliyet sonrası sinyal başına −%0,22. 4h hücresi skor ve adayı üretir,
`timeframe_policy:no_paper_execution` ile bekler; stop/hedef planı karar kaydında
kalır ve kapı karşı-olgu defteri sonucunu yazar. Açık 4h pozisyonları normal
çıkış kurallarıyla kapanır. Geri açma: uzun veride ve ileri sınamada önceden
yazılı ölçütleri geçen yeni bir 4h yön kaynağıyla, owner onayıyla.

## Kesinti telafisi (2026-11-11)

Bilgisayar uyurken pozisyonu kimse izlemiyordu; uyanıştaki ilk tick o anki
fiyatla karar veriyordu (17 Ağu BTC: 56 sa kesinti → −8,04R). Artık her pozisyon
`marked_at` (son fiyatla yönetildiği an) taşır. Tick, bu andan sonra tamamen
kapanmış 15m/1h önbellek barlarını canlı sırayla oynatır (`lifecycle._replay_gap`):
acil fren → stop (TF kapanışı; yoksa fitil) → hedef → trailing, süre stopu bar
sınırında. Çıkış bar zamanı ve fiyatıyla yazılır, denetimde `GAP_REPLAY` satırı
kalır. Normal 30 sn tick'te arada tamamen kapanmış bar olmaz → davranış aynı.
Ölçüm (owner onaylı): sadakat sınırda (%80, ölçüm düzeltmesinden sonra), telafi
gerçeğe göre işlem başına ~+0,14R iyimser; tick fiyatı ile bar serisi bazı
sembollerde farklı (BRENT). Kök çözüm uykuyu önlemektir (kapak ayarı, owner).

## Günlük "neden kaçırdım" incelemesi (2026-11-13)

`packages/learning/daily_review.py` öğrenme döngüsünde günde bir kez (00:15 UTC sonrası
ilk koşu; yalnız dün, geriye dolum yok) dünün büyük hareketlerini (kendi 1h oynaklığına
göre |z| ≥ 1,5, en fazla 5) inceler: paper pozisyon yakalandı mı (kapanan işlemler
defteri + açık pozisyonlar; denetim kaydı değil — orada kapanışsız binlerce eski açılış
var), kaçırıldıysa o yönde aday kaç saat vardı ve hangi kapı durdurdu (karar kaydı
checkpoint + delta ile yeniden kurulur, ilk saat önceki günden tohumlanır), sembolün
başlık sayısı ve ortanca gecikmesi, sistemin kapalı kaldığı süre (karar kaydında 45 dk+
boşluk). Çıktı `data/runtime/daily_review/YYYY-MM-DD.json` + `review_recommendation`
bildirimi. Karara dokunmaz.

## Piyasa şoku bildirimi + şirket adı etiketi (2026-11-13)

`packages/notifications/market_shock.py` öğrenme döngüsünde (5 dk) son tamamlanmış 1h
barları tarar: sembolün kendi oynaklığına göre 1/3/6/24 saatlik hareket; ≥4 sembol
≥2,5σ ve ≥2 sınıf ya da tek sembol ≥5σ → owner'a "ne oldu, ilgili başlıklar, açık
pozisyon lehte/aleyhte, sistemin görüşü (aday + engel), risk seviyesi" bildirimi
(tip `event_outcome`; sözleşmede ayrı tip yok). 6 saat sembol soğuması
`data/runtime/market_shock_state.json`'da. Karara dokunmaz. Eşikler son 60 günde yalnız
sıklıkla seçildi (0,89/gün). Haber sınıflandırıcı kayıtlı sembollere şirket adı takma
adı uygular (`_COMPANY_ALIASES`: Nvidia/Jensen Huang → NVDA) ve adıyla anılan sembolü
4-etki sınırında genel sınıf eşleşmelerinin önüne koyar.

## Olay takvimi elle tutulur (son senkron 2026-11-13)

`config/event_calendar.yaml` olay riski kapısının tek doğrulanmış kaynağıdır:
kritik/yüksek etkili olaydan 24 saat önce ve 30 dakika sonra yeni pozisyon
açılmaz. Dosya Haziran'dan beri güncellenmemişti: Ekim CPI 12 Kasım yazıyordu
(gerçek 10 Kasım) → gerçek veri günü korumasız geçti, ertesi 24 saat boşuna
kapalı kaldı; Eylül CPI/PPI günleri de yanlıştı, Ekim ve Aralık FOMC ile Aralık
CPI/PPI hiç yoktu. 13 Kasım'da bütün günler bls.gov ve federalreserve.gov ile
karşılaştırıldı, 2027 sonuna kadar eklendi (2027 FOMC günleri Fed'de "geçici").
Koruma: `tests/unit/test_event_calendar.py` (aylık kapsama + düzeltilen günler +
kapının gerçek CPI gününde kapanması). Her senkronda bütün günler yeniden
karşılaştırılır; otomatik güncelleme yok.

## Ekran tick'in anını okur (2026-10-30)

Tick snapshot'ı kurunca `pipeline.publish_tick_snapshot` ile, karar matrisini
`decision.tick_artifact.publish` ile süreç içinde yayınlar. `get_cached_snapshot()`
(varsayılan sembol seti) taze tick snapshot'ını döner; cockpit, `/decision/matrix`,
brifing ve YZ bağlamı `decide_matrix_for` ile aynı snapshot için tick'in kararını
kullanır, kararı yeniden hesaplamaz. Tick 180 sn yayınlamazsa eski 30 sn'lik
stale-while-revalidate önbelleği devreye girer. Denetim zinciri: açılış/kapanış
denetim olayları ve `decision_log` kaydı aynı `audit_id`'yi taşır (snapshot, karar
ve sinyal kimliğinden türetilir).

Son kapı tek fonksiyondur (`packages/decision/final_gate.py::evaluate`). Sıra: yürütmeye
hazır (decide_matrix kapıları, RiskGate dahil) → teknik veri → teknik teyit (grup sayımı)
→ haber etkisi (çelişkide ×0,5; require modunda zorunlu) → seans + conflict gate rotası
(block / manual_ready / open). Tick her aday için bir kez çalıştırır ve sonucu
`tick_artifact.publish_final` ile yayınlar; `finalize_matrix_view` aynı snapshot için bu
sonucu gösterir, yayın yoksa aynı fonksiyonu hücre verisiyle çalıştırır (conflict gate ön
hesabı olmadan, fail-open). Owner onayına yönlenen hücre `OWNER_APPROVAL` görünür.

## Konsensüste eksik modül (owner kararı 2026-10-30)

`consensus.missing_module_policy: fixed` yalnız `E_YAY_CANONICAL_RUNTIME=1`
süreçlerde ve filigrandan sonraki snapshot'larda geçerli (pytest/golden altında
kapalı; lokal ve AWS deploy betiği ikisi de =1). Bilinçli oy dışı bırakmalar
(haber çekimserliği, quantum rejim kapısı, TF düşürme, kaynak kısıtı) eksik
SAYILMAZ, ağırlıkları kalanlara dağılır. Verisi gelmeyen modül kendi ağırlığıyla
nötr 50 sayılır ve hücre nötre zorlanır. Kapsama kapısı yönü nötre zorladıysa
karar `hold` olur (`coverage_gate:forced_neutral`). Bulgu: politika 30 Ekim
00:00 UTC'de bilinçli düşürmeleri de eksik sayıyordu; 80 hücre nötr, skorlar ayı
yönüne kaymış, "neutral signal" gerekçeli 5 short açılmıştı.

Teknik teyit (`technical_entry_gate`) farklı gösterge GRUBU sayar: momentum
(MACD histogramı + RSI), trend (EMA dizilimi), konum (VWAP). 15m/1h/1d iki grup,
4h üç grubun hepsini ister; yalnız momentumla geçilmez (owner kararı 2026-10-30).

## Dış kaynaklar, kotalar ve kanıt katmanı (owner kararı 2026-10-30)

Ücretsiz kotalar `packages/data/providers/quota.py` ile korunur (günlük/dakikalık
sayaç, `data/runtime/provider_quota.json`, UTC gün dönümü): CoinGecko 300/gün,
AlphaVantage 20/gün, TwelveData 700/gün 7/dk, Finnhub 50/dk, Tavily 30/gün. Sınır
doluysa çağrı yapılmaz; önbellek ya da zincirde sonraki kaynak kullanılır. CoinGecko
fiyatları tek istekte toplanır; BLS 6 saatte bir, Google News 10 dakikada bir sorulur.

Kripto barları: Kraken (BTC/ETH) → Binance spot (`EYAY_BINANCE_OHLCV_ENABLED`;
anahtarsız, kapanmış mumlar) → CoinGecko. Özel kripto varlıklar (DODO) Binance'ten.

Dış kanıt katmanı (`packages/data/providers/evidence`, öğrenme turunda kaynak başına
aralıkla): FRED kredi/stres/likidite serileri ve 14 günlük açıklama takvimi, Hazine
TGA, net likidite (Fed bilançosu − TGA − ters repo), CFTC COT, GDELT tonu,
Korku/Açgözlülük. `GET /api/v1/data/external-evidence`. **Karara girmez**
(`decision_usage: evidence_only`); rejim/konsensüse bağlanması ayrı owner kararı.

YZ anlatıcı modelleri: OpenRouter `google/gemma-4-31b-it:free`, Groq `openai/gpt-oss-120b`.

## Otomatik açılışta haber/dünya kurulumunun rolü

`news_prepared_setups.auto_open_mode` (`packages/paper/news_setup.py::auto_open_news_effect`,
tick'in tek çağrı noktası). Owner kararı 2026-10-30: **conflict_reduce** —

- Haber/dünya kurulumu yoksa nötr: teknik teyit + RiskGate + seans yolu aynen işler.
- Aday ile aynı varlık/TF'de TERS yönlü silahlı kurulum varsa boyut ×
  `conflict_size_multiplier` (0,5); 0 verilirse engeller.
- Aynı yönlü eşleşme yalnız kanıt kimliği olarak kaydedilir (`news_confluence:` etiketi);
  boyut büyütmez.

Gerekçe: 28–30 Ekim'deki `require` modu (aynı yönlü kurulum zorunlu) kanıtsızdı —
nedensellik kalibrasyonu `INSUFFICIENT` / `shadow_only`; haber öngörüsü karnesinde teyit
edilen adaylar %43, çelişenler %57 isabet (1 gün, 753 çözüm); kurulum yalnız XAU/BTC/ETH
için oluşuyor, 16 varlığın 13'ü otomatik açılamıyordu. `require` ve `shadow` modları
yapılandırmayla geri açılabilir.

## Öğrenme verisi hijyeni

- `outcomes.learning_grade()` öğrenicilerin tek süzgeci: legacy (regime=UNKNOWN),
  keşif (yalnız güven kalibrasyonuna girer) ve **execution_anomaly** dışarıda kalır.
- execution_anomaly (H7): temizlik öncesi çıkış mantığıyla (`Trade.exit_policy` < 2)
  kapanmış, -1.5R'den kötü SL kaybı. Düzeltilmiş mantıkla kapanan işlemler bu sınıfa
  hiç girmez. Kohort raporunda ayrı kolon; P3 son-performans freni de bunları saymaz.
- Yeni karar damgası taşıyan işlemlerde snapshot, fingerprint, DQS, risk aksiyonu ve
  açılış nedeni zorunludur. Eksik atıf işlemi kapatmayı durdurmaz; kayıt raporda kalır,
  fakat `learning_grade()` ve premium `performance` özeti bu işlemi öğrenme kanıtından
  ayırır. Ham metrikler şeffaflık için ayrıca korunur.

## Keşif & Fikir Panosu (salt-gözlem)

Learning worker her turda (`discovery.scan_enabled()`) dört adım koşar;
hiçbiri işlem açmaz, işlem evrenine varlık eklemez, RiskGate'e dokunmaz:

0. **Haber güdümlü keşif** (`packages/discovery/news_discovery.py`): tüm RSS akışı
   (piyasa + jeopolitik + `news_discovery.extra_feeds` konu kaynakları; 15 dk'da bir,
   kaynak başına 15 başlık) her turda 15'lik gruplar halinde yerel YZ'ye (yalnız Ollama,
   JSON modu; ortak LLM bütçesini harcamaz, günde en çok 300 çağrı) sorulur: fiyatı
   gerçekten etkileyecek olay → sonuç → etkilenen işlem gören varlıklar (hisse, ETF,
   vadeli, kripto, döviz; yön + güven). Önerilen sembol Yahoo'da doğrulanır (var mı, tür,
   ad örtüşmesi, ≥31 günlük geçmiş, hisse/ETF/kripto ≥5 M$ günlük hacim; tutmazsa adla
   aranır); elenenler nedeniyle sayılır. Kayıtlı varlığa denk gelen sonuç aday olmaz, o
   varlığın haber öngörüsüne kanıt olur. Doğrulanan adaylar 72 saatlik deftere
   (`NEWS_DISCOVERY_PATH`) yazılır; yukarı yönlüler tarayıcının `news` evrenine girer
   (taze sonucu olmayan turda 2'ye kadar öncelikli). Yerel model yoksa (AWS)
   `LOCAL_LLM_OFF`.
1. **Keşif + teknik analiz** (`packages/discovery/scanner.py`): kripto momentum kısa
   listesi, yükselen sektör ETF'leri ve emtia kısa listesi (`config/discovery.yaml`
   `commodities`, Yahoo vadeli/ETF; 30g/7g momentum) aynı teknik motordan geçer.
   TF başına kompakt teknik özet (`ta`: eğilim, trend/ADX, destek/direnç, formasyon,
   teyit, Fibonacci) artifact'a yazılır; gölge karne `shadow_ledger`'da.
2. **Haber öngörüsü** (`packages/discovery/news_forecast.py`): son snapshot başlıkları
   + sınırlı Tavily araması (turda en çok 5 varlık, varlık başına 6 saatte bir)
   72 saatlik deftere girer; kelime-sınırıyla eşlenir, yön E2 mantığıyla okunur,
   kaynak isabet karnesi ve tazelikle ağırlıklanır. Her öngörü fiyatıyla
   `NEWS_FORECAST_LEDGER_PATH`'e yazılır ve 4sa/1g/3g sonra çözülür (öngörü karnesi).
3. **Fikirler** (`packages/discovery/ideas.py`): teknik sinyal veren veya güçlü yukarı
   haber öngörüsü olan keşif adayları şeffaf skorla (teknik ≤40 + karne ≤25 + haber
   ± − risk cezası) sıralanır. İlk 5 fikir yalnız yerel modele (`get_local_client()`,
   Ollama `OLLAMA_MODEL`; uzak sağlayıcıya düşmez, ortak LLM bütçesine yazılmaz)
   "fikir eleştirmeni" olarak sorulur: HÜKÜM (GÜÇLÜ/İZLE/ZAYIF), tez, lehte/aleyhte,
   riskler. Turda en çok 2 çağrı; dosya değişmedikçe 12 saat önbellek; yerel model
   yoksa (AWS) deterministik değerlendirme. Sonuç `IDEA_BOARD_PATH`
   (`data/runtime/idea_board.json`).

Haber öngörüsü YZ'nin bir varlığa bağladığı başlığı o varlık için doğrudan kanıt sayar
(güvenle ağırlıklı); fikir kartı ve YZ değerlendirme dosyası "başlık → sonuç → yön"
zincirini taşır.

Okuma (owner kararı 2026-10-05, üçüncü tur — ayrı panel YOK):
- **YZ yorumları:** sıkıştırılmış durum bağlamındaki `news_intel` bölümü
  (`packages/discovery/intel.py`: kayıtlı varlık haber öngörüleri, haber zincirleri,
  inceleme tavsiyeleri, canlı aday × haber teyit/çelişki, gölge karnesi, ilk 3 fikir;
  güç 10'luk kovalarla). Persona raporları (Analist teyit/çelişkiyi ve inceleme
  tavsiyelerini, Risk Officer çelişkiyi itiraz olarak, Makro zincirleri senaryoya
  katar; kanıt satırları koddan), sohbet ve Brain brifingi aynı bölümü görür.
- **İnceleme tavsiyesi bildirimi:** haberden bulunmuş fikir + haber öngörüsü yukarı
  (güç ≥ `review.min_news_strength`) + teknik `WOULD_OPEN_LONG` → `review_recommendation`
  (zil + anlık uyarı; varlık başına 24 saatte bir; işlem önerisi değildir).
- **Gölge karar girdisi** (`packages/discovery/news_decision_shadow.py`) tarihsel
  artifact'ları okuyabilir; yeni runtime yazımı kapalıdır. Haber–teknik kararın
  aktif yolu yalnız canonical `decide_matrix` + RiskGate'tir. Eski kayıtlar
  silinmez, fakat yeni karara veya öğrenme hesabına girmez.
- Ham veri: `GET /api/v1/ideas`. Dünya Özeti'nin detayı Soul katmanında.
- **Owner onaylı paper açma (Brain bannerı):** Brain'de hologramın altındaki "Yeni Asset Fikri"
  bannerı Heart panelindeki fikirleri (`useIdeas()`) 3 sn arayla sırayla gösterir (üzerine gelince/eylemden sonra durur); `ONAYLA ve KAĞIT İŞLEMİ AÇ`
  yalnız paper pozisyon açar (`POST /api/v1/paper-trading/ideas/{symbol}/open`,
  `packages/paper/idea_order.py` → `manual_order.place`). RiskGate, günlük zarar, max pozisyon,
  aynı sembolde açık pozisyon ve sinyal süresi kilit içinde yeniden doğrulanır; engel varsa emir
  yok, gerçek neden döner. Pozisyon `open_reason=owner_idea` (öğrenmede MANUAL kohort). Canlı
  fiyat kaynağı olmayan fikir açılamaz (`DATA_UNAVAILABLE`). Karar motorunu etkilemez.
YZ hükmü governor terfi paketine yalnız **kanıt** olarak eklenir; terfi kriterleri
deterministik kalır ve owner onayı şarttır (CP5).

## Doğrulama (her değişiklikte)

```
pytest -q                                      # birim + sözleşme + golden
python -m tests.golden.golden_replay --check   # canlı config ile karar matrisi bayt-aynı mı
ruff check packages apps/api apps/tick_worker apps/learning_worker apps/supervisor
python scripts/codegen.py --check              # openapi → TS
cd apps/web && pnpm exec tsc --noEmit && pnpm build
make smoke                                     # çalışan API gerekir
```

Test koşusu ağa çıkamaz (H14) ve canlı `data/runtime/`'a yazamaz (H17); ikisi de
conftest'teki audit hook ile zorlanır.

Golden replay farkı = davranış değişti. Bilinçli bir mantık düzeltmesiyse fark
PR açıklamasına yazılır ve `--write` ile golden güncellenir.

## Nerede ne var

- Mimari derinlik: [ARCHITECTURE.md](../ARCHITECTURE.md)
- İleriye dönük iş ve açık owner kararları: [ROADMAP.md](ROADMAP.md)
- Frontend kuralları: [DASHBOARD_RULES.md](DASHBOARD_RULES.md)
- Teknik analiz spesifikasyonu: [TECHNICAL_ANALYSIS_SPEC.md](TECHNICAL_ANALYSIS_SPEC.md)
- Dünya durumu / nedensellik (gölge): [WORLD_STATE_CAUSAL_BACKEND_REPORT.md](WORLD_STATE_CAUSAL_BACKEND_REPORT.md)
- Eski yol haritaları, spec v2.3, görev kayıtları: [archive/](archive/)
