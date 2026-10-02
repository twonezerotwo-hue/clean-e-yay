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
