# Denetim Yol Haritası — Kodlama Süreci

> 2026-07-02 tam-repo denetiminin bulgularını sıralı, güvenli bir kodlama
> sürecine çevirir. **Yaşayan belge** — her slice tamamlanınca durum sütunu
> güncellenir. Kaynak denetim raporu: PR #48 açıklaması + oturum kaydı.

## 16 KATEGORİ → 10/10 YOL HARİTASI (2026-07-04, owner talimatı)

> Owner talimatı: 2026-07-04 denetim raporundaki 16 puanlı kategorinin HER
> BİRİNİ 10/10'a taşıyacak fazlı plan. Kural 1 (sistem bozulmaz), Kural 2
> (ölü kod / şişmiş mimari yok), Kural 3 (harcanan her token sistemi iyiye
> götürür). **Token biterse başka asistan bu tablodan sıfır bağlamla devralır.**
> S serisi (aşağıda) bu planın FAZ-1'idir ve çoğu KODLANDI (2026-07-04).
>
> Faz sırası neden böyle: önce HIZ (her deneyi hızlandırır, davranış-nötr) →
> sonra AKTİVASYON (kanıtı hazır kapalı özellikler) → sonra ÇIKIŞ kalitesi
> (en büyük $ kaçağı ama kanıt biriktirmeli) → sonra SİNYAL kalitesi (skorlar
> iyi/kötü işlemi ayırsın) → en son OTONOMİ (kırmızı çizgi).

