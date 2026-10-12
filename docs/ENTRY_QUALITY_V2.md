# Giriş kalitesi v2 — YÖN ≠ GİRİŞ ZAMANLAMASI

Bu dosya kalıcı rehberdir (kod nasıl çalışır, nasıl okunur, nasıl yeniden ölçülür). Bugünkü
bayrak değeri burada **yazılmaz**: `config/thresholds_v1.0.yaml → entry_quality_v2.mode`
(`off` | `shadow` | `active`). Ölçüm kanıtı: `docs/evidence/entry_quality_v2/`.

## Düz dille: ne işe yarıyor

Konsensüs skoru "hangi yön tercih ediliyor"u söyler (ör. SHORT). Bu **hemen aç** demek
değildir. Fiyat düşüşün dibindeyse ve her şey aşırı satımsa, doğru yönde bile olsa o anki
giriş kötü olabilir. Yeni katman bu soruyu ayrıca sorar: *"Yön doğru olsa bile şimdi girmek
mantıklı mı?"* Cevap kötüyse karar **WAIT** (hold) olur. Kötü giriş **asla** zıt yöne
çevrilmez (kötü SHORT → LONG yok), boyut hiçbir zaman artmaz, RiskGate'e dokunulmaz.

## Karar akışı (nerede duruyor)

```
snapshot (pipeline.build_snapshot)
  └─ entry_contexts[sembol][tf]  ← entry_context.build(bars)   (yalnız mode != off)
konsensüs skoru → _candidate_from_score → aday (open_long / open_short / hold)
decide_for_symbol:
  RiskGate (KILL_SWITCH / RISK_REDUCE / NO_POSITION_INCREASE)  ← ÖNCE, değişmedi
  → data-policy (bayat OHLCV) → eşik geçilmedi mi? → hold
  → GİRİŞ KALİTESİ v2  (entry_quality.assess)                  ← yeni, yalnız kısıtlar
  → güven tabanı → EV → mistake memory → korelasyon/konsantrasyon → … → boyut
```

Çıktı `TradeDecision.entry_quality_report` ve decision-matrix hücresinde `entry_quality`
(yalnız mode != off iken; kapalıyken hücre bayt-aynı). Alanlar: `entry_quality` (0–1),
`reversal_risk` (0–1), `verdict` (ok/reduce/wait), `size_factor` (≤ 1), `reasons`, `terms`,
`events`, `old_action`, `new_action`, `applied`.

## Modüller

| Modül | Rol |
| --- | --- |
| `packages/scoring/entry_context.py` | Yön-bağımsız bağlam: aralık konumu (20/60/120), ATR-normalize EMA20/EMA50/VWAP uzaklığı, RSI, Bollinger %b, 5-bar hareket, yönlü mum serisi, hacim/ATR genişlemesi, olaylar |
| `packages/scoring/reversal_events.py` | Dönüş **olayları** (durum değil): CHoCH, süpürme/BOS başarısızlığı, RSI uyumsuzluğu, red mumu, geçerli 0-2 kırılımı, climax. Olay başına yön, bar, ts, güç, güven, yaş; yarı-ömürle deterministik sönüm, 3 yarı-ömürde ölür |
| `packages/scoring/entry_quality.py` | Saf değerlendirme: `kalite = 1 − chase × (loc_floor + (1−loc_floor) × loc)`; dönüş riski = tür başına en güçlü sönümlü olay, noisy-OR |
| `packages/signals/market_structure.py` | `break_events` / `swing_levels`: CHoCH/BOS'u olaya çevirir (look-ahead yok: olay, referans pivot teyit edilmeden damgalanmaz) |
| `packages/scoring/tf_scoring_v4.py` | `rsi_divergence_events` (+ lean eşdeğer), `elliott_lean_canonical` |

**Aralık ucu tek başına ceza değildir** (güçlü trendde fiyat uzun süre uçta kalır ve devam
işlemleri çalışır): ceza için uzamayı *kanıtlayan* terimler gerekir (ATR-normalize ortalama
uzaklığı, RSI bandı, Bollinger dışı, 5-bar hareket, ardışık impulsive mum).

## 0-2 düzeltmesi (ayrı bayrak: `zero_two_canonical`)

`tf_scoring_v4.elliott_lean` `zero_two.find_setups(...)[-1]` alıyor ve **geçerliliği
kontrol etmiyordu** (wave1_clean / IPTAL_DALGA1 / IPTAL_DALGA3): docstring "geçerli" diyor,
kod geometrik adayı alıyor. Ölçüm: lens 4h satırlarının ~%58'inde aktif, aktifken ~%49'u
owner'ın kendi kuralına göre **geçersiz** setup (train+val %49.6, test %48.5).
`elliott_lean_canonical` tek geçerlilik kaynağını (`zero_two.analyze`) kullanır; geçersiz →
0, çizgi kapanışla kırıldıysa → 0, P2'den 60 bar sonra → 0 (doğrusal sönüm). Canlı
davranışı değiştirdiği için **varsayılan kapalı**; ölçümde performans kanıtı yok (aşağıda),
bu bir doğruluk düzeltmesidir.

## Ölçüm sonucu (özet; ayrıntı `docs/evidence/entry_quality_v2/`)

Veri: QuantConnect Lean örnekleri (kamuya açık GitHub) — 15 enstrüman (hisse/ETF, FX, altın,
BTC), 1h/4h/1d, 1998–2021; sahibin BAR_HISTORY arşivi buluttan erişilemedi. Her bar yalnız o
ana kadarki veriyle skorlandı (look-ahead yok). Kronolojik train %50 / validation %20 / test
%30 (sınırlarda 20 bar purge); parametre seçimi yalnız train→validation; test dondurulmuş
config ile **tek sefer** okundu (`test_run.lock`).

