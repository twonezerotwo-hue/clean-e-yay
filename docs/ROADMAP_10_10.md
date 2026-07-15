# 10/10 YOL HARİTASI + DEVİR DOSYASI (2026-07-15)

> **Bu dosya devir içindir.** Token biten asistanın yerine gelen asistan bunu
> sıfır bağlamla okuyup devam edebilir. TEK KAYNAK: bu dosya + `docs/AUDIT_ROADMAP.md`
> (M-serisi satırları) + `MEMORY.md`. Önce `CLAUDE.md`'yi oku (değişmez kurallar).

## 0. Yeni asistan için 60 saniyelik oryantasyon

- **Sistem:** paper-trading karar-DESTEK sistemi (otonom motor DEĞİL). `PAPER_ONLY`/
  `NO_EXECUTION` yapısal. 3 süreç: API (`apps/api`), tick_worker (30sn), learning_worker.
- **Çalışma disiplini (kural özeti — tamamı CLAUDE.md):** additive-only · gölge-önce
  (yeni fikir → flag default KAPALI, açıkken bayt-aynı) · 5y çok-rejim backtest ŞART ·
  shadow→yön terfisi CP5 kırmızı çizgi (owner onayı) · düz dille raporla · lokal+AWS
  her zaman senkron (YAML flag git taşır; env flag scripts/deploy-from-github.sh) ·
  efektif config'i oku (dataclass=False çoğu zaman YAML'da ezili) · roadmap
  dilimlerinde OTOMATİK commit+push (push öncesi TAM test ŞART) · PowerShell'e ASCII-dışı
  YAZMA · yeni env-flag → conftest delenv + flag-sync-check.
- **Test:** `.venv\Scripts\python.exe -m pytest -q --basetemp=.pytest_tmp` (Windows
  Temp kilidi workaround). Baseline bugün **2000 test yeşil**. Ruff: 40 ESKİ hata var,
  YENİ ekleme (yalnız değişen dosyalarını `ruff check` et).