| Kat | Bugün | Hedef | 10/10 için gereken (faz) | Durum |
|---|---:|---:|---|---|
| 14 Hız | 5 | 10 | **FAZ-1:** S1-1 GDELT cooldown + S1-2 log rotasyon + S1-3 TF memo (tik 22s→~3s ölçüldü). **FAZ-1b (kalırsa):** snapshot pool'a technicals paralel (şu an seri 1.3s) — ölçülen kazanç küçük, ertelenebilir | ✅ FAZ-1 kodlandı (S1) |
| 13 Gölge sistem | 7 | 10 | S1-2 (221MB log → tail+rotasyon) + tek-kurulum (S1-3). 10/10 = F5-2 terfi paketi READY olunca gölgenin haklılığı ölçülüp owner'a sunulur (mekanizma hazır, veri birikmeli: ≥200 eşleşme + 30 çözüm) | ✅ FAZ-1 (S1-2/3); terfi veri-bekliyor |
| 9 EV kapısı | 5 | 10 | **FAZ-2:** S3-1 empirical_pwin AÇIK → p(win) şişik güvenden değil gerçekleşen isabetten. 10/10 = payoff_weighted'ın R-verisi birikince devreye girmesi (min_r_samples=8; şu an en dolu hücre 7) — R-damgalı kapanışlar biriktikçe DOĞAL dolar | ✅ FAZ-2 (S3-1); R-verisi birikiyor |
| 4 Haber | 6 | 10 | S1-1 GDELT dürüst degraded (tek kanala düşüş görünür). 10/10 = ek doğrulanmış haber kaynağı (RSS feed genişletme) VEYA GDELT'e alternatif erişim — **YENİ İŞ, henüz planlanmadı** (owner ağ-erişim kararı: bu makineden GDELT/Deribit bloklu; **2026-07-04 probe: AWS'ten de 429 rate-limit — AWS-taraflı çekim çözüm değil, alternatif kaynak şart**). **2026-07-04 RSS genişletme YAPILDI (owner kararı):** +6 market feed (The Block, CryptoSlate, Bitcoin.com, Yahoo Finance, MarketWatch Top, Gold Wire — XAU/XAG metal kanalı ilk kez) + 2 geo (Guardian, France24); 15 aday canlı test edildi, çalışmayan 7'si ELENDİ (DATA_POLICY); fetch havuzu 6→10 worker (soğuk yenileme 2 turda, S1 hız kazanımı korunur). **AWS'te canlı DOĞRULANDI (deploy 40085c27 + EC2 probe PR #55):** yeni kaynaklar snapshot'ta (Yahoo Finance 3, Bitcoin.com 2, CryptoSlate 1 başlık), kararlı tik 4.8–6.8s — hız regresyonu yok | 🔶 RSS ✅ canlı; GDELT ölü |
| 1 Veri toplama | 7 | 10 | Haber (kat 4) + S1-4 opsiyonel-sağlayıcı ayrımı (gerçek arıza görünür). 10/10 = options ETH/BTC erişimi (Deribit bloklu) için fallback veya AWS-taraflı çekim; N1 ile aynı ağ-erişim kararı. **2026-07-04 probe: Deribit AWS'ten OK — canlıda zaten besleniyor, blok yalnız lokal; kalan iş yalnız haber (kat 4)** | 🔶 options ✅; haber N1 |
| 11 ÇIKIŞLAR | 4 | 10 | **FAZ-3 (en büyük $ kaçağı ~$2.4k):** partial_tp shadow kanıtı birikince AÇ (şu an n=2 uplift −$16, YETERSİZ — 🔴 kural). Yardımcı: TF_TARGET_TRAIL_AUTOTUNE zaten AÇIK (trailing mesafesini capture'dan öğrenir). 10/10 = partial_tp AÇIK + EXIT_FORENSICS_NUDGE AÇIK (oransal düzeltme) | ⏳ FAZ-3 kanıt-bekliyor |
| 7 Konsensüs+ağırlık | 6 | 10 | **FAZ-4 (sinyal kalitesi):** skorlar iyi/kötü işlemi ayıramıyor (katkı kazanan≈kaybeden). WEIGHT_REGIME_FILTER (rejim-bazlı eğitim) + MISTAKE_MEMORY_V2 (Wilson-sınırlı hata hafızası) AÇ. 10/10 = ağırlık trainer'ın rejim-ayrık öğrenmesi + kalite ayrımı ölçülür. **✅ ÖLÇÜM DİLİMİ KODLANDI (2026-07-05): `signal_quality.py` rejim başına modül ayrım karnesi (module_attribution'ın rejim-ayrık+hükümlü hâli: separation + rel_separation + DISCRIMINATES/INVERSE/FLAT/INSUFFICIENT); learning summary'ye bağlı (salt-gözlem). CANLI BULGU: 155 outcome, NEUTRAL 17/14 → TÜM modüller FLAT (hiçbiri ayırmıyor; quantum rel −0.049 ~ters, B-3 backtest INVERSE'iyle çapraz tutarlı), diğer rejimler örnek-yetersiz → aktivasyon şimdi fayda getirmez (kanıt kapısı çalışıyor). 6 test.** İki flag (WEIGHT_REGIME_FILTER/MISTAKE_MEMORY_V2) zaten kodlu+testli+watchdog'lu — aktivasyon owner+kanıt kapılı (kanıt: henüz FLAT) | 🔶 ölçüm ✅; aktivasyon kanıt-bekliyor |
| 6 Quantum | 6 | 10 | FAZ-4 kapsamında: ağırlık trainer quantum'un gerçek katkısını ölçüp ağırlığını rejim-bazlı ayarlar (şu an sabit ~%10-15). 10/10 = etkisi veriyle doğrulanmış ağırlık | ⬜ FAZ-4 |
| 3 Makro (fundamental) | 7 | 10 | Çifte-sayım çözüldü (v2 AÇIK). 10/10 = FRED kesintisinde katman-düşürme (regime.drop_unavailable_layers AÇIK) + makro veri kanıtının ağırlıkta ölçülmesi (FAZ-4) | 🔶 büyük kısmı AÇIK |
| 5 Sentinel | 7 | 10 | Çok-girdili kompozit AÇIK (v2). 10/10 = options-stres girdisi gerçek Deribit verisiyle (şu an bloklu → N1); kompozit tam beslenince. **2026-07-04 probe: Deribit AWS'ten OK (200) — canlı kompozit options-stres girdisini alıyor; blok yalnız lokal makinede** | 🔶 canlıda besleniyor |
| 2 Teknik (touche) | 8 | 10 | **FAZ-5:** T-1 htf_alignment AÇIK (S3-2). Kalan T-2 (Elliott×Fib), T-3 (S/R gücü), T-4 (mum teyidi) shadow kanıtı birikince tek tek AÇ. 10/10 = dördü de aktif + kanıtla doğrulanmış | 🔶 T-1 AÇIK; T-2/3/4 shadow |
| 8 Kalibrasyon | 8 | 10 | tf_platt AÇIK + guardrail sıkı (0.10). 10/10 = reliability_bins çifte-sayım fix (denetim bulgusu #3) + TF başına yeterli örnekle fit doğrulanır. **2026-07-04 teyit: çifte-sayım fix ZATEN main'de (d52d44fd, owner onayı 2026-07-02, `test_reliability_bins_no_double_count` yeşil) — kalan yalnız veri birikimi** | 🔶 fix ✅; veri birikiyor |
| 12 Öğrenme | 8 | 10 | Kanıt üreten ama karara bağlanmamış flag'ler açıldıkça (empirical_pwin ✅, MM_V2, WRF). 10/10 = tüm öğrenme kanıtı ya karara bağlı ya bilinçli-shadow, boşta kanıt yok | 🔶 aktivasyonlarla |
| 10 Risk kapıları | 9 | 10 | Zaten en güçlü. 10/10 = S2-1/S3-3 MTM gate (açık pozisyon eriyince realized beklemeden fren) — bu bağlanınca risk gerçek-zamanlı olur | ✅ S2-1 kodlandı; S3-3 flip sırada |
| 15 Panolar | 8 | 10 | 40+ panel. 10/10 = degraded_reasons (S1-4) + coverage çipleri panele yansıtılır (küçük FE işi) | 🔶 BE hazır, FE dokunuşu |
| 16 Güvenlik ağı | 9 | 10 | 1433 test, watchdog, rollback. 10/10 = zaten neredeyse tam; her yeni aktivasyona watchdog+rollback (S serisi bunu korudu) | ✅ korunuyor |

**Bu sprintte KODLANAN (FAZ-1 + FAZ-2 kısmı):** kat 14/13/9/10 doğrudan
ilerledi; 2/3/5/12 kısmen. **Kalan işler (ayrı fazlar, henüz kodlanmadı):**

- **N1 — Ağ/veri erişimi (kat 1/4/5):** GDELT + Deribit bu makineden bloklu.
  Owner kararı gerekli: (a) AWS-tarafı erişim var mı test et (AWS farklı IP),
  (b) yoksa alternatif haber/options kaynağı planla. YENİ İŞ — kod öncesi
  owner ağ-erişim teyidi şart (uydurma veri YASAK — DATA_POLICY).
  **TEST EDİLDİ (2026-07-04, EC2 probe — PR #54, merge edilmeden kapatıldı):**
  (1) **Deribit AWS'ten SORUNSUZ** — 200/0.1s, gerçek opsiyon zinciri; canlı
  tick worker `degraded_reasons`'ta yalnız gdelt var → options canlıda ZATEN
  besleniyor, kat 1/5 için AWS-taraflı ek iş GEREKMİYOR (blok yalnız lokal
  makinede). (2) **GDELT AWS'ten de fiilen erişilemez** — SSL bloğu yok ama
  her istek 429 rate-limit (~8-10s; GDELT AWS IP aralıklarını kısıyor), canlı
  worker da `degraded:gdelt`. Sonuç: kat 4 için AWS-taraflı çekim ÇÖZÜM DEĞİL;
  alternatif haber kaynağı (RSS genişletme vb.) owner kararı bekliyor.
- **FAZ-3 — Çıkış kalitesi (kat 11):** partial_tp shadow uplift kanıtı ≥N
  işlem birikince owner onayıyla AÇ. En büyük $ kaçağı ama 🔴 kanıtsız açılmaz.
- **FAZ-4 — Sinyal kalitesi (kat 6/7):** WEIGHT_REGIME_FILTER +
  MISTAKE_MEMORY_V2 tek tek (bekleme penceresiyle). Skorların iyi/kötü
  ayrımını ölçmek için modül-katkı analizi (rapor madde 4.5) izlenmeli.
  **✅ ÖLÇÜM DİLİMİ (2026-07-05): `signal_quality.regime_module_scorecard`
  bunu somutlaştırdı — canlı 155 outcome'da NEUTRAL modülleri hep FLAT (ayrım
  yok) → aktivasyon HENÜZ kanıtsız. Kalan: örnek birikince (DEFENSIVE/OFFENSIVE)
  yeniden ölç; bir modül DISCRIMINATES olursa flag'i owner onayıyla aç.**
- **FAZ-5 — TA genişletme (kat 2):** T-2/T-3/T-4 shadow kanıtı sırayla.
- **Küçük fix'ler:** ~~reliability_bins çifte-sayım (kat 8)~~ ve ~~denetim
  bulguları #1/#2/#4 (confluence yön, penalty taban, mfe_r clamp)~~ —
  **2026-07-04 teyit: DÖRDÜ DE zaten düzeltilmiş** (commit d52d44fd "4 bugfix
  paketi, owner onayı 2026-07-02", `tests/unit/test_bugfix_2026_07_02.py`
  5/5 yeşil; bu satır bayattı). Kalan tek küçük iş: FE degraded_reasons/
  coverage çipleri (kat 15).

## K serisi — Keşif motoru Faz A+B (2026-07-04, owner talebi — PLAN, kodlanmadı)

> Owner fikri: "analiz sabit, varlık değişken" — sistem eklenen varlıkları
> beklemek yerine geniş evrende analizlere UYAN varlıkları kendisi bulsun.
> Bu CP5 keşif fazının güvenli yarısıdır. Faz A+B'de İŞLEM AÇILMAZ; karar
> zinciri / RiskGate / ağırlıklar / tik süresi DOKUNULMAZ (davranış-nötr, 🟢).
> Faz C (terfi paketi) yalnız TANIMLANIR; Faz D (dar limitli otomatik açılış)
> AYRI owner kararı — kırmızı çizgi.

| # | İş | Kapsam | Risk |
|---|---|---|---|
| K-0 | **Evren + flag (owner kararları 2026-07-04):** `config/discovery.yaml` — (a) kripto: CoinGecko markets top-50 (hacim eşiği, stablecoin + mevcut assets.yaml/custom dışlanır), (b) hisse/ETF tarafı SEKTÖR-GÜDÜMLÜ (K-0b) — statik genel liste YOK. Env flag `DISCOVERY_SCAN_ENABLED` DEFAULT OFF → adım tam no-op (learning run bayt-aynı). Yeni env-flag kuralları: conftest delenv + flag-sync-check SYNC_FLAGS + lokal .env↔AWS ensure_env birlikte. **✅ KODLANDI (2026-07-04): discovery.yaml (yalnız sector_rotation bölümü — kripto/kota bölümleri K-1'de okuyucusuyla gelir, ölü config yok), flag + conftest delenv + SYNC_FLAGS kayıtlı. ✅ AKTİVE (2026-07-04 owner kararı, ayrı commit): lokal .env + deploy ensure_env birlikte =1; flag-sync OK. Salt-gözlem — watchdog kaydı gerekmez (outcome'a temas yok), izleme penceresini bozmaz. Sektör karnesi birikmeye başladı** | config + kayıt | 🟢 |
| K-0b | **Sektör rotasyon motoru** `packages/discovery/sector_rotation.py` (owner kararı 2026-07-04): 12 sektör ETF'si (XLK/XLE/XLF/XLV/XLI/XLY/XLP/XLU/XLB/XLRE/XLC/IYT) discovery.yaml'da tanımlı; 1d barlar mevcut OHLCV provider+cache'ten (assets.yaml'a GİRMEZ — snapshot/işlem evreni değişmez, likidite rotasyonuna EKLENMEZ: o canlı konsensüsü besler ve sınıf-arası soruya cevap verir, sektör motoru sınıf-İÇİ alt katman). Ölçüm rotation/engine deseniyle: SPY'a göreli getiri (1w/1m/3m) + 30g momentum → sektör başına YÜKSELEN/NÖTR/DÜŞEN + sıralama; veri yoksa ÖLÇÜLEMEDİ (mock yok). Saatte 1 koşum yeter. **Sektör karnesi:** her hüküm damgalanır, N gün sonra gerçekle kıyas (ETF/SPY gerçekleşen) → motorun isabet karnesi panelde; hiçbir karar bu motora karneden önce bağlanmaz. v1 kapsam: yalnız YÜKSELEN sektörler → LONG adayı; short tarafı sonraki faz (owner). Aday üretimi v1: sektör ETF'sinin KENDİSİ; v2: sektör→~10 likit hisse haritası (config'te statik seed; akıl seçimde, üyelik listesi nadiren değişen veri). **✅ KODLANDI (2026-07-04): `packages/discovery/sector_rotation.py` (göreli güç 1w/1m/3m ağırlıklı skor + 30g momentum, verified-only, benchmark yoksa hepsi UNAVAILABLE) + karne (günde 1 damga, ~7 takvim günü sonra gerçekleşenle çözüm, NEUTRAL puanlanmaz, 30 gün çözümsüz → expired) + learning worker adımı (`discovery_status` run meta; OFF=DISABLED) + 12 ETF yfinance OHLCV haritasına (evren/rotasyon değişmedi) + SECTOR_ROTATION_PATH conftest izolasyonu. 9 test; suite 1445 yeşil** | yeni modül | 🟢 |
| K-1 | **Tarayıcı çekirdeği** `packages/discovery/scanner.py`: learning worker `run_once`'a kendi try/except + status'lu YENİ adım (mevcut adım deseni). Koşu başına kota `DISCOVERY_SCAN_PER_RUN` (default 5 aday) + round-robin cursor (`data/runtime/discovery_scan.json`) → ~50'lik evren ~50dk'da bir tam tur (worker ~5dk cadence). Aday başına: OHLCV multi-TF (mevcut provider+cache; verified bar yoksa SKIP — DATA_POLICY, mock yok) → `build_timeframe_result` (touche) per TF; global bağlam (rejim/sentinel/news) SON canlı snapshot'tan okunur (yeni ağ çağrısı yok, aday başına haber çekilmez). Karar simülasyonu: mevcut eşikler + kalibrasyon + empirical_pwin (tf\|rejim — varlık-bağımsız tablolar) → verdict {açılırdı/açılmazdı, yön, güven, hipotetik SL/TP (tf_targets geometrisi)}. Bütçe: LEARNING_BUDGET_MS'in yarısı aşılırsa o koşuda durur, cursor'dan devam. **✅ KODLANDI (2026-07-04): `universe.py` (CoinGecko markets TEK liste çağrısı → momentum kısa listesi; stablecoin/wrapped-dublör/mevcut-varlık/likidite süzgeci; API bütçe gerekçesi discovery.yaml'da — 50 coin'e kör OHLCV çekilmez) + `scanner.py` (discovery-lite: teknik motor + kalibrasyon + EV formülü + SL/TP motoru CANLI fonksiyonların KENDİSİ, kopya yok; bilinçli farklar docstring'de: haber/sentinel/quantum/mistake-memory/portföy kapıları girmez). v1 sinyal kuralı: LONG-only + 1d bullish ŞART + ≥2 TF bullish + min_open_confidence + EV>0. Kota round-robin (per_run 5 / 15dk), markets TTL 1h, kripto 4h yerel resample (ek çağrı yok). Artifact discovery_scan.json (conftest izole). 10 test; suite 1455 yeşil. Not: bütçe-durdurucu yerine kota+interval yeterli çıktı (12 sembol/sa tavan)** | yeni modül + worker adımı | 🟢 |
| K-2 | **Gölge kanıt defteri** `packages/discovery/shadow_ledger.py`: "açılırdı" verdiktleri AYRI append-only jsonl'e (`data/runtime/discovery_shadow.jsonl`; S1-2 rotasyon deseni). Çözümleme missed_opportunity deseniyle: sonraki koşularda OHLCV'den TP-önce/SL-önce/TTL → missed_win / avoided_loss / expired. MEVCUT missed-opp ve shadow_decisions verisine KARIŞMAZ (ayrı dosya — gerçek ölçüm hücreleri kirlenmez, F5-1 cf_by_tf ilkesi). Aday özeti: n_signals, resolved, cf_win_rate, ort. R. **✅ KODLANDI (2026-07-04): `shadow_ledger.py` (track_open/resolve event replay — missed_opportunity kuralının AYNISI: aynı barda ikisi → temkinli SL-önce, mfe 20R kırp; TTL tablosu discovery.yaml `shadow.ttl_hours` 1h:24/4h:72/1d:240; DISCOVERY_SHADOW_MAX_MB rotasyonu). API bütçe kuralı closure'da: kripto barı yalnız o koşuda ZATEN taranan sembole (cache sıcak → sıfır ek çağrı), ETF her zaman (ucuz orkestratör), listeden düşmüş kripto yalnız yaş-expiry. Aday özeti (`candidate_summary`: n_signals/resolved/cf_win_rate/avg_r/TF seti — K-4 kriterinin girdileri) scan artifact'ının `shadow` bloğuna gömülü; worker log'u defter sayaçlarını basar. Çözülen izleme sonrası süren sinyal YENİ izleme açar (kanıt birikir). Gerçek-veri kanıt (lokal): 5 ETF sinyali damgalandı (XLV/XLF/IYT/XLI 1h ttl24, XLK 4h ttl72), geometri sağlıklı. DISCOVERY_SHADOW_PATH conftest izolasyonu. 7 test; suite 1463 yeşil** | yeni modül | 🟢 |
| K-3 | **API + panel** (contract-first): `GET /learning/discovery` (openapi.yaml → codegen) — evren durumu, tarama ilerlemesi, aday tablosu (sembol, sinyal n, cf_win_rate, son sinyal, TF dağılımı) + dürüstlük satırı ("hipotetik — işlem açılmadı"). DiscoveryPanel (mevcut panel desenleri, FE hesap yapmaz) | API + FE | 🟢 KODLANDI+DOĞRULANDI (2026-07-04): `scanner.viewmodel()` artifact'tan türetir (aday satırı = güncel WOULD_OPEN_LONG ∪ gölge geçmişi olan semboller; "tarandı-boş" satırlar elenir; sıra: sinyal önce, sonra çözüm/isabet/EV). `GET /learning/discovery` (learning router) read-only, PAPER_SAFE. Contract-first: openapi.yaml `DiscoveryView`+alt-şemalar → `codegen.py` schema.ts + elle api.ts tipleri (friendly_types_map_to_contract GEÇER — KNOWN_UNCONTRACTED gerekmedi) → client/keys/hook → `DiscoveryPanel` (Öğrenme Hattı ADIM 11; dürüstlük banner'ı HER ZAMAN; flag OFF → "kapalı" durumu; sinyal yeşil/gölge-only "—"; isabet+Ort.R kolonları). 3 viewmodel testi (boş/flag/satır-birleşim). Preview uçtan uca doğrulandı (API 9000 → next rewrite → panel render: XLV %75 isabet, IYT sinyal-karnesiz, XLK gölge-only −1R; konsol temiz). tsc+ruff+codegen-check temiz |
| K-4 | **Faz C terfi kriteri** `packages/discovery/promotion.py`: aday owner paketine girer ancak: ≥20 çözülmüş kararlı gölge sinyali (missed_win+avoided_loss; expired hariç) + cf_win_rate %95 Wilson ALT sınırı > 0.5 + ≥2 farklı TF'de sinyal (F5-2/challenger_promotion deseninin uyarlaması; wilson_bounds REUSE). Paket = custom_assets'e ekleme ÖNERİSİ (STRATEGY_ENABLE, `add_custom_asset` dedupe; owner onayı; otomatik ekleme YOK). Tüketim = governor defteri + worker run meta `discovery_promotion_status` (ayrı panel/kontrat gerektirmez, promotion_criteria yüzeyi). discovery.yaml `promotion` bloğu (min_resolved_decisive/min_timeframes okunur). **✅ KODLANDI (2026-07-05): aynı DISCOVERY_SCAN_ENABLED kapısı (tarayıcı+defter SONRASI worker adımı); canlı: 7 gölge aday hepsi NOT_READY (çoğu dec=0 çözülmemiş, LABUSD dec=2 cf=0.5 → hiçbiri ≥20 eşiğine yakın değil, kriter ince kanıtta ateşlenmiyor). 9 test.** KIRMIZI ÇİZGİ: onay bile canlı evreni (custom_assets/assets.yaml) değiştirmez | ✅ (2026-07-05) | 🔴 owner-onay; **K serisi TAMAM** |