| Soru | Bulgu |
| --- | --- |
| Short'lar dipte, long'lar tepede mi açılıyor? | **Evet (yapısal).** Short'ların %45'i 60-bar aralığın alt %20'sinde (taban %19), long'ların %51–53'ü üst %20'de (taban %28) — her TF ve sınıfta |
| Bu bedel ödetiyor mu? | **Havuzlu örnekte hayır.** Aynı konumdaki rastgele barlara göre kenar ≈ 0 (short alt %20: +%0.004; long üst %20: +%0.002) |
| Yön skoru tahmin gücü? | Havuzlu örnekte ~yazı-tura: IC 0.007 (train+val), −0.017 (test); yön isabeti %50.3 / %49.3 |
| Dönüm noktalarında yanlış tarafta mı? | **Evet.** Gerçek diplerin %59'unda ESKİ short açık, gerçek tepelerin %74'ünde long açık (test); YENİ: %43 / %52 |
| Momentum çifte sayımı | RSI↔EMA20-uzaklığı korelasyonu 0.98, RSI↔MACD 0.61, çekirdek↔nihai skor 0.98; ancak RSI/MACD çıkarılınca IC değişmiyor (Δ≈0). EMA dizilimi dışında kenar taşıyan bileşen yok ve o da tutarsız (train+val ΔIC −0.007, test +0.013) |
| Korumalar | Yön sınıfını %2'de değiştiriyor, hiç yön çevirmiyor, çıkarılınca IC değişmiyor — etkisiz |
| RSI lineer mi olmalı? | Bantlı/katlı varyantlar IC'yi değiştirmiyor. RSI<30 sonrası getiri işaret değiştirdi (train+val +%0.17…0.25, test −%0.29…−0.41) → kararlı bir ilişki yok |
| "Uzamış giriş kötüdür" varsayımı | Havuzlu IC |0.01|'in altında. Sınıfa göre: **endeks ETF'lerinde tutarlı negatif** (train/val −0.04…−0.055, test −0.008…−0.027), **petrol ETF'inde tersi** (pozitif, devam), FX/altın/tek hisse ≈ 0 |
| YENİ vs ESKİ (test, yürütme: SL/TP/zaman stopu/ücret) | İşlem başına net R −0.073 → −0.056, maks. DD 664R → 454R, işlem 8564 → 7775; sinyal düzeyi z −0.009 → −0.012 |
| Kabul ölçütleri (9) | **6 geçti, 3 kaldı:** sinyal z'si, trend yönündeki iyi sinyallerin korunumu (%78 < %85), enstrüman tutarlılığı (11/31 < %60) |

**Karar:** pooled kanıt `active` için yetmiyor → **terfi yok**; katman `shadow`'da çalışır
(karar değişmez, eski/yeni yan yana birikir). Canlı evren (BTC, ETH, XAU, XAG, BRENT) için
doğrudan kanıt yok (örnekte ETH/gümüş/Brent/kripto gün-içi yok) — gerçek kanıt shadow'dan ve
sahibin arşivinden gelir. `active`'e terfi CP5 kırmızı çizgisidir: owner onayı + canlı gölge
kanıtı.

Dürüst sınırlar: teknik oy tek başına simüle edildi (fundamental/haber/sentinel/quantum
modülleri geçmiş veri olmadığı için yok); v4'ün bölge merceği S/R vekiliyle; trailing stop
modellenmedi; maliyetler varsayım; satırlar örtüşüyor (t-istatistiği verilmedi); 4h hisse
çubukları seans başına 2 kutu.

## Shadow çıktısını okuma

`GET /api/v1/decision/matrix` hücrelerinde `entry_quality`; ayrıca her tick snapshot'ı
`causal_reconstruction.entry_contexts` taşır (tekrar oynatılabilir). Örn. "gölgede WAIT diyen
ama ESKİ'nin açtığı işlemler ileride kaybetti mi?" sorusu `decision_log` + snapshot'lardan
cevaplanır. Aktivasyondan önce önerilen kanıt: ≥ 30 gün, sembol × TF başına yeterli örnek,
bloklanan işlemlerin kapanış-R'si ile korunanların kıyası.

## Yeniden ölçme (kendi arşivinde)

```bash
python -m scripts.score_diag.run extract  --bar-history data/runtime/bar_history --out OUT
python -m scripts.score_diag.run diagnose --bar-history data/runtime/bar_history --sig OUT --out R
python -m scripts.score_diag.run tune     --sig OUT --out R        # TRAIN tara, VALIDATION seç, config'i dondur
python -m scripts.score_diag.run validate --bar-history data/runtime/bar_history --sig OUT --out R
python -m scripts.score_diag.run final    --bar-history data/runtime/bar_history --sig OUT --out R   # TEST: tek sefer
```

Kamuya açık örnek veri için `fetch` + `extract` (bar-history vermeden). `final` yalnız
dondurulmuş config varken çalışır ve `test_run.lock` yazar; ikinci kez çalışmayı reddeder.

## Geri alma

`entry_quality_v2.mode: "off"` (tek satır, git iki ortama taşır; supervisor yeniden başlar):
hiçbir bağlam hesaplanmaz, matrix hücresi ve karar bayt-aynıdır (golden replay korur).
