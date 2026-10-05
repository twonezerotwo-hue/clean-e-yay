# STATE — Clean E-yAy bugün nasıl çalışıyor

Bu dosya yalnız **bugün doğru olanı** anlatır. Tarihçe `docs/archive/` altında.
Kural: buraya flag değeri, test sayısı gibi kendiliğinden eskiyen rakamlar
**kopyalanmaz**; nereden okunacağı yazılır.

## Sistem ne yapar

Paper-trading **karar-destek** sistemi. Gerçek emir yok, broker yok
(`PAPER_ONLY` / `NO_EXECUTION` yapısal). Karar deterministik koddur; LLM yalnız
anlatır. Ayrıntılı kurallar: [SAFETY_RULES](SAFETY_RULES.md), [DATA_POLICY](DATA_POLICY.md).

## Karar akışı (tek tick, ~30 sn)

```
snapshot (fiyat + OHLCV + makro + haber, DQS)
  → rejim → 5 modül konsensüs (touche, fundamental, news, sentinel, quantum)
  → decide_matrix: sembol × TF hücreleri (15m, 1h, 4h, 1d, 1w)
      RiskGate ÖNCE (KILL_SWITCH / RISK_REDUCE / NO_POSITION_INCREASE)
      → güven tabanı → EV kapısı → boyut katmanları → korelasyon/konsantrasyon
  → gates (seans, conflict gate) → attempt_open (fiyat bekçisi, duplicate, reentry)
  → paper lifecycle (SL/TP, kapanış-bazlı stop + acil fren, trailing, time-stop)
  → kapanış → decision_log → learning worker
```

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

`paper_trading.paper_auto_open` açık (owner kararı K1): güven/EV yumuşak
kapılarında kalan aday küçük boyutla açılabilir. Bu pozisyonlar
`exploration=true` damgalanır ve `decision_log`'a kapı listesiyle (`blocked_by`)
yazılır ve EXPLORATION kohortuna düşer: yalnız güven kalibrasyonu (`calibration_trainer`, `tf_calibration`) bunları kullanır, diğer öğreniciler dışarıda bırakır.

## Öğrenme verisi hijyeni

- `outcomes.learning_grade()` öğrenicilerin tek süzgeci: legacy (regime=UNKNOWN),
  keşif (yalnız güven kalibrasyonuna girer) ve **execution_anomaly** dışarıda kalır.
- execution_anomaly (H7): temizlik öncesi çıkış mantığıyla (`Trade.exit_policy` < 2)
  kapanmış, -1.5R'den kötü SL kaybı. Düzeltilmiş mantıkla kapanan işlemler bu sınıfa
  hiç girmez. Kohort raporunda ayrı kolon; P3 son-performans freni de bunları saymaz.

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
   ± − risk cezası) sıralanır. İlk 5 fikir yerel LLM'e (`get_client()`, Ollama
   `OLLAMA_MODEL`) "fikir eleştirmeni" olarak sorulur: HÜKÜM (GÜÇLÜ/İZLE/ZAYIF), tez,
   lehte/aleyhte, riskler. Turda en çok 2 çağrı; dosya değişmedikçe 12 saat önbellek;
   LLM yoksa deterministik değerlendirme. Sonuç `IDEA_BOARD_PATH`
   (`data/runtime/idea_board.json`).

Haber öngörüsü YZ'nin bir varlığa bağladığı başlığı o varlık için doğrudan kanıt sayar
(güvenle ağırlıklı); fikir kartı ve YZ değerlendirme dosyası "başlık → sonuç → yön"
zincirini taşır.

Okuma: `GET /api/v1/ideas` → Heart "Fikirler" sekmesi (başta Dünya Özeti satırı ve
"Haber akışından keşif", altta katlanır "Haber kaynaklı hazır pozisyonlar"; Dünya
Özeti'nin detayı Soul katmanında); sohbet bağlamında ilk 3 fikir.
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