**Dilimleme:** (1) K-0+K-0b (evren + sektör motoru + karne temeli), (2) K-1
(tarayıcı; kota sıcak sektörlere ve kripto top-50'ye akar), (3) K-2, (4) K-4
kriterini rapora gömerek K-3 — her dilim ayrı commit + OFF-bekçi regresyon
testi (flag kapalıyken learning run bayt-eşdeğer). Aktivasyon (`DISCOVERY_SCAN_ENABLED=1`) davranış-nötr
🟢 olduğundan S3 izleme penceresini BOZMAZ; yine de ayrı tarihli commit.
**Riskler:** CoinGecko ücretsiz plan rate-limit (kota+cache ile yönetilir; 429
görülürse aday SKIP+cooldown), missed-opp çözümü için OHLCV bar derinliği,
statik hisse listesinin bakım yükü (owner düzenler).
**Owner kararları (2026-07-04):** kripto top-50 ✅; hisse/ETF sektör-güdümlü
(statik genel liste yerine) ✅; v1'de aday = sektör ETF'sinin kendisi ✅; v2
hisse haritası sektör başına ~10 ✅; v1 yalnız LONG (yükselen sektör) ✅;
sektör ETF'leri likidite rotasyonuna EKLENMEZ ✅. Açık kalan: koşu başına
kota (öneri 5) + panel önceliği — kodlama sırasında default'la gidilir.

## S serisi — Hız + Acil + Aktivasyon sprinti (2026-07-04, owner talimatı)

> Kaynak: 2026-07-04 tam-repo denetim raporu (oturum kaydı). Owner talimatı:
> hız sorunlarını çöz, kanıtı hazır kapalı özellikleri aç, acil bozuklukları
> düzelt. Kurallar: (1) çalışan sistem bozulmaz, (2) ölü kod/şişmiş mimari
> yok, (3) harcanan her token sistemi iyiye götürür.
>
> **Ölçülmüş taban (bu sprint öncesi):** tick süresi ~22.4s (30s aralıkta);
> `build_snapshot` ~19.9s; bunun içinde news cold ~11.2s (GDELT SSL
> handshake 8s timeout — bu makineden ağ seviyesinde ERİŞİLEMİYOR, canlı
> test 2026-07-04) + prices ~3.9s; agent matrix 1.3s × tick başına 2 kez;
> `shadow_decisions.jsonl` 221MB / 27.704 satır ve `read_recent` her
> çağrıda TÜM dosyayı okuyor. Deribit options da bu makineden bloklu
> (WinError 10054). Canlı sonuç: realized −$1.495; SL_HIT 42/−$2.877,
> TP_HIT 23/+$3.382, TRAILING 34/+$280 (kârın %66–83'ü geri veriliyor,
> forensics tahmini kaçak ~$2.400), TIME_STOP 31/−$3.

| # | İş | Durum | Risk | Not |
|---|---|---|---|---|
| S1-1 | GDELT başarısızlık-cooldown'u: ardışık hata sonrası `GDELT_COOLDOWN_SEC` (default 900) boyunca fetch atlanır; status dürüstçe degraded + cooldown notu. Tekrarlayan 8s SSL timeout'un her news-refresh'te (~120s TTL) tick'i kilitlemesini keser | ✅ (2026-07-04) 3 test | 🟢 | davranış-nötr (veri zaten gelmiyordu) |
| S1-2 | Shadow log tail-read + rotasyon: `read_recent` dosya sonundan chunk'la okur (tam-dosya `read_text` yerine); `record` dosya `SHADOW_LOG_MAX_MB` (default 128) aşınca `.1` yan-dosyasına devirir, okuyucu gerekirse `.1`'e uzanır. En büyük tüketici promotion_criteria (limit 200 satır ≈ 1.6MB) | ✅ (2026-07-04) 3 test; mevcut 221MB dosya ilk record'da `.1`'e devrilir | 🟢 | davranış-nötr (aynı kayıtlar döner) |
| S1-3 | Agent matrix tek kurulum/tick: `build_timeframe_result` sonuçlarına kısa-TTL memo (symbol+tf+içerik-parmak-izi anahtarlı, TTL 25s; explicit `now` verilirse — testler — memo DEVRE DIŞI) — conflict-gate precompute + shadow.observe aynı ağır hesabı 2 kez yapmasın. tf_weights farkı memo'yu etkilemez (weights memo'dan SONRA, consensus birleşiminde) | ✅ (2026-07-04) 2 test | 🟢 | çıktı bayt-eşdeğer (aynı kapanmış barlar) |
| S1-4 | Heartbeat dürüstlüğü: worker DEGRADED hesabına `degraded_reasons` (additive) + OPSİYONEL sağlayıcı ayrımı (`OPTIONAL_PROVIDERS = {gdelt, options_deribit}`) — yalnız bunlar arızalıysa worker OK kalır (sebepler yine listelenir). Kalıcı-arızalı yan sağlayıcının gerçek arızayı maskelemesini bitirir | ✅ (2026-07-04) 1 test | 🟢 | yalnız gözlem yüzeyi |
| S2-1 | F2-1 gate bağlama (kayıt fazı): `RiskInput.mtm_equity_usd` (additive, default None) + `risk_gates.mtm_equity_enabled` flag (bu commit'te FALSE) → açıkken drawdown kontrolü `min(equity, mtm_equity)` ile (yalnız SIKILAŞTIRIR; MTM kârı gate'i asla gevşetemez — testle kilitli). tick_worker değeri geçer; watchdog REGISTRY `mtm_equity_gate` kaydı AYNI commit (flag OFF — E-6 dersi: kayıt ve aktivasyon AYRI deploy) | ✅ (2026-07-04) 4 test | 🟡 | aktivasyon S3-3'te |
| S2-2 | `data/runtime/paper_state.corrupt-*.json` (19 dosya) → `data/runtime/archive/` altına taşındı (kök neden PR#4'te çözülmüştü; dosyalar çöp). Kod değişikliği yok | ✅ (2026-07-04) | 🟢 | geri alınabilir (taşıma) |
| S3-1 | **AKTİVASYON** `empirical_pwin.enabled: true` (owner kararı 2026-07-04). Kanıt: 15m\|NEUTRAL p=0.449 (n=49) → cal_conf yerine gerçekleşen isabetle EV/Kelly; 15m Kelly cap f*≈0.08 → zayıf TF otomatik küçülür. Paket 2/(2) — sırası gelmişti. conftest OFF-pin eklendi (suite v1 baseline'da kalır) | ✅ (2026-07-04) | 🟡 | watchdog kayıtlı (OFF→ON arm olur) |
| S3-2 | **AKTİVASYON** `technical.htf_alignment.enabled: true` (T-1; owner kararı 2026-07-04). Kanıt: bloklanan 15m fırsatlarının %87'si avoided_loss + 15m ampirik EV negatif — alt dilim üst-dilim trende karşı işlem üretiyor; filtre YALNIZ kısar. conftest OFF-pin eklendi | ✅ (2026-07-04) | 🟡 | watchdog kayıtlı |
| S3-3 | **AKTİVASYON** `risk_gates.mtm_equity_enabled: true` — S2-1'den AYRI deploy. Açık pozisyonlar toplamda eriyorsa drawdown freni realized beklemeden çeker | ✅ (2026-07-04, commit 5ea0d709) watchdog mtm_equity_gate baseline OFF görüp ARM etti (last_seen False→True doğrulandı) | 🟡 | E-6 sıralaması yerel doğrulandı |

**Bilinçli AÇILMAYANLAR (2026-07-04 kanıt durumu — kural 3):**
`partial_tp` (shadow kanıtı n=2, uplift −$16 → YETERSİZ; 🔴 kural: uplift
kanıtı birikmeden AÇILMAZ — trailing giveback'in asıl ilacı bu, kanıt
biriktikçe İLK aday), `empirical_pwin.blend_counterfactual` (S3-1
penceresinden SONRA anlamlı), `EXIT_FORENSICS_NUDGE` (rollout sırası:
TF_TARGET_AUTO_ONLY penceresi temiz + EDGE_GATE kararı sonrası),
`TF_TARGET_EDGE_GATE=0` (owner kararı 2026-07-03: aktif tuning sürsün),
`WEIGHT_REGIME_FILTER` / `MISTAKE_MEMORY_V2` / `EXPECTANCY_R_MODE` (kanıt/
R-verisi bekliyor), T-2/T-3/T-4 (shadow kanıtı birikiyor),
`strategy_shaping` (gölge setup dağılımı izlenmeden açılmaz),
`conflict_gate` SCALP/SWING (önce INTRADAY/TACTICAL HARD sonuçları),
`data_policy.block_stale_ohlcv_for_trade` (dampening yeterli, sert blok
kanıtsız), `shadow.affect_decision` + `conflict_resolver_activation`
(KIRMIZI ÇİZGİ — owner onay paketi F5-2 READY olmadan asla).

## B serisi — Backtest-challenger motoru (2026-07-04, owner kararı)

> **AKTİF (2026-07-05, owner kararı): `BACKTEST_CHALLENGER_ENABLED=1`** (lokal
> .env + deploy ensure_env + flag-sync SYNC_FLAGS birlikte). İzole/shadow:
> geçmiş-yeniden-kurma verisi otomatik birikir (B-2 günlük interval + B-3 karne
> + B-4 terfi değerlendirmesi her cycle); canlı ağırlık/paper/karara ASLA
> dokunmaz. Sıradaki: bu kanıtı görselleştiren öğrenme-katmanı paneli.
>
> Owner sorusu: "cat 6/7 (quantum/ağırlık) için canlı veri birikmesini
> beklemek yerine backtest ile devam etsek?" Kanıt: NEUTRAL %88 (137/155
> outcome), OFFENSIVE 7, DEFENSIVE/CRISIS 0 → rejim-çeşitliliği yok, ağırlık
> trainer'ı öğrenemez; module_attribution kazanan≈kaybeden (touche 23.6/24.3
> TERS, quantum 3.1/3.4 TERS). Mevcut iki backtest aracı yetersiz:
> `strategy_backtest` touche-only, `backtest.py` snapshot-replay yalnız ~9
> saatlik NEUTRAL pencere. ÇÖZÜM: quantum/fundamental/sentinel fiyat/makro
> serilerinden TÜREDİĞİ için (BTC/altın/DXY/VIX 1-2 yıl gerçek geçmiş var,
> news hariç) geçmişe dönük yeniden-kurulabilir → rejim-çeşitli GERÇEK-veri.
>
> **Pazarlıksız güvenlik:** (1) yalnız gerçek seri (news nötr+damgalı, uydurma
> yok — DATA_POLICY); (2) İZOLASYON — backtest outcome'ları AYRI challenger
> kanalına, canlı `verified` deftere/ağırlığa ASLA karışmaz; champion/
> challenger (F5-2) deseniyle owner onayına sunulur, oto-uygulanmaz; (3)
> bilinen sınır: geçmiş ilişkiler canlıda birebir tutmayabilir → backtest
> KARAR VERMEZ, owner'a kanıt sunar.

