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
| 4 Haber | 6 | 10 | S1-1 GDELT dürüst degraded (tek kanala düşüş görünür). 10/10 = ek doğrulanmış haber kaynağı (RSS feed genişletme) VEYA GDELT'e alternatif erişim — **YENİ İŞ, henüz planlanmadı** (owner ağ-erişim kararı: bu makineden GDELT/Deribit bloklu, AWS'ten erişilebilir olabilir — kontrol edilmeli) | ⬜ N1 (aşağıda) |
| 1 Veri toplama | 7 | 10 | Haber (kat 4) + S1-4 opsiyonel-sağlayıcı ayrımı (gerçek arıza görünür). 10/10 = options ETH/BTC erişimi (Deribit bloklu) için fallback veya AWS-taraflı çekim; N1 ile aynı ağ-erişim kararı | ⬜ N1 |
| 11 ÇIKIŞLAR | 4 | 10 | **FAZ-3 (en büyük $ kaçağı ~$2.4k):** partial_tp shadow kanıtı birikince AÇ (şu an n=2 uplift −$16, YETERSİZ — 🔴 kural). Yardımcı: TF_TARGET_TRAIL_AUTOTUNE zaten AÇIK (trailing mesafesini capture'dan öğrenir). 10/10 = partial_tp AÇIK + EXIT_FORENSICS_NUDGE AÇIK (oransal düzeltme) | ⏳ FAZ-3 kanıt-bekliyor |
| 7 Konsensüs+ağırlık | 6 | 10 | **FAZ-4 (sinyal kalitesi):** skorlar iyi/kötü işlemi ayıramıyor (katkı kazanan≈kaybeden). WEIGHT_REGIME_FILTER (rejim-bazlı eğitim) + MISTAKE_MEMORY_V2 (Wilson-sınırlı hata hafızası) AÇ. 10/10 = ağırlık trainer'ın rejim-ayrık öğrenmesi + kalite ayrımı ölçülür | ⬜ FAZ-4 |
| 6 Quantum | 6 | 10 | FAZ-4 kapsamında: ağırlık trainer quantum'un gerçek katkısını ölçüp ağırlığını rejim-bazlı ayarlar (şu an sabit ~%10-15). 10/10 = etkisi veriyle doğrulanmış ağırlık | ⬜ FAZ-4 |
| 3 Makro (fundamental) | 7 | 10 | Çifte-sayım çözüldü (v2 AÇIK). 10/10 = FRED kesintisinde katman-düşürme (regime.drop_unavailable_layers AÇIK) + makro veri kanıtının ağırlıkta ölçülmesi (FAZ-4) | 🔶 büyük kısmı AÇIK |
| 5 Sentinel | 7 | 10 | Çok-girdili kompozit AÇIK (v2). 10/10 = options-stres girdisi gerçek Deribit verisiyle (şu an bloklu → N1); kompozit tam beslenince | 🔶 N1'e bağlı |
| 2 Teknik (touche) | 8 | 10 | **FAZ-5:** T-1 htf_alignment AÇIK (S3-2). Kalan T-2 (Elliott×Fib), T-3 (S/R gücü), T-4 (mum teyidi) shadow kanıtı birikince tek tek AÇ. 10/10 = dördü de aktif + kanıtla doğrulanmış | 🔶 T-1 AÇIK; T-2/3/4 shadow |
| 8 Kalibrasyon | 8 | 10 | tf_platt AÇIK + guardrail sıkı (0.10). 10/10 = reliability_bins çifte-sayım fix (denetim bulgusu #3) + TF başına yeterli örnekle fit doğrulanır | 🔶 küçük fix + veri |
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
- **FAZ-3 — Çıkış kalitesi (kat 11):** partial_tp shadow uplift kanıtı ≥N
  işlem birikince owner onayıyla AÇ. En büyük $ kaçağı ama 🔴 kanıtsız açılmaz.
- **FAZ-4 — Sinyal kalitesi (kat 6/7):** WEIGHT_REGIME_FILTER +
  MISTAKE_MEMORY_V2 tek tek (bekleme penceresiyle). Skorların iyi/kötü
  ayrımını ölçmek için modül-katkı analizi (rapor madde 4.5) izlenmeli.
- **FAZ-5 — TA genişletme (kat 2):** T-2/T-3/T-4 shadow kanıtı sırayla.
- **Küçük fix'ler:** reliability_bins çifte-sayım (kat 8), FE degraded/coverage
  çipleri (kat 15), denetim bulguları #1/#2/#4 (confluence yön, penalty taban,
  mfe_r clamp — 2026-07-02'de raporlanmış, owner onayı bekliyor).

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