- **Commit mesajı ASCII-dışı içeriyorsa** dosyadan ver: `git commit -F <dosya>`
  (PowerShell here-string apostrof/tire'de bozuluyor). Sonuna:
  `Co-Authored-By: Claude <noreply@anthropic.com>`.
- **Deploy senkron:** push sonrası `bash scripts/deploy-status.sh` "SENKRON" diyene
  kadar bekle (until-döngü, ~3dk). Config-flag aktivasyonu LOKAL worker restart ister
  (lru_cache) — WMI ile: `start-dashboard.ps1`'i Win32_Process.Create ile başlat
  (sandbox tool-call çocukları ölür). AWS deploy worker'ları kendi restart eder.
- **Makro backtest tezgâhı:** `python -m packages.learning.macro_backtest --horizon 10`
  (BAR_HISTORY_ENABLED=1 + PYTHONPATH=. gerekir). Aday formül/ağırlık buraya eklenir.

## 1. BUGÜN NEREDEYIZ (2026-07-15 gece)

16+ commit'lik dış-denetim düzeltme dalgası bitti. **Genel karne 4.5 → 7/10.**
Son commit `224b26a` (M24 aktivasyon dalgası-2). CANLI olan yeni davranışlar:

- `fundamental_v4=true` (v4.1 yüzdelik momentum; İKİ tüketici: fundamental modülü +
  rejim Likidite katmanı). Canlı: skor 3.0, rejim OFFENSIVE→NEUTRAL (dürüst sıkılaşma).
- `touche_speaker_tf_only=true` (16 kopya-yön hücresi kapandı).
- `news_abstain=true` (40 sahte-nötr oy kesildi).
- `min_module_coverage=0.60` · `block_stale_ohlcv_for_trade=true`.
- `quantum_regime_gate=true` (NEUTRAL'da quantum düşer — canlı 55/55) ·
  `dominant_directional=true` · `regime.hysteresis_band=3.0`.
- Arşiv bekçisi `macro_backfill.ensure_depth` (learning worker sığ makro arşivi 5y
  doldurur — AWS kendi doldurur, kural-6).

## 2. EN KRİTİK GÖLGE DERSİ — touche v4 ALARM (öncelik-0 karar)

`tf_scoring_race` karnesi (canlı, `data/runtime/tf_scoring_race_report.json`, 124 çözülmüş):

| Motor | decisive | hit_rate | avg_return |
|---|---:|---:|---:|
| **touche v4 (CANLI)** | 18 | **%16.7** | **−1.41%** |
| touche_backup | 25 | %36 | −0.03% |
| **zemin motor** | 95 | **%52.6** | **+0.59%** |

`beats_backup: false`, `race_status: COLLECTING`. Kural: "V4_BEHIND → owner geri
alır." **KARAR (owner onayı bekliyor → owner "başla" dedi, öneri uygulanıyor):
`consensus.touche_v4: false`** — teknik oy zemin motora döner; v4 gölgede yarışmaya
devam eder, karne V4_AHEAD derse tekrar açılır. Örnek hâlâ COLLECTING → kesin değil
ama bu tabloyla canlıda tutmak kural #3'e aykırı.

## 3. GÖLGE ENVANTERİ — 22 kalem, hüküm sınıfları

### 🟢 DALGA-1: AÇ (kanıt hazır; hepsi yalnız-KISAR/BLOKLAR — işlem AÇTIRMAZ)
Sıra: reentry_guard İLK (owner'ın 1 numaralı derdi), sonra diğerleri tek tek
(her biri: flag → iki ortam → worker restart → ilk kanıt kontrolü → sonraki).
| Flag (config yolu) | Gölge kanıtı |
|---|---|
| `reentry_guard.enabled` | Kârda kapat→30sn geri-gir problemi; recent_trades'ten türetilir; manuel MUAF |
| `technical.htf_alignment` (T-1) — **ZATEN AÇIK** (satır ~1049, teyit et) | bloklanan 15m'in %87 avoided_loss |
| Korelasyon vetosu D (`risk_gates.correlation_*` / decision engine) | 5/5 yıl backtest+; yalnız BLOKLAR |
| `sizing_layers.brake` (P3, satır ~745) | maks düşüş −293→−213; yalnız KISAR |
| `strategy_shaping` (satır ~591) | backtest'li guardrail [0.5,1.5]; yalnız KISAR |
| `quantum_dampen` (satır ~781) | kanıt İNCE n=21 → dalga sonu, ayrı izleme |

### 🟡 DALGA-2: KANIT-KAPILI AÇ
| Flag | Kapı |
|---|---|
| `shadow.affect_decision` | ERKEN aç — yeni zinciri yalnız manual_ready kuyruğuna (oto-açılış YOK); CP5 forward kanıtını bugünden biriktirir |
| `LEARNING_ADVISOR_APPLY` (env) | context.py bağlama bitince (Faz 3 başı); yalnız kısar |
| T-2/3/4 `technical.elliott_confluence`/`sr_strength`/`candle_confirm` | ≥N log gözlem + karşıt-örnek (Faz 6) |
| `WEIGHT_REGIME_FILTER`+`MISTAKE_MEMORY_V2` (env) | signal_quality FLAT diyor; sözleşme sonrası DISCRIMINATES çıkarsa |
| `EXIT_FORENSICS_NUDGE` (env) | E-zinciri sonu + EDGE_GATE kararı |

### 🔴 SİL / ONAR (Faz 1)
| Kalem | Aksiyon |
|---|---|
| `consensus.fundamental_v3` (+flag+test) | ÇÜRÜDÜ (5y backtest TERS) → SİL |
| `regime.liquidity_momentum` (config satır ~209) | ÖLÜ ANAHTAR — M21'de okuyucusu söküldü, anahtar kaldı → SİL |
| `packages/decision/gates.py` (102 satır) | HİÇ import edilmiyor (hayalet) → SİL |
| `packages/data/providers/price/mock.py` | referanssız → SİL (registry'de fallback_to_mock:false teyit et) |
| **`packages/learning/threshold_trainer.py` (222 satır)** | `.env`'de `THRESHOLD_AUTOTUNE=1` YANIYOR ama trainer'ı hiçbir yer çağırmıyor (kablo kopuk CP4). **Owner kararı:** geri-kablola (edge-gate+rollback niyeti vardı) VEYA flag+modül birlikte sök. Güvenli default: SÖK (otonom config-mutator geri-kablolaması kendi doğrulamasını ister) |
| CPI (classifier ~189 okunuyor, skora girmiyor) | likidite eksenine bağla (tezgâh testi) VEYA çıkar |
| catalyst event-study (kopuk) | news güven çarpanına bağla VEYA emekli et |
| decision-log config/ağırlık SHA damgası | EKLE (yeniden-üretilebilirlik) |
| zone artifact yaş kontrolü (v4 okumasında yok) | EKLE |

### ⚪ TASARIM GEREĞİ GÖLGE (borç DEĞİL — açma)
zone_plan/zone_proposer/zone_influence (owner çizim-grameri, makine SEÇMEZ) ·
capital_flow (terfi çürüdü, tezgâh girdisi) · blend_counterfactual (öğrenme saflığı) ·
EDGE_GATE=0 (owner kararı) · tezgâh/analiz araçları.

### KARAR #4: `enforce_decision_usage`
Uygulamayı açmak yerine **registry ETİKETİNİ güncelle** (news artık abstain'li,
quantum kapılı — `config/source_registry_v1.0.yaml` etiketleri gerçeği yansıtmıyor).

## 4. FAZLI PLAN (bağımlılık sıralı; her faz kanıt-kapılı + tek-satır geri-alma)

- **FAZ 0** (bu hafta): M24 watchdog izleme + **DALGA-1 aktivasyonları** +
  `touche_v4:false` + pazartesi stale-blok kontrolü (16 blok kapalı-piyasa mı?)
- **FAZ 1** (1 oturum): SİL listesi + CPI/catalyst bağla + zone-yaş + SHA damgası
- **FAZ 2**: veri omurgası — US02Y(FRED) + MOVE endeksi + CPI-sürpriz eksen +
  DQS çok-eksen GATE (M14 observe→eşik) + kapalı-piyasa/stale ayrımı + bekçiye ekle +
  `shadow.affect_decision` erken açılış
- **FAZ 3** (en büyük, 2-3 oturum): SKOR SÖZLEŞMESİ v2 — her modül {lean,güven,kapsama,
  durum,kanıt-id}; birleşim Σ(lean·w·güven·kapsama)/Σ(w·güven·kapsama); **sentinel-veto
  taşınması** (yön havuzundan çıkar, risk çifte-cezası tekilleşir, VIX tek yerde);
  confluence v2 (aynı-kaynak tek oy); news güven çarpanı + negation; advisor bağla→aç;
  WRF/MM_V2 yeniden-ölçüm. Kabul: 5y tezgâh replay + 2 hafta canlı gölge yan yana.
- **FAZ 4**: rejim v2 (global/asset ayrımı; self-amp kesimi) + kanıtlı ağırlıklar
  (fundamental↑ + CRISIS sentinel yeniden-ölçüm; dar-bant auto-apply/rollback REUSE)
- **FAZ 5** (CP5 kırmızı çizgi): decide_matrix emekliliği — shadow resolver zinciri
  (setup/alignment/conflict_resolver HAZIR, shadow_activation kablosu canlı) terfi eder.
  Kapı: `promotion_criteria` (≥200 eşleşme + ≥30 çözüm + Wilson>0.5) — REUSE, yeni yok.
- **FAZ 6** (paralel): touche derinliği — per-TF artifact + v4 formül revizyonu +
  race karnesi hükmüyle v4 geri-dönüş sınavı + T-2/3/4 aktivasyon

**Karne projeksiyonu:** F1-2→7.5 · F3-4→8.5 · F5-6→9.5-10.

## 5. İLERLEME KAYDI (her dilim burada güncellenir — devir için)

- [x] 2026-07-15: Devir dosyası yazıldı. touche_v4 alarmı tespit. Dalga-1 başlıyor.
- [x] 2026-07-15: **touche_v4:false** (race V4_BEHIND) + **reentry_guard:true**
      (owner #1 problem) CANLI. 2000 test yeşil. Commit sırada.
- [x] 2026-07-15: Dalga-1 TAMAMLANDI (teyit + düzeltmelerle):
      - `htf_alignment` ZATEN CANLI (2026-07-04) — teyit edildi
      - `correlation_veto` (D) ZATEN CANLI (2026-07-10) — teyit edildi
      - `sizing_layers.brake` AÇILDI (yalnız kısar, ≥10 örnek kendini-korur)
      - **RECLASSIFY → Dalga-2 (körlemesine açılmadı, gerekçeli):**
        · `strategy_shaping`: profil trail:1.25 (gevşek) exit_backtest "trail SIK"
          bulgusuyla ÇELİŞİR → önce UZLAŞTIRMA (E-9 ile tutarlı profil), sonra aç
        · `quantum_dampen`: kanıt ince (n=21) + artık quantum_regime_gate'le üst
          üste biner (quantum çoğu NEUTRAL hücrede zaten düşüyor) → ayrı izleme
- [x] 2026-07-15: FAZ 1 SİL turu — **KRİTİK DÜZELTME: orphan taraması 3 YANLIŞ
      POZİTİF verdi** (bundled import'ları regex kaçırdı). gates.py CANLI
      (tick_worker:290 apply_gates), price/mock.py CANLI (price provider), 
      threshold_trainer.py CANLI (learning_worker:388 train() + THRESHOLD_AUTOTUNE=1
      aktif!) — ÜÇÜ DE SİLİNMEDİ. Gerçek silme 2 kaleme indi:
      · `consensus.fundamental_v3` SÖKÜLDÜ (engine _fundamental_v3/_v3_enabled +
        merdiven + observe + config flag + watchdog REGISTRY + 4 test; 5y tezgâh
        çürüttü). macro_backtest fund_v3 analiz-referansı olarak KALDI.
      · ölü `regime.liquidity_momentum` config anahtarı SÖKÜLDÜ (okuyucu M21'de
        consensus.fundamental_v4'e taşınmıştı). 1996 test yeşil.
      DERS: orphan-scan regex güvenilmez; her silme "grep apply_X çağrısı" ile teyit.
- [x] 2026-07-15: decision-log config SHA damgası (yeniden-üretilebilirlik denetim
      bulgusu) — `loader.config_provenance()` {weights_version, weights_sha,
      thresholds_sha, manifest_sha}; açılışta Trade'e damgalanır (open_config_
      provenance), kapanışta decision_log.opening_signal.config_provenance'a yazılır.
      Legacy geriye-uyumlu (None). 2000 test.
- [x] 2026-07-15: zone artifact yaş kontrolü (denetim bulgusu: v4 bölge
      artifact'ını yaş-kontrolsüz okuyordu) — `zone_proposer.load_fresh(max_age)`
      + `fresh_zones_by_symbol()`; 2 günden eski bölge KARAR/SKOR beslemez
      (tf_scoring_shadow + risk.zone_influence bağlandı). Görüntü yolu (_load)
      yaş-kontrolsüz kalır (stale gösterip uyarabilsin). 2005 test.
- [x] 2026-07-15: FAZ 1 SON KALEM — **çerçeve düzeltildi (ikisi de ölü DEĞİL):**
      · **CPI**: arşivi YOK (yalnız canlı FRED) → 5y tezgâhta ölçülemez; skorlama
        FAZ-2 işi (FRED backfill gerekir). Evidence'ta gösteriliyordu (şeffaflık)
        ama "kullanılıyor" yanılsaması yaratıyordu (denetim) → etiket "(gösterim;
        skora girmez)" ile dürüstleştirildi. SİLİNMEDİ (gösterim legit).
      · **catalyst**: SİLİNMEDİ — CANLI ve DOĞRU rolde: catalyst_risk.assess
        işlemleri BLOKLUYOR (engine:796) + event_risk kapısı. "Edge beslemiyor"
        bulgusu YÖN-edge içindi; olay-catalyst'i yön değil RİSK gate'i beslemeli
        (CPI açıklamasına trade açmaz, gate'lersin) — zaten doğru. Ek iş YOK.
      **FAZ 1 KAPANDI.** DERS: "yarım-inşa" sanılan iki kalem aslında doğru-sınırlı.
- [ ] FAZ 2: veri omurgası — US02Y(FRED) eğri ekseni + MOVE endeksi (sentinel
      kripto-dışı stres) + CPI-skorlama (FRED backfill sonrası tezgâh) + DQS
      çok-eksen GATE + kapalı-piyasa/stale ayrımı + shadow.affect_decision erken aç
- [ ] Faz 1 SİL listesi
- [ ] (sonrası yukarıdaki fazlar)

> Yeni asistan: bir dilim bitince bu listeyi işaretle + `docs/AUDIT_ROADMAP.md`'ye
> M-satırı ekle + commit+push + deploy-senkron bekle + lokal worker restart.