| # | İş | Durum | Risk | Not |
|---|---|---|---|---|
| B-1 | **Geçmiş çok-modül yeniden-kurma + fidelity harness** (`packages/learning/backtest_recon.py`, salt-ölçüm/izole): CANLI fonksiyonların kendisiyle (kopya yok) touche/quantum/fundamental_v2/sentinel'i geçmiş indekste yeniden kurar; LOOK-AHEAD yok (tarih-hizalı `ts ≤ as_of`); news nötr+damgalı. Fidelity: son indekste yeniden-kurulan quantum ↔ BAĞIMSIZ canlı `get_rotation()`; FAITHFUL/DRIFT. Flag `BACKTEST_RECON_ENABLED` OFF→no-op; artifact `backtest_recon.json` (izole). Learning worker adımı OFF-kapılı | ✅ (2026-07-04) 8 test; **canlı FAITHFUL (quantum_delta 0.0)** — tarih-hizalama bug'ı harness'le yakalanıp düzeltildi (indeks-hizalama farklı-uzunluk serilerde yanlış tarihi alıyordu). Bilinen sınır: Likidite katmanı düşüyor (US10Y/US02Y FRED'de, OHLCV cache'te yok) → B-2 FRED geçmişini ekler | 🟢 | fidelity kapısı FAITHFUL → B-2 yeşil ışık |
| B-2 | **Rejim-çeşitli outcome üretimi:** B-1 çekirdeğini her geçmiş indekste koştur → her kararın forward-return outcome'u + rejim etiketi + module_contributions, AYRI `backtest_challenger.jsonl`'e. Karar CANLI `consensus.build()` ile (kopya yok → yön/dominant/module_contributions canlı şekliyle, champion ağırlıklarıyla); ortak `_snap_at` (B-1 fidelity davranışı birebir korunur). LOOK-AHEAD yok (karar `bars ≤ i`; son `horizon` indeks atlanır). FRED geçmişi (`fred.get_history`, US10Y/US02Y/CPI) `_load_series`'e merge (anahtar varsa Likidite tam). news nötr+damgalı. Ayrı flag `BACKTEST_CHALLENGER_ENABLED` OFF→no-op, interval-kapılı; canlı outcome defterine/ağırlığa/paper'a ASLA yazmaz | ✅ (2026-07-05) 15 test; **canlı üretim: 365 barda 329 kayıt, rejim histogramı OFFENSIVE 80 / NEUTRAL 143 / DEFENSIVE 100 / CRISIS 6** (motive eden kanıt DEFENSIVE/CRISIS 0 idi → çeşitlilik geldi); label WIN 85 / LOSS 102 / FLAT 142. Bilinen sınır: lokalde `FRED_API_KEY` yok → `fred_liquidity=False` (damgalı; AWS'te anahtarla True) | 🟢 | izole kanal — B-3 için yakıt hazır |
| B-3 | **Challenger ağırlık eğitimi + quantum ayrım karnesi** (`packages/learning/challenger_trainer.py`): `read_challenger()` kayıtlarını rejim başına `dominant_module` ile bucketle → CANLI `auto_weight_trainer._module_score`/`_loss_aware_score`/`_propose_for_regime` REUSE (kopya yok, champion matematiği) → rejim başına challenger ağırlık + champion delta (shadow). win_rate=WIN/(WIN+LOSS) (FLAT paydadan düşer). Quantum karnesi (cat 6): rejim başına separation=mean(fr\|q≥55)−mean(fr\|q≤45) + Pearson corr + verdict (DISCRIMINATES/INVERSE/FLAT); quantum dominant olmasa da skoru `module_contributions`'tan okunur. Aynı `BACKTEST_CHALLENGER_ENABLED` kapısı (B-2 sonrası worker adımı); izole rapor `backtest_challenger_report.json`; canlı ağırlığa/config'e ASLA yazmaz | ✅ (2026-07-05) 10 test; **canlı karne: quantum DEFENSIVE'da DISCRIMINATES (sep +0.005, corr +0.18), NEUTRAL'da INVERSE (sep −0.018, corr −0.14), OFFENSIVE corr +0.31**; challenger ağırlık NEUTRAL+DEFENSIVE PROPOSED (touche DEFENSIVE'da win_rate 0.11 → kısılıyor), OFFENSIVE/CRISIS yetersiz-çeşitlilik | 🟢 | shadow — B-4 owner terfi için hazır |
| B-4 | **Owner terfi paketi** (`packages/learning/challenger_promotion.py`): B-3 challenger ağırlık setlerini champion'a (canlı aktif) karşı EŞLEŞMELİ kıyaslar — aynı kaydın modül skorlarını İKİ ağırlık vektörüyle yeniden-harmanlar; harman+yön CANLI `consensus._redistribute`/`_direction` REUSE (kopya yok, fark yalnız ağırlıkta). Piyasa gerçeği = ham `forward_return` işareti (nötr band çözülmez); ayrışma = yön farkı + kararlı piyasa, kazanan yönü tutan (missed_win/avoided_loss analogu). Üç kriter (promotion_criteria deseni): eşleşmiş hacim ≥200 + çözülmüş ayrışma ≥30 + challenger isabetinin %95 Wilson ALT sınırı > 0.5. Tutarsa governor defterine STRATEGY_ENABLE paketi (dedupe; promotion_criteria'dan AYRI `requested_change` anahtarı). Aynı `BACKTEST_CHALLENGER_ENABLED` kapısı (B-3 sonrası worker adımı). KIRMIZI ÇİZGİ: onay bile canlı ağırlığı değiştirmez — terfi owner-gated rebalance ile ayrı elle iş | ✅ (2026-07-05) 11 test; **canlı: 244 eşleşme (≥200 ✓) ama yalnız 3 çözülmüş ayrışma (≥30 gerek) → NOT_READY** (challenger dar bantta farklı → nadiren yön ayrışır; kriter ince kanıtta ateşlenmiyor — dürüst fren). per_regime: NEUTRAL challenger 2/2, DEFENSIVE champion 1/1 | 🔴 | owner-onay; **B serisi TAMAM** |

**B serisi ne açar:** cat 6 (quantum ayrımı rejim-bazlı ölçülür), cat 7
(rejim-çeşitli challenger ağırlık), BONUS cat 11 (aynı motor devasa çıkış-
outcome örneği üretir). Hepsi izole/shadow/owner-kapılı — canlı sistem bozulmaz.

## I serisi — Öğrenme katmanı entegrasyonu + otomasyonu (2026-07-05, owner talebi)

> Tam analiz: **`docs/LEARNING_INTEGRATION_REPORT.md`** (mevcut durum + mimari +
> shadow-dahil mekanizması). Owner talebi: 40+ öğreniciyi (bugün 4 ayrı olgunluk
> katmanında ada) tek omurgaya bağla + shadow/toplanan veriyi GEREKTİĞİNDE dahil
> et. Omurga: **Kanıt Otobüsü → Olgunluk Kapısı → Karar → İzleme → Rollback.**
> Pazarlıksız: additive · flag-OFF=bayt-aynı · shadow-önce · rollback'li ·
> off-tick · ölü-kod-yok. KIRMIZI ÇİZGİ: yön motoru + execution owner onayı
> olmadan ASLA otomatik (I serisi bu ikisini basamak-2/öneride durdurur).
>
> **Otomasyon merdiveni (her öğrenici bu 5 basamaktan çıkar):** 0-Ölç (risksiz) →
> 1-Gölge (risksiz) → 2-Öner (owner onayı) → 3-Dar-bant oto (edge-gate+rollback)
> → 4-İzle (watchdog+guard_safety). Yön/execution basamak-2'yi geçemez.
>
> **Öneri sırası + gerekçe:** I1+I2 ÖNCE (omurganın kendisi; ikisi de güvenli
> gözlem/refactor, davranış değişmez) → I3 (owner'ın asıl "shadow-dahil" isteği)
> → I4/I5/I6 (omurga kurulunca hızlı+düşük risk).

| # | İş | Kapsam (kod + kabul kriteri) | Durum | Risk |
|---|---|---|---|---|
| I1 | **Kanıt Otobüsü** `packages/learning/evidence_bus.py` | 5 kaynağı (signal_quality=live, quantum karnesi=backtest, edge_report=live, discovery candidate_summary=shadow, tf_calibration=live) TEK `EvidenceRecord{topic, subject, source: live\|shadow\|backtest, regime, timeframe, n_samples, statistic, verdict, detail}` listesine indirger. Her kaynak İZOLE try (biri patlarsa otobüs düşmez). `collect()` + `viewmodel()` + `GET /learning/evidence-bus`. Salt-gözlem: mevcut fonksiyonları OKUR. **✅ KODLANDI (2026-07-05): 4 test; canlı endpoint total=26 (live 15 / backtest 4 / shadow 7), 5 konu, 9 hüküm — üç kaynak türü de tek görünümde.** Tüketim: endpoint (I6 paneli okuyacak) | ✅ (2026-07-05) | 🟢 |
| I2 | **Olgunluk Kapısı** `packages/learning/maturity_gate.py` | Üç dağınık kapıyı TEK saf fonksiyona topla: `assess(n_samples, verdict, edge_safe) → {level(0-3), maturity, reason, ready_to_propose, ready_to_autotune}`. Basamaklar: 0 INSUFFICIENT (az örnek) → 1 OBSERVED (yeterli örnek/net sinyal yok) → 2 PROPOSABLE (net sinyal, edge stabil değil → owner ÖNERİ) → 3 ACTIONABLE (net sinyal + edge stabil → dar-bant OTO, owner-flag ayrı). min-örnek (20) + net-hüküm (INVERSE de net) + `edge_report.safe_to_autotune` (GLOBAL, evidence_bus'tan). I1'in HER kaydına `maturity` damgası ekler (`collect()` doldurur; `viewmodel` `by_maturity` sayacı). KIRMIZI ÇİZGİ: kapı yalnız "kanıt olgun mu" der, TERFİYİ YAPMAZ (I4/I5). Trainer'lara HENÜZ dokunmaz (migrasyon I4). **✅ KODLANDI (2026-07-05): 12 test; canlı damga total=22 → INSUFFICIENT 12 / OBSERVED 6 / PROPOSABLE 4 / ACTIONABLE 0 — global edge stabil değil, kapı hepsini basamak-2'de tutuyor (dürüst fren, hiçbir kanıt oto-hazır değil).** Tüketim: evidence_bus (I6 paneli okuyacak) | ✅ (2026-07-05) | 🟢 refactor |
| I3 | **Kaynak Seçici** `packages/learning/source_selector.py` | **Owner'ın asıl isteği.** Bir öğrenici "bu rejim/TF için canlı kanıt ince" derse sırayla shadow → backtest_challenger → discovery_shadow'dan AYRI KANALDA damgalı kanıt çeker (F5-1 `cf_by_tf` ilkesi: gerçek hücreler KİRLENMEZ; kaynak damgalı). Tek switch `LEARNING_INCLUDE_SHADOW` (env, DEFAULT OFF=bayt-aynı). İlk tüketici: signal_quality/FAZ-4 boş rejimlerini backtest quantum karnesiyle destekle (damgalı). **Kabul:** flag OFF→bayt-aynı; ON→ince rejimde `source: backtest` damgalı kanıt; rollback = flag kapat. | ⬜ | 🟡 flag-OFF |
| I4 | **Terfi Hattı** `packages/learning/promotion_rail.py` | 3 kopyayı (`promotion_criteria`/`challenger_promotion`/`discovery_promotion`) TEK motora indir: "kanıt → Wilson kapısı → governor.submit → dedupe". Üçü de rail'i çağırsın (davranış+dedupe anahtarları KORUNUR — bayt-aynı). Yeni terfi = config satırı. **Kabul:** üç modülün mevcut testleri yeşil kalır; governor paketleri aynı şekil. | ⬜ | 🟢 refactor |
| I5 | **İzleme kapsama** (`activation_watchdog` + rollback standardı) | Canlıya dokunan HER terfiye watchdog+rollback otomatik takılsın. Eksik kalan aktivasyonları REGISTRY'ye ekle; auto-apply store'larının hepsi rollback'e bağlı olduğunu guard'la (test). **Kabul:** "izlemesiz canlı-dokunuş yok" testi; registry-kapsama testi. | ⬜ | 🟢 |
| I6 | **Orkestrasyon paneli** "Öğrenme Beyni" | I1 evidence_bus + I2 maturity'yi tek panelde göster: her öğrenici hangi basamakta (0-4), hangi kanıtla (live/shadow/backtest), sıradaki eşik ne. Contract-first değil — observe-only friendly type (DiscoveryPanel/BacktestChallengerPanel deseni + KNOWN_UNCONTRACTED). **Kabul:** tsc temiz, izole preview render, panel Öğrenme Hattı'nda. | ⬜ | 🟢 |

**Dilimleme:** her I-dilimi AYRI commit + OFF-bekçi/refactor-bayt-aynı testi + push öncesi tam suite yeşil. I3 aktivasyonu (`LEARNING_INCLUDE_SHADOW=1`) AYRI owner kararı + ayrı deploy (flag-kayıt vs aktivasyon ayrı — watchdog arm kuralı). Yeni env-flag (`LEARNING_INCLUDE_SHADOW`) → conftest delenv + flag-sync SYNC_FLAGS + lokal .env↔AWS ensure_env birlikte.

**I serisi ne açar:** dağınık 40+ öğrenici tek nehir; shadow/backtest verisi gerektiğinde damgalı akar; her yeni öğrenici sıfır-tekrar omurgaya takılır. Owner kırmızı çizgileri (yön motoru + execution) sabit — I serisi onları basamak-2'de (öneri) tutar, asla otomatik terfi ettirmez.

## Devir notu (son güncelleme: 2026-07-03)

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
- **E serisi — Çıkış/Stop öğrenme derinleştirme (2026-07-03, kodlama
  TAMAM, aşağıda tabloda):** Gerekçe: AUTO kohort net −$864/133 işlem;
  zararın kaynağı çıkış kalitesi (SL_HIT 38 işlem −$1978 vs TP_HIT 22
  işlem +$3313). Yeni modül `exit_forensics` (Çıkış Otopsisi, salt-gözlem)
  + `size_usd` zenginleştirme + dashboard paneli flag'siz/additive canlı;
  iki davranış flag'i DEFAULT OFF: `TF_TARGET_AUTO_ONLY` (trainer +
  entry_exit_quality dataset'i yalnız AUTO kohort — TF_CALIBRATION_
  AUTO_ONLY'nin klonu; o flag sabah 2026-07-03 AÇILDI) ve
  `EXIT_FORENSICS_NUDGE` (sabit ±%10 yerine ölçülen şiddete oranlı adım,
  klamp [0.05, 0.15] = AUTO_APPLY_BAND_PCT tavanı). Rollout sırası:
  SHADOW ≥2 hafta (panel $ toplamları OutcomeLedger by_close_reason ile
  mutabık olmalı) → `TF_TARGET_AUTO_ONLY=1` → `TF_TARGET_EDGE_GATE=1` →
  `EXIT_FORENSICS_NUDGE=1` (hepsi lokal .env + deploy-from-github.sh
  ensure_env birlikte). Bilerek reddedilenler: 1d için 4h kanıtı
  havuzlama, MIN_TRADES_PER_TF indirme (1d panelde dürüst "EĞİTİLMEMİŞ
  13/20" gösterilir), kapanış-sonrası karşı-olgu hesabı.
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
| E-1 | `size_usd` zenginleştirme: decision_log outcome bloğu + `CanonicalOutcome.size_usd` (legacy kayıt → None) — $ maliyeti tahmin yerine kesin ölçülebilsin (notional çıkarımı başabaş time-stop'ta çöker) | 2026-07-03 çıkış denetimi | ✅ (2026-07-03) flag'siz saf-additive alan (risk_pct/F1-1 deseninin aynısı); iki outcome builder'da okunur | 🟢 | E |
| E-2 | `packages/learning/exit_forensics.py` — Çıkış Otopsisi (salt-gözlem): yalnız AUTO kohort; TF × kapanış-kategorisi bucket'ları; trailing give-back/capture, time-stop kaçan hareket (never_worked = giriş sorunu, çıkış maliyetine GİRMEZ), SL üçlü sınıf (roundtrip=makine kârı koruyamadı / straight=giriş sorunu HARİÇ / gray=atıfsız); $ alanları `*_usd_est` (size_usd tercih, yoksa notional çıkarım, yoksa None); en pahalı 3 hata Türkçe düz-dil kart; `trainer_evidence()` E-5 girdisi; worker snapshot `data/runtime/exit_forensics.json` {latest, history≤60} | 2026-07-03 çıkış denetimi | ✅ (2026-07-03) kapanış-sonrası karşı-olgu YOK (veri yok, hesaplanamaz); MIN_BUCKET=5 altı bucket kart üretmez; excluded/limits şeffaflık blokları; worker run meta `exit_forensics_status` (canlı: usable=133 buckets=16 top_costs=3) | 🟢 | E |
| E-3 | API + kontrat + dashboard: `GET /learning/exit-forensics` (yeni şemalar) + `/learning/tf-targets`e additive `coverage` (TF-başı auto_n/verified_n/min_required/TRAINED\|UNTRAINED — 1d dürüst "EĞİTİLMEMİŞ 13/20") ve `trainer_inputs` (iki flag durumu); YENİ `ExitForensicsPanel` ("Çıkış Otopsisi": 3 maliyet kartı + TF×neden $ çapraz tablo "tahmini" rozetiyle + capture trend + dürüstlük satırı, frontend HESAP YAPMAZ); TfTargetsPanel coverage çipleri + flag rozetleri; CockpitView grup 03 yeni adım | 2026-07-03 çıkış denetimi | ✅ (2026-07-03) contract-first (openapi.yaml → codegen, ratchet geçer); canlı 200 doğrulandı | 🟢 | E |
| E-4 | Girdi hijyeni `TF_TARGET_AUTO_ONLY` (env, DEFAULT OFF = bayt-aynı): ON → `tf_target_trainer.train()` VE `entry_exit_quality.report()` dataset'i yalnız `cohorts.classify()==AUTO` (verified MANUEL işlemler geometri öğrenmesine/çıkış-kalite hükümlerine sızmaz — TF kalibrasyonunda kapatılan deliğin aynısı, tek flag iki tüketici); `audit_note` `dataset=auto_cohort\|verified` damgalı | 2026-07-03 çıkış denetimi (kod teyidi: tf_target_trainer.py + entry_exit_quality.py yalnız data_verified filtreliyordu) | ✅ (2026-07-03) OFF bayt-uyum bekçi testi; apply yolu değişmez (±%15 bant + guardrail + tf_target_rollback zaten kapsar). AKTİVASYON BEKLİYOR (rollout: shadow sonrası İLK açılacak flag) | 🟡 | E |
| E-5 | Oransal nudge adımı `EXIT_FORENSICS_NUDGE` (env, DEFAULT OFF = sabit ±%10 bayt-aynı): ON → `step = 0.05 + 0.10×şiddet`, klamp [0.05, 0.15] — tavan AUTO_APPLY_BAND_PCT'ye eşit, hibrit-kapı semantiği yapısal korunur; şiddet önce `exit_forensics.trainer_evidence()` (sl_roundtrip_share / timestop_missed_ratio / trailing_giveback_ratio), yoksa TfStats fallback (ikisi de ölçüm, sahtelik yok); `TfNudge.step_source`+`evidence` additive (onay kaydı + panelde) | 2026-07-03 çıkış denetimi | ✅ (2026-07-03) OFF sabit-0.10 regresyon bekçisi + klamp/fallback/bant-sınırı testleri. AKTİVASYON BEKLİYOR (rollout: EN SON, E-4 + TF_TARGET_EDGE_GATE'ten sonra) | 🟡 | E |
| E-6 | Aktivasyon izleme deliği kapatma: E flag'leri (`TF_TARGET_AUTO_ONLY`, `TF_TARGET_EDGE_GATE`, `EXIT_FORENSICS_NUDGE`) `activation_watchdog.REGISTRY`'de YOKtu — açılınca baseline damgalanmıyor, bozulma izlenmiyordu. Diğer 16 owner-flag gibi kaydedildi. KRİTİK SIRALAMA: watchdog yalnız `last_seen=False→ON` geçişinde arm olur; bu yüzden kayıt (bu commit, flag'ler OFF) ile aktivasyon (E-4, ayrı commit) AYRI deploy olmalı — yoksa ilk görüşte zaten-ON sayılıp monitör kurulmaz | 2026-07-03 rapor-üstü denetim (checker kör-nokta bulgusu) | ✅ (2026-07-03) 3 REGISTRY satırı + `test_tf_target_auto_only_arms_on_activation` + registry-kapsama testi; conftest EDGE_GATE delenv | 🟢 | E |
| E-7 | Çıkış Otopsisi $ güvenilirlik göstergesi: `dataset_health.coverage.size_usd_pct` — outcome'ların kaçında `size_usd` damgalı (düşükse forensics dolar rakamları çoğunlukla notional-çıkarım vekili). Rapor "Exit Coverage Monitor" önerisinin yeni panel yerine mevcut Veri Sağlığı paneline additive çözümü | 2026-07-03 rapor-üstü denetim | ✅ (2026-07-03) coverage'a additive alan + DatasetHealthPanel "$ boyutlu (çıkış tahmini)" çubuğu (friendly tip elle, dataset-health kontratsız) + test | 🟢 | E |
| E-8 | Flag sapma guard'ı: `scripts/flag-sync-check.sh` lokal `.env` ↔ AWS `deploy-from-github.sh` ensure_env/set_env davranış-flag'i SAPMASINI görünür kılar (owner kuralı "lokal+AWS her zaman senkron"; ensure_env yalnız-yoksa-ekle olduğu için sapma mümkündü). `test_flag_sync`: deploy'un set ettiği her flag checker SYNC_FLAGS'te tanınmalı (CI'da kör-nokta guard'ı; lokal .env gitignore → CI göremez) | 2026-07-03 rapor önerisi (Flag Sync) | ✅ (2026-07-03) script + 3 test; canlı çalıştı (11 flag, sapma yok) | 🟢 | E |

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
