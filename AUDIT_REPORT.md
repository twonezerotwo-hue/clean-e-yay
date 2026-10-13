# AUDIT_REPORT — Clean E-yAy salt-okur kod denetimi

| | |
| --- | --- |
| Tarih | 2026-10-11 |
| Denetlenen commit | `61ef58c` (`feat(heart): Yeni Asset / Emtia Firsatlari paneli …`) |
| Kapsam | `packages/` (31 paket, ~57,7 bin satır), `apps/` (api · tick_worker · learning_worker · supervisor · web), `tests/` (230 dosya, ~34,9 bin satır), `contracts/`, `config/`, CI |
| Yöntem | Kod okuma + statik analiz (AST import grafiği, referans sayımı, vulture, ruff, tsc) + komut koşuları + **küçük izole deneyler** (aşağıda "Kanıt: ✔ repro") |
| Değişen dosya | Yalnız bu rapor. Kaynak ağaca dokunulmadı; tüm koşular repo kopyasında (geçici dizin) yapıldı. |
| İşaret | **BELİRSİZ** = kanıtlayamadım / niyet repodan okunamıyor. Tahmin gerçek gibi yazılmadı. |
| Durum notu (2026-10-13) | Bu rapor `61ef58c` anının görüntüsüdür. Sonradan main'e giren değişiklikler (ör. PR #58 `fix: close p0 risk and manual order bypasses`) bazı bulguları kapatmış olabilir; raporun bulguları yeniden doğrulanmadı. Güncel durum için `docs/STATE.md` esastır. |

**Önemli okuma notu.** İstenen üç dosya (`docs/AGENT_CONTEXT.md`, `docs/CURRENT_STATE.md`, `.tasks/NEXT_TASK.md`)
artık kökte yok; `docs/archive/` altına taşınmış ve **2026-07 durumunu** anlatıyor ("Backend FREEZE", "pytest 419/419").
Güncel kaynaklar `CLAUDE.md`, `docs/STATE.md`, `docs/ROADMAP.md` ("temizlik dönemi 2026-10"). Bu raporda arşivdeki
belgeler yalnız tarihçe olarak kullanıldı; `docs/SAFETY_RULES.md`, `docs/DASHBOARD_RULES.md` ve `ARCHITECTURE.md` güncel
kabul edildi (ARCHITECTURE'ın bazı bölümleri bayat — bkz. §2.6).

**Seviye tanımı.** **P0** = değişmez kural / owner kararıyla çelişen, deterministik, canlıda tetiklenebilir → freeze'de bile
hotfix adayı. **P1** = yanlış ya da yanıltıcı davranış, güvenlik katmanında zayıflık; koşullu ya da workaround'lu.
**P2** = gizli / düşük etki / hijyen.

---

## İçindekiler

0. [Düz dille özet](#0-düz-dille-özet)
1. [Shadow task envanteri](#1-shadow-task-envanteri)
2. [Ölü kod ve mimari çöp](#2-ölü-kod-ve-mimari-çöp)
3. [Mantık hatası şüpheleri (P0 / P1 / P2)](#3-mantık-hatası-şüpheleri)
4. [Test boşlukları](#4-test-boşlukları)
5. [Frontend](#5-frontend)
6. [Mevcut durum — komut sonuçları](#6-mevcut-durum--komut-sonuçları)
7. [Önerilen iş sırası](#7-önerilen-iş-sırası)
- [Ek A — Değişmez kurallar kontrolü](#ek-a--değişmez-kurallar-kontrolü)
- [Ek B — Repro betikleri (özet)](#ek-b--repro-betikleri-özet)

---

## 0. Düz dille özet

**Genel resim.** Sistem sağlam görünüyor: 2220 test yeşil, lint temiz, API sözleşmesi ile TypeScript tipleri senkron,
karar matrisi "dondurulmuş" çıktıyla bayt-aynı, `make smoke` 8/8 geçti. Kodda broker / gerçek emir / `ccxt` yolu **yok**;
`/system/health` `paper_safe=true`, `no_execution=true` döndürüyor. RiskGate karar motorunda gerçekten **ilk** kapı.

**Ama okuma + küçük deneylerle şunları doğruladım:**

1. **Günlük zarar freni ertesi gün kalkmıyor (P0).** Sistem günde %2 zarar edince "bugün yeni pozisyon açma" diyor ve
   dokümana göre ertesi gün (UTC) kendiliğinden kalkması gerekiyor. Kodda "günün zararı" sayacı yalnızca bir pozisyon
   **kapanınca** sıfırlanıyor. Açık pozisyon kalmadıysa sayaç dünkü zararda takılı kalıyor, fren her tick yeniden kuruluyor
   ve owner'ın "halt reset"i de işe yaramıyor (deneyle doğrulandı). Sonuç: paper işlem tamamen duruyor.
2. **Sohbet kutusuna *soru* yazmak bile pozisyon açabiliyor (P0).** "ETH'de satış baskısı var mı, 2000 dolar pozisyon
   açsam ne olur?" cümlesi 2000 dolarlık bir **short emri** olarak ayrıştırılıyor. Üstelik cevap "…risk kapısını geçtim"
   diyor; oysa manuel emir yolu RiskGate'e hiç bakmıyor (KILL_SWITCH aktifken 20 000 dolarlık pozisyon açıldı).
3. **%8 düşüş freni "tüm pozisyonları kapatır" demesine rağmen kapatmıyor (P1).** Canlıda MTM (açık pozisyonlar dahil)
   düşüşü kontrolü açık; RiskGate "KILL_SWITCH" diyor ama pozisyonları kapatan mekanizma yalnızca *gerçekleşmiş* kayba
   bakıyor. Ayrıca %8 freninin owner reset'i, tepe değeri (peak) yeniden tabanlamadığı için bir sonraki tick'te
   fren tekrar kuruluyor.
4. **Hata anında "güvenli" değil "gevşek" davranan yerler (P1):** `NaN` bir boyut çarpanı pozisyonu **en büyük** boyuta
   (1,5×) çıkarıyor; yarım yazılmış `risk_halts.json` kalıcı KILL_SWITCH'i sessizce siliyor.
5. **Sohbetin "aktif ticket var mı" cevabı her zaman "yok" (P1)** — var olmayan bir değişkeni import ediyor; hata sessizce yutuluyor.
6. **Owner onay kuyruğu (`manual_ready`) görünmez ve süresiz (P1):** kuyruğa düşen adayları listeleyen/onaylayan bir
   ekran yok, süre sınırı yok; onaylanınca da zayıf sinyal tam boy (3,3×) açılıyor.
7. **Test düzeni canlı konfigürasyonu görmüyor:** `conftest` 21 YAML bayrağını + EV/Kelly kapısını varsayılan KAPALI pinliyor ve
   17 env bayrağını siliyor; yukarıdaki hataların çoğu tam bu boşluktan kaçtı. `packages/paper/position_ops.py` **%0**,
   `manual_order.py` **%36** kapsamda.
8. **Temizlik fırsatları:** 4 kullanılmayan FE dosyası, hiçbir FE dosyasının import etmediği 6369 satırlık "codegen"
   çıktısı (FE el yazması `api.ts` kullanıyor), tick'te her 30 sn çalışıp çıktısını kimsenin okumadığı "haber hazır
   pozisyon" hattı, 6 çağrısız fonksiyon, boş bir paket.

**Özet tablo** (ayrıntı §3):

| ID | Sev | Başlık | Kanıt |
| --- | --- | --- | --- |
| M-01 | **P0** | Günlük PnL UTC gün dönümünde sıfırlanmıyor → DAILY_LOSS halt'ı yeniden doğuyor, owner reset etkisiz | ✔ repro |
| M-02 | **P0** | Chat serbest metinden (soru dahil) pozisyon açıyor; "risk kapısını geçtim" yalanı | ✔ repro |
| M-03 | P1 | MTM drawdown: RiskGate KILL_SWITCH diyor, flatten/halt yok; API girdileri MTM'siz | ✔ repro |
| M-04 | P1 | MAX_DRAWDOWN owner reset'i peak'i tabanlamıyor → anında yeniden kuruluyor (owner kararı gerek) | ✔ repro |
| M-05 | P1 | Manuel market emri / bekleyen emir dolumu / flip / scale-in: RiskGate, DQS, pozisyon limiti, boyut tavanı dışı (owner kararı gerek) | ✔ repro |
| M-06 | P1 | `NaN`/`inf` boyut çarpanı → maksimum boyut (fail-open) | ✔ repro |
| M-07 | P1 | `risk_halts.json` atomik yazılmıyor; bozuk dosya → halt sessizce kayboluyor | ✔ repro |
| M-08 | P1 | Chat "ticket" cevabı hep boş (kırık import) | ✔ repro |
| M-09 | P1 | manual_ready onayı: kademe/güven kaybı (3,3× boyut), `data_verified=False`, eski fiyat yedeği | ✔ repro |
| M-10 | P1 | manual_ready kuyruğu: UI yok, TTL yok, `rejected_signals` hiç temizlenmiyor | kod + grep |
| M-11 … M-25 | P2 | scale-in ortalama fiyat, sıfır boyutlu kısmi kapanış, kilit içinde ağ, hayalet kapanış kaydı, state sıfırlama, zehirli pozisyon, … | bkz. §3.3 |

---

## 1. Shadow task envanteri

**Kapsam tanımı.** Kodda "shadow task" tek bir yapı değil. Burada iki zamanlayıcıdaki **her adım** listelendi:
tick worker (`apps/tick_worker/main.py`, her tick) ve learning worker (`apps/learning_worker/main.py::run_once`, her
`LEARNING_INTERVAL_SEC`=300 sn'de bir; çoğu adım kendi içinde interval-kapılı). Sınıf kolonu:

- **G** = gölge / salt-gözlem (karara yazmaz) · **C** = canlı karar/SL-TP/eşiği **etkiler** (gölge değil) ·
  **Y** = öneri / owner-onay hattı · **B** = bakım.
- "Efektif durum" = `config/thresholds_v1.0.yaml` (okundu) ve AWS için `scripts/deploy-from-github.sh` `ensure_env`/`set_env`
  satırları. **Lokal `.env` gitignored → lokal efektif değer BELİRSİZ.** Deploy'un set etmediği bayrakların AWS değeri de
  BELİRSİZ (AWS `.env` repodan okunamıyor).
- Satır numaraları: `Tanım` = fonksiyonun tanım satırı, `Çağıran` = worker içindeki çağrı satırı (commit `61ef58c`).

### 1.1 Tick worker adımları

| # | Görev | Sınıf | Tanım | Çağıran | Efektif durum | Çıktı → tüketen | Karar | Gerekçe |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| T-1 | `shadow.observe` + `shadow.record` | G→C | `packages/decision/shadow.py:519` | `tick_worker/main.py:556-566` | YAML `shadow: enabled=true, affect_decision=true, manual_ready_only=true` | `SHADOW_LOG_PATH` → `GET /decision/shadow`, `ShadowPanel`, T-2, T-3 | **KEEP** | Adı "gölge" ama `affect_decision=true` ile T-3 üzerinden owner-onay kuyruğunu besliyor → salt-gözlem değil. ARCHITECTURE §7.5 bunu "true — manual_ready_only" diye belgeliyor. |
| T-2 | `missed_opportunity.scan_and_track` | G | `learning/missed_opportunity.py:244` | `main.py:572` | YAML `missed_opportunity.enabled=true` | `MISSED_OPP_LOG_PATH` → `GET /learning/missed-opportunities`, FE | **KEEP** | Conflict-gate kararı için kanıt biriktiriyor; paper'a dokunmuyor. |
| T-3 | `shadow_activation.activate` | C | `decision/shadow_activation.py:47` | `main.py:586-595` | `shadow.affects_paper(cfg)=true` (T-1 yapılandırması) | `paper_state.manual_ready` kuyruğu | **BELİRSİZ** | Kuyruğu boşaltacak UI yok, TTL yok (M-10). Ya kuyruk operasyonu (UI/TTL) tamamlanmalı ya `affect_decision=false`. Owner kararı. |
| T-4 | Conflict-gate ön-hesabı (`agent_pipeline.build_agent_matrix` + `shadow.evaluate_symbol`) | C | `decision/agent_pipeline.py`, `shadow.py` | `main.py:396-409` | `conflict_gate.enabled=true`; INTRADAY=HARD, TACTICAL=HARD, POSITION=HARD_MANUAL, SCALP/SWING=OFF | `gates.apply_gates` → canlı rota | **KEEP** | Gölge değil canlı kapı; ARCHITECTURE §7.5 tablosu "yalnız POSITION aktif" diyor → bayat (§2.6). |
| T-5 | `news_setup.sync` (+ her tick `build_world_state` + `causal.build_shadow`) | G | `paper/news_setup.py:103` | `main.py:504-534` | koşulsuz (bayrak yok) | `paper_state.news_prepared_setups` → `/cockpit/brief`, `/paper-trading/state`; **hiçbir FE dosyası okumuyor** | **DELETE** (owner onayıyla) | ROADMAP 2026-10-05: "Haber Kaynaklı Hazır Pozisyonlar … Heart'tan kalkar". Backend üreticisi geride kalmış: tick başına ek world+causal hesap + ikinci state transaction. |
| T-6 | `calibration_audit.record_open` | G | `learning/calibration_audit.py:78` | `main.py:483` | koşulsuz | `CALIBRATION_AUDIT_PATH` → `/learning/calibration-jumps`, `CalibrationJumpsPanel` | **KEEP** | Tüketicisi var. |
| T-7 | `event_outcomes.track` | G | `learning/event_outcomes.py:366` | `main.py:387` | koşulsuz | → `/calendar/event-outcomes`, panel, bildirim, brifing | **KEEP** | STATE.md'de tarif edilmiş canlı gözlem. |
| T-8 | `compute_rechecks` + `ticket.build_tickets_from_decisions` + `notif_detector.*` | G | `paper/recheck.py`, `paper/ticket.py`, `notifications/detector` | `main.py:357-381` | koşulsuz | `/paper-trading/tickets`, `PositionChecksPanel`, bildirimler | **KEEP** | Kapsam düşük: `ticket.py` %28, `recheck.py` %71 (§4). |
| T-9 | `snapshot_store.record` | G | `data/snapshot_store.py` | `main.py:605-613` | koşulsuz | `/replay/*` | **KEEP** | Replay temeli. |

### 1.2 Learning worker adımları

| # | Görev | Sınıf | Tanım | Çağıran | Efektif durum | Çıktı → tüketen | Karar | Gerekçe |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| W-01 | `macro_backfill.ensure_depth` | B | `learning/macro_backfill.py` | `main.py:149` | otomatik | makro arşiv → `fundamental_v4`, rejim (canlı) | **KEEP** | Canlı girdi derinliği. |
| W-02 | `build_summary` | G | `learning/summary.py` | `main.py:157` | — | `/learning/summary` (smoke'da), FE | **KEEP** | |
| W-03 | `calibration_trainer.train` | C | `learning/calibration_trainer.py` | `main.py:171` | YAML `calibration.tf_platt=true` | Platt (a,b) → `decision/engine.py` | **KEEP** | Canlı güven kalibrasyonu. |
| W-04 | `empirical_pwin.write_table` | C | `learning/empirical_pwin.py:173` | `main.py:184` | YAML `empirical_pwin.enabled=true` | EV kapısı (`engine.py`), `discovery/scanner` | **KEEP** | Canlı. |
| W-05 | `exit_forensics.write_snapshot` | G | `learning/exit_forensics.py:405` | `main.py:196` | `EXIT_FORENSICS_NUDGE`: AWS değeri BELİRSİZ | `/learning/exit-forensics`, FE panel, `dataset_health`, `tf_target_trainer` | **KEEP** | |
| W-06 | `tf_calibration.calibration_report` | G | `learning/tf_calibration.py` | `main.py:215` | `TF_CALIBRATION_AUTO_ONLY=1` (AWS) | `tf_calibration.json`; tick; `tf_weights` trust | **KEEP** | |
| W-07 | `tf_weight_trainer.propose` | Y | `learning/tf_weight_trainer.py:134` | `main.py:233` | trust-kapılı | `/learning/tf-weights`, FE; `resolve_live_tf_weights` yalnız `shadow.observe`/`shadow_activation`'a gidiyor | **KEEP** | Doğrudan canlı karara yazmıyor (`main.py:553-594`; yalnız shadow ve manual_ready yolu). |
| W-08 | `tf_target_trainer.train` (+ `tf_target_store`, `tf_target_rollback`) | C | `learning/tf_target_trainer.py:326` | `main.py:262`, `main.py:371` | `TF_TARGET_AUTO_ONLY=1`, `TF_TARGET_TRAIL_AUTOTUNE=1`, `TF_TARGET_EDGE_GATE=0` (AWS, zorla) | SL/TP geometri override'ı (dar bantta oto-uygular) | **KEEP** | Canlı etki; kural #4 ile ilişki → M-23. |
| W-09 | `auto_weight_trainer.train` + `rebalance_store` + `weight_rollback` | Y | `learning/auto_weight_trainer.py` | `main.py:323`, `main.py:352` | `REBALANCE_AUTO_APPLY`: deploy set etmiyor; STATE.md: oto-uygulama kapalı (AWS `.env` değeri BELİRSİZ) | `/learning/rebalance/*`, FE | **KEEP** | Ağırlıklar owner onaylı (K5). |
| W-10 | `threshold_trainer.train` / `check_rollback` | C | `learning/threshold_trainer.py:116` | `main.py:388-395` | `THRESHOLD_AUTOTUNE=1` (AWS) | `threshold_overrides` → canlı eşik; `/learning/threshold-autotune` | **BELİRSİZ** | `technical.bias_cuts.*`, `technical.adx_trend_min`, `paper_trading.tp_rr_ratio` otomatik değişiyor (threshold_trainer.py:59-64). RiskGate eşiği içermiyor (iyi) ama kural #4 ile ilişkisi owner'a ait → M-23. |
| W-11 | `guard_safety.run` | Y | `learning/guard_safety.py:289` | `main.py:404` | — | `/learning/guard-safety` | **KEEP** | |
| W-12 | `promotion_criteria.run` | Y | `learning/promotion_criteria.py:110` | `main.py:416` | — | governor defteri; `/learning/promotion-criteria` (FE yok) | **KEEP** | Owner-onay hattı. |
| W-13 | `activation_watchdog.run` | Y | `learning/activation_watchdog.py:378` | `main.py:431` | — | `/learning/activation-watchdog` (FE yok) | **KEEP** | Yalnız-öneri izleyici. |
| W-14 | `sector_rotation.run_if_due` | G | `discovery/sector_rotation.py:226` | `main.py:448` | `DISCOVERY_SCAN_ENABLED=1` (AWS) | `discovery/universe`, FE Discovery | **KEEP** | |
| W-15 | `news_discovery.run` | G | `discovery/news_discovery.py:526` | `main.py:468` | aynı bayrak; AWS'de yerel LLM yok → `LOCAL_LLM_OFF` | `ideas`, `intel`, `news_forecast`, `scanner` | **KEEP** | AWS'te fiilen kapalı olabilir → BELİRSİZ (yerel model durumu). |
| W-16 | `discovery.scanner.run_if_due` | G | `discovery/scanner.py:272` | `main.py:488` | aynı | `/learning/discovery`, `ideas`, `promotion`, `zone_proposer` | **KEEP** | |
| W-17 | `news_forecast.run` | G | `discovery/news_forecast.py:482` | `main.py:507` | aynı | `agent/briefing`, `agent/llm/report`, `intel`, `ideas` | **KEEP** | |
| W-18 | `news_decision_shadow.run` | G | `discovery/news_decision_shadow.py:117` | `main.py:527` | aynı; `affect_decision` kodda sabit false | `agent/briefing`, `intel` (LLM bağlamı) | **KEEP** | Karar bağlantısı owner onayı bekliyor (ROADMAP açık karar). |
| W-19 | `ideas.run` | G | `discovery/ideas.py:339` | `main.py:542` | aynı | `GET /ideas`, `briefing`, `intel`, `promotion` | **KEEP** | |
| W-20 | `discovery.promotion.run` | Y | `discovery/promotion.py:126` | `main.py:560` | aynı | governor defteri | **KEEP** | Otomatik evren ekleme yok. |
| W-21 | `backtest_recon.fidelity_report` (B-1) | G | `learning/backtest_recon.py:311` | `main.py:580` | `BACKTEST_RECON_ENABLED`: deploy'da **yok**, SYNC_FLAGS'ta yok → AWS kapalı varsayımı **BELİRSİZ** | challenger modülleri import ediyor; `BacktestChallengerPanel` | **BELİRSİZ** | Bayrak iki ortama senkronlanmıyor; fidelity çıktısının tüketicisi dolaylı. |
| W-22 | `backtest_recon.run_if_due` (B-2 challenger üretim) | G | `learning/backtest_recon.py:527` | `main.py:598` | `BACKTEST_CHALLENGER_ENABLED=1` (AWS) | → W-23/W-24, `regime_risk_brake` kanıtı | **KEEP** | |
| W-23 | `challenger_trainer.run` (B-3) | G | `learning/challenger_trainer.py:243` | `main.py:620` | aynı | `/learning/backtest-challenger`, `evidence_bus` | **KEEP** | |
| W-24 | `challenger_promotion.run` (B-4) | Y | `learning/challenger_promotion.py:226` | `main.py:643` | aynı | governor paketi | **KEEP** | Hiç READY üretip üretmediği BELİRSİZ. |
| W-25 | `regime_risk_brake.compute` | C | `learning/regime_risk_brake.py:83` | `main.py:666` | YAML `regime_risk_brake.enabled=true` | `decision/engine.py` (kısıtlayıcı fren) | **KEEP** | Gölgeden canlıya terfi etmiş, yalnız kısıtlıyor. |
| W-26 | `news_event_study.record_events/compute` + nedensel arşiv + `causal_calibration.run_if_due` | G | `learning/news_event_study.py:70`, `learning/causal_calibration.py:194` | `main.py:683-749` | koşulsuz; `calibration.apply=false` | `/learning/news-event-study`, `evidence_bus`, `causal.engine` | **KEEP** | ROADMAP: 60 gün kanıt birikmeden karara bağlanmaz. |
| W-27 | `exit_backtest.run_if_due` | G | `learning/exit_backtest.py:216` | `main.py:761` | haftalık | `/learning/exit-backtest`, FE panel, `zero_two_strategy` | **KEEP** | |
| W-28 | `reflection.write_digest` | G | `learning/reflection.py:171` | `main.py:776` | koşulsuz | `decision/learning_advisor.py` (her açılış adayı) | **KEEP** | `LEARNING_ADVISOR_APPLY` AWS değeri BELİRSİZ; apply kapalıysa yalnız gözlem. |
| W-29 | `zero_two_strategy.run_if_due` | G | `learning/zero_two_strategy.py:299` | `main.py:790` | bayrak yok; ROADMAP K4: "0-2 stratejisi donduruldu" | `/learning/zero-two-strategy`, FE panel, `council_scorecard`, `zone_plan_shadow` | **BELİRSİZ** | "Donduruldu" geliştirme mi çalışma mı? Haftalık ağır tarama sürüyor; tüketicileri var. Owner net karar vermeli. |
| W-30 | `zone_plan_shadow.run_if_due` | G | `learning/zone_plan_shadow.py:379` | `main.py:809` | `config/zone_plans.yaml`: tek plan (BTCUSD, `valid_from 2026-07-11`, **`valid_until` yok**; not "Eyl–Eki 2026 beklentisi") | `zone_proposer`, `zone_chart` | **BELİRSİZ** | Planın geçerlilik bitişi yok; owner planı hâlâ geçerli sayıyor mu bilinmiyor. |
| W-31 | `council_scorecard.run_if_due` | G | `learning/council_scorecard.py:221` | `main.py:825` | bayrak yok | `/learning/council` (sözleşmesiz), FE | **KEEP** | |
| W-32 | `zone_proposer.run_if_due` | G | `learning/zone_proposer.py:504` | `main.py:841` | `config/zone_proposer.yaml`; `zone_influence.enabled=false` | `/learning/zone-proposer*`, `tf_scoring_shadow` (zone leans), `zone_chart` | **KEEP** | SL/TP'ye etkisi (zone_influence) kapalı. |
| W-33 | `subsignal_scorecard.run_if_due` | G | `learning/subsignal_scorecard.py:261` | `main.py:859` | `SUBSIGNAL_SCORECARD_ENABLED=1` (AWS) | `tf_scoring_shadow`, `scoring/tf_scoring_v2`, FE panel | **KEEP** | Canlı touche ağırlıklarının kanıtı. |
| W-34 | `tf_scoring_shadow.run` | **C** | `learning/tf_scoring_shadow.py:161` | `main.py:878` | `TF_SCORING_V2_SHADOW=1` (AWS) | **`consensus/engine.py:_touche_shadow_row` (canlı yön kaynağı)**, `data/quality/dqs.py` | **KEEP** | Gölge **değil**: canlı touche'un yön kaynağı. Bayrak/dosya adı yanıltıcı; bayrak OFF → artifact 3 sa'te bayatlayıp zemine düşüyor (kural #2'nin tersi). Yeniden adlandırma önerisi → M-22. |
| W-35 | `tf_scoring_race.run` | Y | `learning/tf_scoring_race.py:353` | `main.py:897` | aynı bayrak | `/learning/tf-scoring-race`, FE panel | **BELİRSİZ** | K2 ile v4 zaten canlı (`consensus.touche_v4=true`); yarışın "terfi" amacı bitmiş görünüyor. Owner kararı: kapat ya da raporlama için tut. |

**Envanter sonuçları (özet).**
- 44 adımın **hiçbiri** broker/emir yolu içermiyor. Tüm yazımlar `data/runtime/*` artifact'ı ya da governor defteri.
- **Gölge olmayan "gölge" adlar:** T-1/T-3 (kuyruğu besler), W-34 (canlı yön kaynağı), W-25 (canlı fren), W-10 / W-08 (canlı eşik/SL-TP).
- **DELETE adayı:** T-5. **BELİRSİZ (owner):** T-3, W-10, W-21, W-29, W-30, W-35.
- **Tüketicisi olmayan adım bulunmadı** (T-5 hariç); çoğunun tüketicisi yalnız bir API route + FE paneli.
- `learning_worker.run_once` ~850 satırlık tek fonksiyon, ~35 `try/except Exception` bloğu; adım başına zaman aşımı yok,
  yalnız toplam süre için `LEARNING_BUDGET_MS` uyarısı var (M-22).

---

## 2. Ölü kod ve mimari çöp

### 2.1 Kullanılmayan modül / sembol (backend)

Yöntem: AST import grafiği (313 modül) + üst-seviye sembol referans sayımı (2353 sembol). `vulture --min-confidence 80`
**sıfır** bulgu verdi; ayrıntı aşağıdaki özel analizden.

| Öğe | Satır | Kanıt | Öneri |
| --- | --- | --- | --- |
| `packages/data/providers/fundamentals/` (boş paket, yalnız docstring) | 1 | repo genelinde 0 import | **DELETE** |
| `data/providers/liquidity/defillama.py:45` `get_chain_tvl` (18 satır), `:97` `get_protocol_tvl` (26) | 44 | repo genelinde yalnız tanım (1 geçiş) | **DELETE** |
| `data/registry/loader.py:49` `load_feature_registry` (3) **+ `config/feature_registry_v1.0.yaml`** | 3 | fonksiyon yalnız tanım; YAML'ı yalnız bu ölü fonksiyon okuyor → **ölü konfigürasyon dosyası** | **DELETE** (ikisi birlikte) |
| `learning/book_audit.py:250` `self_conflict_sides` | 8 | yalnız tanım | **DELETE** |
| `learning/outcomes.py:285` `outcome_to_dict` | 2 | yalnız tanım | **DELETE** |
| `liquidity/rotation.py:206` `WindowFlow` | 6 | yalnız tanım | **DELETE** |
| `risk/trade_economics.py:623` `tf_size_cap` | 10 | yalnız test (`test_trade_economics.py:93`). Motor `engine._timeframe_policy` (`engine.py:154-167,822`) ile birebir aynı işi yapıyor; üçüncü kopya `agent_decision.py:59` | **DELETE** (+ testi); tek kaynak = `_timeframe_policy` |
| `decision/engine.py:987` `decide_all` | 37 | yalnız 5 test dosyası; canlı yol `decide_matrix` | **BELİRSİZ** — testler `decide_all`'a bağımlı; testleri `decide_matrix`'e taşıyıp sil |
| `paper/manual_queue.py:70` `is_recurring_signal` (6), `:217` `purge_stale_rejection` (9) | 15 | yalnız test; `purge_stale_rejection` üretimde **hiç çağrılmıyor** → `rejected_signals` hiç temizlenmiyor (M-10) | `purge_stale_rejection`'ı bağla, `is_recurring_signal`'ı sil |
| `paper/sizing.py:35` `apply_ai_opinion` (7) + `:24` `clamp_ai_multiplier` (9) | 16 | yalnız test + mimari guard; üretimde AI çarpanı yok | **KEEP** (değişmez kuralın yapısal belgesi) — BELİRSİZ: yorumla işaretle |
| `learning/news_event_study.py:465` `causal_backtest` (33), `:923` `causal_historical_replay` (105) | 138 | yalnız test | **BELİRSİZ** — analiz aracı; `tools/` altına taşı |
| `learning/macro_backtest.py` (760 satır) | 760 | prod importer yok; yalnız 4 test + `__main__` + yorum referansları | **BELİRSİZ** — "tezgâh" kaydı; `packages/` dışına (`tools/`) taşı |
| `learning/monitoring_coverage.py` (197), `ops/env_registry.py` (214) | | yalnız contract testleri (kapsama/ratchet verisi) | **KEEP** ama `tests/` altına taşımak daha dürüst (çalışma zamanında yüklenmiyor) |
| `audit.ACTIONS` (`paper/audit.py:29-42`) | | hiçbir yerde kullanılmıyor; `MANUAL_OPEN`, `PENDING_*`, `DISASTER_STOP`, `STATE_CONFLICT` … listede yok ("openapi enum ile senkron" iddiası yanlış; OpenAPI `action: string`) | listeyi sil ya da tam yap + test |

### 2.2 Kullanılmayan API route'ları

119 route (1'i `async`: SSE `stream`; geri kalanı senkron → thread havuzunda; olay döngüsünü bloklamıyor).
Aşağıdakilerin FE'de **hiçbir çağrısı yok** (doğrudan `grep` ile doğrulandı; `technical/*`, `notifications/*`, `replay/{id}` şablon
dizgesiyle çağrılıyor → listede yok):

| Route | Test? | Not |
| --- | --- | --- |
| `GET /paper-trading/manual-ready`, `POST …/{id}/approve`, `…/reject`, `…/dismiss` | var | **Owner onay kuyruğunun UI'ı yok** (M-10) |
| `POST /paper-trading/reset` | **hiç koşmuyor** | arşivsiz yıkıcı (M-18) |
| `POST /paper-trading/maintenance/archive`, `…/repair`, `…/reset` | var | admin aracı; UI'sız kabul edilebilir |
| `GET /risk/portfolio` | var | |
| `GET /replay/strategy-backtest`, `/all`, `/replay/backtest/{run_id}` | var | |
| `GET /learning/promotion-criteria`, `/activation-watchdog`, `/technical-books-replay` | var | |
| `GET /learning/zone-proposer/chart/{symbol}` | **hiç koşmuyor** | |
| `GET /analysis/asset/{symbol}` | **hiç koşmuyor** | |

Testlerde **hiç koşmayan** 38 route gövdesi var (örn. `POST /paper-trading/positions/open`, `…/{id}/close`, `GET /stream`,
`DELETE /paper-trading/orders*`, `POST /learning/tf-targets/approve|reject|retrain`, `POST /learning/guard-safety/adopt`,
`GET /technical/*/{asset_code}` ×9) — 38'in **20'si** sözleşmesiz 28 route'luk borcun (`tests/contract/contractless_routes.txt`) içinde.
(Yöntem: route fonksiyon gövdesinin satırlarından hiçbiri kapsam ölçümünde "executed" değil.)

### 2.3 API katmanına sızmış iş mantığı

`apps/api` "ince HTTP katmanı" (mimari guard: arka plan döngüsü yok ✔). Ama yeniden hesaplama ve alan mantığı sızmış:

| Yer | Sorun |
| --- | --- |
| `routers/cockpit.py:32-114` (`GET /cockpit/brief`) | **Her GET'te tüm karar motorunu** (`decide_matrix`, 5 TF × tüm semboller) + `build_world_state` + `causal.build_shadow` + portföy + LLM dünya brifini yeniden koşuyor; ayrıca router içinde `conflict_inputs` sezgileri (`"trade_economics_valid": None`, `"rr_context_unavailable": True`) üretiyor. Supervisor tek süreç olduğundan tick ile aynı GIL'i paylaşıyor. |
| `routers/decision.py:25-40` | `GET /decision/matrix` her çağrıda `decide_matrix` koşuyor. |
| `routers/dashboard_state.py:43-139` (`get_dashboard_state`, 95 satır) | `build_world_state` + `causal.build_shadow` GET içinde yeniden hesaplanıyor (`decide_matrix` yok). |
| `routers/data.py:18-190` (`get_snapshot`, 173 satır) | View-model montajı router'da. |
| `routers/paper_trading.py:197-290` | SL/TP doğrulama kuralları (`_risk_plan_side_reason`, `_parse_risk_price`) router'da; `packages/paper/position_ops.modify_sltp` ise **doğrulamasız ikinci kopya** (yalnız chat çağırıyor). |
| `routers/paper_trading.py:154-188`, `:363-386` | Manuel kapama / onay akışı (snapshot + sanity + `RiskInput` kurma) router'da; `position_ops.partial_close` ile kopya. |
| **9 ayrı `RiskInput(...)` kurucusu** (`agent/briefing.py:111`, `agent/llm/context.py:34`, routers: `technical.py:193`, `cockpit.py:36`, `dashboard_state.py:48,152`, `decision.py:28`, `paper_trading.py:371`, `risk.py:23`; tick: `main.py:307,327`) | Yalnız tick `mtm_equity_usd` dolduruyor → **dashboard ile tick aynı anda farklı RiskGate sonucu görebiliyor** (M-03). Tek yardımcı fonksiyon gerekli. |
| **Ters bağımlılık** `packages/agent/llm/chat.py:664` → `apps.api.routers.paper_trading` | `packages` → `apps` yönü yasak olmalı; üstelik import **kırık** (M-08). |
| **Chat → hesap mutasyonu** `chat.py:824-1027` → `manual_order.place`, `position_ops.*` | Narrative katmanı (regex ayrıştırıcı) paper state'i değiştiriyor (M-02). |

### 2.4 Üç-süreç izolasyonu

Güncel topoloji (owner kararı K6): **tek süreç** `apps.supervisor` içinde API (event loop) + tick (thread) + learning (thread).
Yani fiziksel izolasyon kasıtlı olarak yok; mantıksal izolasyon dosya artifact'larıyla sağlanıyor. Bulgular:

1. **Kod-düzeyi bağımlılıklar:** `apps/supervisor → api/tick_worker/learning_worker` (beklenen). `apps/*` arası başka import yok ✔.
   `packages → apps` ters bağımlılığı yalnız `chat.py:664` (kırık).
2. **Tick ← learning artifact bağımlılığı (belgeli ama sıkı):**
   - `consensus/engine.py:270-296` her karar için `data/runtime/tf_scoring_v2_shadow.json` okuyor (3 sa bayatlayınca zemin motora düşüyor).
   - `data/quality/dqs.py:137-152` + YAML `data_policy.dqs_extended_gate.enabled=true`, `artifact_freshness_min=30`
     → artifact ~2,1 saatten eskiyse **snapshot durumu OK→DEGRADED** oluyor. Learning thread'i takılırsa (adım başına zaman
     aşımı yok) tick'in veri kalitesi etiketi bozuluyor.
3. **İki bağımsız snapshot üreticisi:** tick `build_snapshot()` (her ~30-44 sn), API `get_cached_snapshot()` (TTL 30 sn, ayrı
   `_CACHE`). Aynı sağlayıcılara çift trafik; dashboard ile tick farklı `snapshot_id` görüyor.
4. **Süreç-içi kilitler:** `threading.Lock` (`state._LOCK`, `halt._LOCK`) yalnız thread'ler arası; süreçler arası koruma
   `Transaction` dosya kilidi. `lru_cache`'li config (`load_thresholds`) → bayrak değişimi restart istiyor (belgeli).
5. **Learning worker bağımsız çalıştırılırsa** (`python -m apps.learning_worker.main`) `get_cached_snapshot()` boş cache ile
   senkron ağ çağrısı yapar; ayrı süreçte tick'in cache'i görünmez (BELİRSİZ: bu mod artık kullanılmıyor, K6).

### 2.5 Diğer mimari çöp / tutarsızlık

- **Giriş yolları:** ARCHITECTURE §7.5 "`attempt_open()` kod tabanında yalnız tick'te çağrılır" diyor — **yanlış**. Pozisyon açan **6 yol** var:
  tick `attempt_open` (tüm koruma), `manual_queue.approve` → `attempt_open`, `manual_order.place` → `open_position` (market),
  `lifecycle.trigger_pending_orders` → `open_position`, `position_ops.flip` → `open_position`, `position_ops.scale_in` (mevcut pozisyonu büyütür).
  Son dördü `price_sanity` dışında `state_anomaly`/duplicate/RiskGate korumalarını atlıyor (M-05).
- **`max_position_usd` adı yanıltıcı:** gerçek tavan `1.5 × 25 000 = 37 500` (`sizing.py:59`, `MAX_SIZE_MULTIPLIER=1.5`).
- **Atomik olmayan yazımlar:** `halt.py:91`, `calibration_store.py:108`, `tf_target_store.py:78`, `rebalance_store.py:217,227,270`,
  `custom_assets.py:51`, `regime/classifier.py:88`, `agent/llm/budget.py:60`. Ratchet testi (`test_ops_store.py:83`) yalnız
  el yapımı `tmp.replace` desenini yakalıyor; düz `write_text` serbest (M-19).
- **Sessiz hata yutma:** 163 geniş `except Exception`, 41'i sessiz (`pass/continue/return sabit`) — `ruff BLE001` 151, `S110` 14, `S112` 7.
- **Runtime mock:** kural "runtime'da mock yok", ama `PRICE_USE_MOCK`, `OPTIONS_USE_FIXTURE`, `DERIVATIVES_USE_FIXTURE` env opt-in'leri
  var (varsayılan kapalı; UI'da `MockModeBanner`). Prod'da set edilmesini engelleyen bir kapı yok (BELİRSİZ: deploy script set etmiyor).
- **Python bağımlılıkları sabitlenmemiş:** `pyproject.toml` taban sürümleri; kilit dosyası yok. CI `pip install ruff pytest fastapi httpx
  pydantic pyyaml` (sürümsüz, `edge-tts` yok), Python **3.11**; bu denetimde 3.13 + fastapi 0.143 + pydantic 2.14 kullanıldı ve
  `starlette.testclient` "`httpx` yerine `httpx2` kurun" uyarısı veriyor (gelecek kırılma riski).

### 2.6 Doküman bayatlığı (kod ≠ belge)

| Belge | İddia | Gerçek |
| --- | --- | --- |
| `ARCHITECTURE.md` §7.5 | `attempt_open` tek çağrı noktası tick | 6 giriş yolu (yukarıda) |
| `ARCHITECTURE.md` §7.5 tablo | Conflict Gate "yalnız POSITION aktif, diğerleri OFF" | YAML: INTRADAY=HARD, TACTICAL=HARD, POSITION=HARD_MANUAL |
| `ARCHITECTURE.md` §7.5 | `decision/conflict_resolver_activation.py` | dosya yok (`shadow_activation.py` olmuş) |
| `ARCHITECTURE.md` §8/§9 | `risk/{models,gate,sizing,drawdown,kill_switch}.py`, `paper/{models,simulator,position_manager,state_store}.py`; paper sim "spread, slippage, fee, latency" | gerçek dosyalar farklı; `grep` ile paper'da fee/slippage/spread **yok** (M-20) |
| `docs/STATE.md` "Risk frenleri" | "%8 (MTM dahil) → KILL_SWITCH, tüm pozisyonlar kapanır, yalnız owner reset" | MTM ihlali pozisyon kapatmıyor (M-03); reset anında yeniden kuruluyor (M-04) |
| `docs/STATE.md` | "%2 günlük zarar … UTC gün dönümünde kendiliğinden kalkar" | M-01 |
| `docs/DASHBOARD_RULES.md` | yeni panel `lib/panel-registry.ts`'e eklenir | dosya hiçbir yerde import edilmiyor (§5) |
| `types/generated/api.ts` başlığı | "Generated … DO NOT EDIT" | el yazması; gerçek codegen çıktısı `schema.ts` ve onu kimse kullanmıyor (§5) |

---

## 3. Mantık hatası şüpheleri

Her kayıtta: **Yer** (dosya:satır), **Neden hatalı**, **Risk**, **Kanıt**, **Önerilen test**. Düzeltme önerileri değişmez kuralları gevşetmez;
gevşetme sayılabilecek olanlar açıkça "owner kararı" diye işaretlendi.

### 3.1 P0

#### M-01 — Günlük PnL sayacı UTC gün dönümünde sıfırlanmıyor; DAILY_LOSS halt'ı yeniden doğuyor
- **Yer:** `packages/paper/lifecycle.py:165-172` (`_ensure_daily_anchor`), **tek çağrı** `lifecycle.py:587` (yalnız `close_position` içinde);
  tüketici `apps/tick_worker/main.py:307-312` (`daily_pnl_usd=ps.daily_pnl_usd`, anchor çağrılmadan); `packages/risk/halt.py:132-144,158-193`;
  `packages/risk/engine.py:83-91`.
- **Neden hatalı:** `halt.sync()` UTC gün dönümünde eski DAILY_LOSS'u `day_rollover` ile kapatıyor (`halt.py:167-174`) — ama aynı çağrıda
  `_breaches(inp)` hâlâ **dünkü** `daily_pnl_usd` ile çalışıyor ve **bugünün tarihli yeni halt'ı** hemen yeniden açıyor. `daily_pnl_usd`
  yalnız bir pozisyon kapanınca (`close_position`) sıfırlandığı için, açık pozisyon yoksa hiçbir zaman sıfırlanmıyor. Owner `POST /risk/halts/reset`
  halt'ı kapatsa bile bir sonraki tick aynı sebeple yeniden kuruyor. `engine.evaluate` de aynı bayat değerle RISK_REDUCE veriyor.
- **Risk:** STATE.md'deki owner kararı H11 ("UTC gün dönümünde kendiliğinden kalkar") fiilen çalışmıyor. Günlük kayıptan sonra tüm pozisyonlar
  kapanmışsa yeni paper işlem **süresiz** duruyor; çıkış yalnızca ilk kapanış (olmuyor) ya da tüm state'i sıfırlamak (`/paper-trading/reset`).
  Fail-closed (para riski yok) ama sistem sessizce felç; `halt` zaman çizelgesinde her gün yeni "bugün" kaydı birikiyor.
- **Kanıt (✔ repro, Ek B-1):** dünkü anchor + `daily_pnl_usd=-300` (equity 9700) + pozisyon yok →
  `sync → [('DAILY_LOSS','RISK_REDUCE','2026-10-11')]`, `evaluate → RISK_REDUCE`; `owner_reset` sonrası `sync` yine aktif; `_ensure_daily_anchor` çağrılınca değer 0.0'a iniyor.
- **Neden testler yakalamadı:** `tests/unit/test_halt.py:219` gün dönümünü yalnız halt modülünde, `daily_pnl=0` girdisiyle sınıyor; state taşıyan bütün senaryo yok.
- **Test önerisi:** `test_daily_loss_halt_lifts_after_utc_rollover_without_closes` — state(anchor=dün, daily=-3%, pozisyon yok) → bir tick (`run_once`, ağsız snapshot)
  → `active_halts()==[]`, `RiskGate==HOLD`, `ps.daily_pnl_usd==0`. Ek: `test_owner_reset_not_recreated_same_day_after_rollover`. **Canlı YAML ile** (conftest pin'siz) koşmalı (§4.3).
- **Düzeltme yönü (uygulanmadı):** `_ensure_daily_anchor(ps)` tick transaction'ının başında ve `RiskInput` kuran her okuma yolunda (ya da `PaperState.daily_pnl_usd`'yi gün-farkında yapan bir okuma yardımcısı) çağrılmalı. Bu, **dokümante owner kararını uygulamaktır**; yine de RiskGate girdisini değiştirdiği için owner onayıyla.

#### M-02 — Chat, serbest metinden (soru cümleleri dahil) pozisyon açıyor; yanıt "risk kapısını geçtim" diyor
- **Yer:** `packages/agent/llm/chat.py:824-842` (`_parse_manual_order`), `:846-872` (`_manual_order_answer`; yanıt metni `:868`), `:1005-1027` (`_grounded_answer` → en öncelikli dal), `:782-783,1011-1023` (`_PENDING_ORDER` modül-global, TTL 180 sn);
  `packages/paper/manual_order.py:59-101` (RiskGate'siz market açılışı); `apps/api/routers/chat.py`.
- **Neden hatalı:** (a) Ayrıştırıcı yalnız "al|sat|aç|emir|pozisyon|long|short…" sözcüğü + sembol + ≥3 haneli sayı arıyor; soru kipi/koşul/olasılık kontrolü yok.
  `sat\w*` deseni "satış" gibi isimleri de yön sayıyor. (b) Yön belirsizse emir **modül-global** `_PENDING_ORDER`'a yazılıp sonraki mesajdaki yalın "al/sat"
  ile tamamlanıyor — oturum/kullanıcı ayrımı yok, thread-güvenli değil. (c) Başarı mesajı "patron yetkisiyle, **risk kapısını geçtim**" diyor, oysa
  `manual_order.place` `evaluate_risk`'i hiç çağırmıyor (M-05). Owner yanlış güvenceyle bilgilendiriliyor.
- **Risk:** İlke ihlali: "LLM/narrative yalnız anlatır; RiskGate final". Chat uç noktası (POST) `API_AUTH_TOKEN` yoksa açık (M-21). Yalnız paper, ama
  istemeden açılan pozisyonlar öğrenme verisini (`owner_manual` kohortu), pozisyon sayısı limitini ve günlük PnL'i etkiliyor.
- **Kanıt (✔ repro, Ek B-2):**
  `"ETH'de satış baskısı var mı, 2000 dolar pozisyon açsam ne olur?"` → `{'symbol':'ETHUSD','side':'short','size_usd':2000.0}`;
  `"Altın 3000 dolar seviyesini görürse al sinyali gelir mi?"` → `long 3000`; `"BTC için 5000 dolarlık pozisyon riskli mi?"` → yön sorulup beklemeye alınıyor.
  KILL_SWITCH halt aktifken `manual_order.place("BTCUSD","long",20000)` → pozisyon **açıldı**.
- **Test önerisi:** parametrik `test_chat_questions_never_place_orders` (soru işareti / "mı|mi|olur|sinyali|görürse" içeren 30+ cümle → `manual_order.place` çağrılmaz);
  `test_chat_order_requires_explicit_confirmation`; `test_chat_order_answer_never_claims_risk_gate_passed_unless_evaluated`; `test_pending_order_is_per_session`.
- **Düzeltme yönü:** soru/koşul cümlelerinde ayrıştırma yapma; emri iki adımla (özet + açık "onaylıyorum") yap; yanıt metnini gerçeğe uydur (ya da RiskGate'i gerçekten uygula — M-05 kararına bağlı);
  KILL_SWITCH/halt altında reddet (yalnız kısıtlayıcı).

### 3.2 P1

#### M-03 — MTM drawdown: RiskGate KILL_SWITCH diyor ama ne pozisyonlar kapanıyor ne halt kalıcı oluyor; API girdileri MTM'siz
- **Yer:** `packages/risk/engine.py:97-116` (MTM'li DD → KILL_SWITCH adayı), `packages/risk/halt.py:132-155` (`_breaches` yalnız **realized** `equity_usd`),
  `apps/tick_worker/main.py:320-326` (flatten yalnız `halts` içinde KILL_SWITCH varsa); YAML `risk_gates.mtm_equity_enabled: true`;
  API kurucuları (`routers/cockpit.py:36`, `dashboard_state.py:48,152`, `decision.py:28`, `risk.py:23`, `paper_trading.py:371`) `mtm_equity_usd` vermiyor.
- **Neden hatalı:** Canlı MTM bayrağı açık. MTM DD ≥ %8'de `evaluate` KILL_SWITCH döndürüyor (yeni açılış yok) ama persist edilen halt oluşmadığı için
  `flatten_all` çalışmıyor; açık pozisyonlar sürüyor. Fren "owner reset gerekli" metnini taşıyor ama sıfırlanacak bir halt yok; MTM toparlanınca fren kendiliğinden kalkıyor.
  YAML yorumu "RISK_REDUCE freni", engine "KILL_SWITCH", STATE.md "tüm pozisyonlar kapanır" diyor — **üç kaynak çelişiyor** (niyet BELİRSİZ).
  API tarafı MTM'siz olduğundan aynı anda dashboard `HOLD`, tick `KILL_SWITCH` görüyor; `manual_queue.approve` MTM ihlalini göremiyor.
- **Risk:** Belgelenmiş güvenlik davranışı uygulanmıyor (pozisyonlar kapanmıyor). Para riski yok (paper) ama risk modeli test edilmiyor.
- **Kanıt (✔ repro, Ek B-3):** 25k long, fiyat −%40 → `mtm_equity=90 000`; tick girdisi: `KILL_SWITCH ['DD(mtm) 10.0% ≥ 8%']`; `halt.sync → []`; API girdisi: `HOLD`.
- **Test önerisi:** `test_mtm_dd_breach_is_persisted_or_flattened_per_policy` (karar sonrası); `test_api_risk_input_matches_tick_risk_input` (tek `risk_input_from_state()` yardımcısı).
- **Düzeltme yönü:** önce **owner kararı** (MTM ihlali ne yapsın: sadece yeni açılış durdur mu, flatten mi?); sonra belge/kod hizala. Tek `RiskInput` fabrikası.

#### M-04 — MAX_DRAWDOWN owner reset'i peak'i yeniden tabanlamıyor; fren bir sonraki tick'te geri geliyor
- **Yer:** `apps/api/routers/risk.py:48-54`, `packages/risk/halt.py:196-209` (`owner_reset`), `halt.py:145-154`.
- **Neden hatalı:** KILL_SWITCH sonrası tüm pozisyonlar kapanmıştır; equity tepe değerin altında kalır. `owner_reset` yalnız halt kaydını kapatır; `peak_equity_usd` aynı kalır →
  bir sonraki `sync` aynı DD'yi görüp yeni halt kurar. STATE.md "Yalnız owner reset ile kalkar" vaadi fiilen yerine gelmiyor; tek çıkış tam state sıfırlama.
- **Risk:** Owner kontrolü yok sayılıyor (kilitlenme). **Peak'i tabanlamak bir gate gevşetmesidir** → düzeltme yalnız açık owner kararıyla (örn. `?rebase_peak=true` açık parametre + audit).
- **Kanıt (✔ repro, Ek B-4):** `sync → MAX_DRAWDOWN`; `owner_reset → temizlendi, aktif []`; sonraki `sync → MAX_DRAWDOWN KILL_SWITCH`.
- **Test önerisi:** `test_owner_reset_of_max_drawdown_has_defined_effect` (seçilen politikaya göre).

#### M-05 — Manuel yollar RiskGate / halt / DQS / pozisyon limiti / boyut tavanı dışında (owner kararı)
- **Yer:** `packages/paper/manual_order.py:91-101` (market → `open_position`), `:59-70` docstring ("RiskGate … BAYPAS edilir — owner yetkisi"), `apps/api/routers/paper_trading.py:315-331`;
  `packages/paper/lifecycle.py:684-706,741-751` (bekleyen emir dolumu yalnız persist edilmiş `active_halts()`, hesap anomalisi ve duplicate'i kontrol eder; `NO_POSITION_INCREASE` (pozisyon limiti), DQS<55 ve olay riski **kontrol edilmez**);
  `packages/paper/position_ops.py:105-137` (`scale_in`, `flip`).
- **Neden sorunlu:** `docs/SAFETY_RULES.md`: "RiskGate, DQS veto, kill switch, RR, sizing kuralları zayıflatılamaz veya bypass edilemez." Kod ise owner yetkisini gerekçe göstererek
  hepsini atlıyor. Ayrıca `size_usd` yalnız `equity`'ye karşı sınanıyor; `max_position_usd` (25 000) uygulanmıyor (90 000 USD'lik emir kabul edilir).
  Aynı `manual_queue.approve` yolu ise RiskGate'i **yeniden** çalıştırıyor — tutarsız.
- **Risk:** İlke çatışması (belge ↔ davranış). Paper-only. Niyet **BELİRSİZ**: docstring bilinçli muafiyeti anlatıyor; SAFETY_RULES tersini söylüyor.
- **Kanıt (✔ repro, Ek B-2):** `MAX_DRAWDOWN/KILL_SWITCH` halt aktifken market emri → `size_usd=20000` açıldı (sonraki tick flatten edecek).
- **Test önerisi:** politika netleşince `test_manual_market_order_respects_kill_switch` (veya "muaf" olduğunu açıkça kilitleyen test + belge).
- **Öneri:** owner iki seçenekten birini seçsin: (A) manuel emir de KILL_SWITCH/RISK_REDUCE/DQS ve `max_position_usd`'ye tabi (yalnız kısıtlama); (B) muafiyet belgelenir, SAFETY_RULES'a istisna olarak yazılır, UI'da açıkça gösterilir.

#### M-06 — `NaN`/`inf` boyut çarpanı maksimum boyuta dönüşüyor (fail-open)
- **Yer:** `packages/paper/sizing.py:59` (`max(0.0, min(MAX_SIZE_MULTIPLIER, float(x)))`), `packages/decision/engine.py:592,665,699,734,763,803` (`max(0.0, min(1.5, size))`).
- **Neden hatalı:** Python'da `min(1.5, nan)` → `1.5` (karşılaştırma False olduğu için ilk argüman kalır) → `max(0.0, 1.5)=1.5`. Operand sırası ters olan
  yerlerde (`session_gate.py`: `min(1.0, max(0.0, x))`, `paper_policy.cap_size`) NaN → 0.0 (güvenli); iki desen tutarsız.
- **Risk:** Boyut zincirinde bir `NaN` (numpy/pandas türevli korelasyon/vol, bozuk JSON) pozisyonu 1,5× (=37 500 USD) açar. NaN kaynağı **BELİRSİZ** (kodda sıfıra bölme çoğunlukla exception veriyor); sonuç ağır olduğundan P1.
- **Kanıt (✔ repro, Ek B-5):** `compute_size_usd(nan)=37500.0`, `compute_size_usd(inf)=37500.0`; `max(0.0,min(1.5,nan))=1.5`.
- **Test önerisi:** özellik testi `test_every_size_clamp_is_fail_closed_on_nan_inf` (sizing + engine zinciri + `news_setup`); ortak `clamp_size()` + yapısal guard (regex `min\(1\.5,`).

#### M-07 — `risk_halts.json` atomik yazılmıyor; bozuk dosya halt'ı sessizce siliyor
- **Yer:** `packages/risk/halt.py:76-84` (`load`: `JSONDecodeError → HaltState()`), `:87-91` (`save`: düz `write_text`).
- **Neden hatalı:** Yazma sırasında süreç düşerse yarım JSON kalır; `load` bunu "halt yok" sayar → owner-reset-only KILL_SWITCH kalıcı olarak düşer, audit'e bile iz bırakılmaz.
  `state.py`'daki gibi yedekle + audit yok. (`write_text_atomic` repo'da var.)
- **Kanıt (✔ repro, Ek B-6):** yarım dosya → `active_halts()==[]`, `sync(...)==[]`.
- **Test önerisi:** `test_corrupt_halt_file_fails_closed` (bozuksa: yedekle + audit + KILL_SWITCH varsay / uyarı); `test_halt_save_is_atomic`. Kapsam: `halt.py:83-84` şu an testlerde hiç koşmuyor.

#### M-08 — Chat'in "aktif ticket" cevabı her zaman "yok"
- **Yer:** `packages/agent/llm/chat.py:661-664` (`from apps.api.routers.paper_trading import _LAST_TICKETS`).
- **Neden hatalı:** `_LAST_TICKETS` router'da artık yok (T1 ile ticket üretimi worker'a taşındı, veri `data/runtime/tickets.json`'da). `except Exception: tickets = []` hatayı yutuyor →
  cevap daima "Şu an broker'a gidecek aktif Trade Ticket yok". Ayrıca `packages → apps` ters bağımlılığı. Metindeki "broker'a gidecek" ifadesi paper-safe diline aykırı.
- **Kanıt (✔ repro, Ek B-7):** `ticket.save_last([...aktif...])` sonrası `chat._tickets_answer(None)` → `tickets:none`.
- **Test önerisi:** `test_chat_tickets_answer_reads_ticket_store`; `ticket.load_last()` kullan.

#### M-09 — manual_ready onayı: güven kademesi kayboluyor (3,3× boyut), `data_verified=False`, eski fiyat yedeği
- **Yer:** `packages/paper/manual_queue.py:191-205` (`attempt_open` çağrısında `predicted_confidence/raw_confidence/data_verified/atr/module_contributions` yok),
  `:191` (`price = current_price if … else entry.requested_price`), `state.py:179-191` (`ManualReady` bu alanları taşımıyor).
- **Neden hatalı:** Otomatik yolda boyut = `d.size_multiplier × tier.size_mult` (WEAK 0,3). Onay yolunda tier `NEUTRAL` (1,0) → aynı aday onaylanınca **3,3×** büyük açılıyor ve
  `data_verified=False` olduğu için öğrenmeden dışlanıyor. Anlık fiyat yoksa kuyruğa girdiği andaki (günler eski olabilir) `requested_price` giriş fiyatı oluyor.
- **Kanıt (✔ repro, Ek B-8):** `size_multiplier=0.35` aday: onay → `tier=NEUTRAL, size_usd=8750`; otomatik (güven 0,25 → WEAK) → ≈2625.
- **Test önerisi:** `test_manual_ready_approval_preserves_conviction_tier_and_size`; `test_approval_without_live_price_is_refused`.

#### M-10 — manual_ready kuyruğu: UI yok, TTL yok, `rejected_signals` hiç temizlenmiyor
- **Yer:** FE'de `manual-ready` endpoint'lerinin çağrısı **sıfır** (yalnız `AgentMatrixPanel` etiket metni); `packages/paper/manual_queue.py` süre sınırı içermiyor;
  `purge_stale_rejection` (`:217`) üretimde çağrılmıyor.
- **Neden sorunlu:** Seans kapısı, conflict-gate (POSITION=HARD_MANUAL), `shadow_activation` ve `regime_manual_ready` adayları bu kuyruğa yönlendiriyor (T-1/T-3, ARCHITECTURE "3 farklı yol"); owner'ın onaylayacağı bir ekran yok
  (yalnız ham API). Reddedilen `(symbol, side, tf)` anahtarı **kalıcı** sessiz-bloğa dönüşüyor; liste sınırsız büyüyor (state dosyası her kayıtta bütün listeyi yazıyor).
- **Risk:** "Owner onayı" ilkesinin pratikte işlemeyen yarısı; kuyruktaki eski aday haftalar sonra onaylanırsa M-09 devreye girer. UI "yeni özellik" olduğundan temizlik döneminde ayrı owner kararı.
- **Kanıt:** `grep manual-ready apps/web` (1 etiket), `grep purge_stale_rejection` (yalnız test).
- **Test önerisi:** `test_manual_ready_entries_expire`, `test_rejected_signal_ttl`.

### 3.3 P2

| ID | Yer | Neden hatalı / risk | Kanıt | Test önerisi |
| --- | --- | --- | --- | --- |
| M-11 | `paper/position_ops.py:116-117` | `scale_in` ortalama giriş fiyatını **notional-ağırlıklı aritmetik ortalama** ile hesaplıyor; doğrusu miktar-ağırlıklı (harmonik): `(s1+s2)/(s1/e1+s2/e2)`. | ✔ 1000$@100 + 1000$@110, fiyat 120: gerçek PnL 290,91 vs modelin 285,71 (−5,19$ ≈ %1,8) | `test_scale_in_pnl_equals_sum_of_legs` (özellik testi) |
| M-12 | `position_ops.py:95`, `lifecycle.py:517-518` | `partial_close` için 0/negatif miktar doğrulanmıyor → **sıfır boyutlu Trade** üretilip `recent_trades`+`decision_log`'a yazılıyor (öğrenme verisini kirletir). | ✔ `close_size=0` → `trade.size_usd=0.0`, kayıt eklendi | `test_partial_close_rejects_nonpositive_size` |
| M-13 | `position_ops.py:68,86,112,126` | `_market_price()` → `build_snapshot()` (~20 sn ağ) **transaction kilidi içinde**; `manual_order.place` doğru yapıyor (kilit dışı). Tick de kilidi `decide_matrix` boyunca tutuyor (`main.py:299→497`): API sahip-mutasyonları tick süresince bekler (süre BELİRSİZ; log satırı "tick aşama süreleri" var). | kod | `test_no_network_inside_transaction` (yapısal guard) |
| M-14 | `lifecycle.py:580,592` (decision_log/audit commit'ten önce) vs `tick:497` | İstisna `txn.abort()` ile state'i geri alırsa audit/decision_log'da **hayalet kapanış** kalır; ertesi tick aynı pozisyonu başka fiyattan yeniden kapatır → `decision_log`'ta çift kayıt. Kısmi bacakların `trade_id`'si `closed_at`'e bağlı → dedupe edemez. `decision_log.py:60` "deterministic id" iddiası `closed_at` yüzünden yanlış. | kod | `test_aborted_txn_leaves_no_decision_log_rows` |
| M-15 | `paper/state.py:322,424-443` + `Position` zorunlu alanları (`:54-63`) | Tek bozuk/eksik pozisyon kaydı (`sl`/`tp` alanı yok) `TypeError` → **tüm state "corrupt" sayılıp equity/peak/realized sıfırlanıyor** (yedek + `STATE_REPAIRED` audit var). `SCHEMA_VERSION` yazılıyor ama yüklemede hiç doğrulanmıyor. | ✔ equity 87 000 → 100 000 | `test_load_skips_single_bad_record_not_whole_state` |
| M-16 | `paper/execution_sim.py:41`, `state.py:119-124,283-289`, `tick:315` | `unrealized_pnl` `/entry_price` — `entry_price==0` bir pozisyon `ERROR_STATE`'e alınsa da `ps.mtm_equity_usd` `ZeroDivisionError` veriyor → **her tick FAILED**, API `_serialize_state` de düşer ("zehirli pozisyon"). | ✔ | `test_error_state_position_does_not_break_mtm` |
| M-17 | `lifecycle.py:738-740` | Bekleyen `stop` emri tetik fiyatından dolduruluyor (gap'te gözlenen fiyat daha kötü olabilir) → iyimser dolum. | kod | `test_stop_order_fills_at_observed_price_on_gap` |
| M-18 | `apps/api/routers/paper_trading.py:408-421` | `POST /paper-trading/reset` **arşivsiz** siliyor (arşivleyen `/maintenance/reset` ayrı); audit etiketi `STATE_REPAIRED`; testlerde hiç koşmuyor. | grep | `test_reset_archives_first` |
| M-19 | `halt.py:91`, `calibration_store.py:108`, `tf_target_store.py:78`, `rebalance_store.py:217,227,270`, `custom_assets.py:51`, `regime/classifier.py:88`, `agent/llm/budget.py:60` | Düz `write_text` (atomik değil); ratchet testi yalnız `tmp.replace` desenini arıyor. | grep | `test_runtime_json_stores_use_atomic_write` (baseline listesiyle) |
| M-20 | `paper/execution_sim.py` (tüm dosya) | Paper P&L **sürtünmesiz**: ücret/spread/slippage/gecikme yok (`grep` boş); ARCHITECTURE §9 "gerçekçi olmalı" diyor. EV kapısındaki `cost_r=0.1` gerçekleşen PnL'e yansımıyor → öğrenme (kalibrasyon, edge) iyimser. Niyet **BELİRSİZ**. | grep | `test_realized_pnl_includes_configured_costs` (owner kararı sonrası) |
| M-21 | `apps/api/main.py:121-129` | `API_AUTH_TOKEN` tanımsızsa **tüm yazma uçları** (reset, halt reset, manuel emir, chat) açık. Owner kararı K7 (şifresiz tünel); deploy script token'ı yalnız secret varsa set ediyor. | kod | `test_auth_required_when_token_set` (var); uyarı: token yokken `/system/health` owner uyarısı |
| M-22 | `apps/learning_worker/main.py:876→896,973-985`; `learning/tf_scoring_shadow.py` | (a) R5 bloğu `tf_scoring_shadow`'u **önceki** `try` içinde import edilmiş addan kullanıyor (D6 importu patlarsa `NameError` ile yanlış hata etiketi); (b) `run_store.save`/`heartbeat.record` korumasız; (c) adım başına zaman aşımı yok; (d) "shadow" adı + `TF_SCORING_V2_SHADOW` canlı yön kaynağını gizliyor. | kod | `test_learning_run_once_isolates_step_failures`; yeniden adlandırma için eski env adı alias'ı |
| M-23 | `learning/threshold_trainer.py:59-64`; AWS `THRESHOLD_AUTOTUNE=1` | Otomatik değişen eşikler arasında **giriş yönü** eşikleri (`technical.bias_cuts.*`, `adx_trend_min`) var. CLAUDE.md kural #4: "owner onayı olmadan gölge zekâyı yön kararına bağlama." ROADMAP K9: canlı teknik oy v4'ten geldiği için bu eşikler yalnız yedek motoru etkiliyor → etki **BELİRSİZ**. RiskGate eşiği allowlist'te yok (iyi). | kod | owner onayı + `test_autotune_allowlist_excludes_risk_gate` (yapısal) |
| M-24 | `paper/sizing.py:23,59` | `paper_trading.max_position_usd: 25000` aslında "taban notional"; gerçek tavan `1.5×` = 37 500. İsim yanıltıcı; `manual_order` hiç uygulamıyor (M-05). | ✔ | belge + `test_position_never_exceeds_documented_cap` |
| M-25 | `paper/audit.py:29-42` | `ACTIONS` listesi güncel değil ve kullanılmıyor (bkz. §2.1). | grep | listeyi kaldır ya da `test_audit_actions_are_registered` |

**Doğrulanan ve sağlam çıkanlar (olumlu bulgular).** Karar motorunda RiskGate ilk kapı (`engine.py:406-438`: KILL_SWITCH→blocked, RISK_REDUCE/NO_POSITION_INCREASE→hold);
`halt.py` "yalnız kısıtlayıcı" ilkesine uygun; event-risk yalnız WATCH/NO_POSITION_INCREASE üretiyor; `state.Transaction` kilit + revision + `STATE_CONFLICT` audit
doğru çalışıyor; SL bar-kapanış/acil-fren/`price_sanity` zincirinde (H1-H3) kod ile belge uyumlu; `reentry_guard` %94 kapsamlı.

---

## 4. Test boşlukları

### 4.1 Kapsam ölçümü (`pytest --cov=packages --cov=apps --cov-branch`, 2220 test)

Toplam: **%83,5 satır** (25 322 / 29 564), dal **6 865 / 8 992 (%76,3)**.

| Modül (`packages/paper`) | Satır % | Not |
| --- | --- | --- |
| `position_ops.py` | **0,0** (100 satır / 38 dal) | `scale_in`, `flip`, `partial_close`, `set_trailing`, `modify_sltp` **hiç test edilmiyor** — M-11/12/13 burada |
| `ticket.py` | **28,1** | 133 eksik satır; her tick'te üretiliyor |
| `manual_order.py` | **35,6** | yalnız doğrulama dalları; market açılış, bekleyen emir, iptal yolları yok |
| `recheck.py` | 70,9 | verdict dalları (REDUCE/WATCH/EXIT_RECOMMEND) eksik |
| `news_setup.py` | 80,8 | |
| `lifecycle.py` | 86,6 | **short-taraf trailing yok** (`:669-673`), `ERROR_STATE` (`:780-786`), bekleyen-çıkış toparlanması (`:860`), `flatten_all` EXIT_PENDING (`:880`), reentry istisna dalı (`:475-476`), bekleyen emir `continue` dalları (`:720-724`) |
| `maintenance.py` | 86,7 | repair dalları |
| `state.py` | 91,8 | `_LAST_GOOD_RAW` yedeği (`:420`), `_backup_corrupt` hata dalı, Windows kilit dalı, `_disk_revision` hata dalı |
| `guards/state_anomaly.py` | 94,4 | |
| `reentry_guard`, `session_gate`, `manual_queue`, `conviction`, `audit`, `execution_sim` | 94-97 | `manual_queue` yüksek ama **davranış** boşlukları var (M-09/M-10) |
| `sizing.py`, `guards/price_sanity.py` | 100 | satır %100 ama **NaN/inf** davranışı yok (M-06) |

| Modül (`packages/risk`) | Satır % | Not |
| --- | --- | --- |
| `engine.py` (RiskGate) | 98,6 | tek eksik dal: `peak_equity_usd<=0` (`:106`) |
| `halt.py` | 95,7 | eksik: bozuk dosya (`:83-84`, M-07), `peak<=0`, `owner_reset` boş dalı |
| `event_risk.py` | 98,2 | |
| `trade_economics.py` | 84,8 | 34 eksik satır (yapısal stop dalları) |
| `correlation.py` 93,0 · `zone_influence.py` 85,1 · diğerleri 90-100 | | |

> **Satır kapsamı yanıltıcı:** `halt.py` %95,7 ve `engine.py` %98,6 olmasına rağmen M-01/M-03/M-04 yakalanmadı — çünkü
> hatalar *modüller arası etkileşimde* (state ↔ halt ↔ engine ↔ tick).

### 4.2 Eksik testler — öncelik sırasıyla

| # | Test (öneri adı) | Önem | Hedef |
| --- | --- | --- | --- |
| 1 | `test_daily_loss_halt_lifts_after_utc_rollover_without_closes` (+ owner reset sonrası yeniden doğmama) | P0 | M-01 |
| 2 | `test_chat_questions_never_place_orders` + onay adımı + yanıt doğruluğu | P0 | M-02 |
| 3 | RiskGate **bütünsel matris**: {DQS<55, günlük limit, DD realized, DD MTM, max pozisyon, event-risk, halt aktif} × {tick, API, manual approve, manuel emir, bekleyen dolum} → beklenen aksiyon tablosu | P1 | M-03/M-05 |
| 4 | `test_every_size_clamp_is_fail_closed_on_nan_inf` | P1 | M-06 |
| 5 | `test_corrupt_halt_file_fails_closed`, `test_halt_save_is_atomic` | P1 | M-07 |
| 6 | `position_ops` birim testleri (PnL korunumu: parça PnL toplamı = birleşik; kısmi kapama 0/negatif; flip idempotensi; trailing/short) | P1 | M-11/12 |
| 7 | `manual_order.place` başarı yolları (market, limit, stop, stop_limit, iptal) + `_infer_type` sınırları | P1 | |
| 8 | `lifecycle`: short-taraf trailing, `ERROR_STATE`, pending-exit toparlanma, `flatten_all` EXIT_PENDING, gap'te stop dolumu | P1 | |
| 9 | `state`: eksik zorunlu alanlı kayıt, `schema_version` uyuşmazlığı, 2-süreç eşzamanlı yazım (gerçek `multiprocessing`), `_LAST_GOOD_RAW` yolu | P1 | M-15 |
| 10 | Özellik testleri (hypothesis benzeri): equity = başlangıç + Σ(trade pnl); kapanış idempotent; boyut ≤ tavan; SL her zaman kayıp yönünde | P2 | |
| 11 | Kuyruk: TTL, `rejected_signals` budaması, onayda kademe korunumu | P1 | M-09/10 |
| 12 | `smoke`'u güçlendir: yalnız HTTP 200 değil, `dqs.status`, `paper_safe`, şema anahtarları; bu denetimde DQS=19/BLOCKED iken smoke yine "OK" verdi | P2 | |

### 4.3 Yapısal test sorunları

1. **Test config'i ≠ canlı config.** `conftest.py:42-169`: 21 YAML bayrağı varsayılan KAPALI pinleniyor (örn. `risk_gates.mtm_equity_enabled`,
   `exit_close_based_stop`, `exit_structural_stop`, `reentry_guard`, `empirical_pwin`, `correlation_veto`, `sizing_layers.*`,
   `regime_risk_brake`, `trailing_tf_aware`, `dqs_extended_gate`, …), EV/Kelly kapıları monkeypatch ile kapatılıyor ve 17 env bayrağı
   `delenv` ediliyor (`TF_TARGET_AUTO_ONLY`, `DISCOVERY_SCAN_ENABLED`, `TF_SCORING_V2_SHADOW`, …). Golden replay yalnız
   `decide_matrix`'i canlı config ile koşuyor — **paper lifecycle / halt / tick bütünü canlı bayraklarla hiçbir testte yok.**
   Öneri: pin'siz bir `live_config` test kümesi (tick `run_once` + state + halt + lifecycle; sahte snapshot ile).
2. **Golden kapsamı dar** (yalnız karar matrisi); `THRESHOLD_AUTOTUNE`, `TF_TARGET_AUTO_ONLY` vb. bilerek temizleniyor → AWS'teki efektif davranış golden'da yok.
3. **CI kapsamı:** ruff `tests/` ve `scripts/`'i taramıyor — bu denetimde `ruff check tests scripts conftest.py` **27 hata** verdi (22 `I001`, 4 `E741`, 1 `RUF005`; 22'si `--fix` ile otomatik).
   Python **3.11 tek sürüm** (bu denetim 3.13'te yeşil; 3.11 koşusu yapılmadı → BELİRSİZ). Kapsam eşiği yok.
4. **FE'de sıfır test dosyası** (`*.test.*`/`*.spec.*` = 0); FE güvencesi yalnız `tests/test_architecture_guards.py` regex guard'ları + `tsc`.
5. **Ratchet boşlukları:** atomik yazım ratchet'i yalnız `tmp.replace` desenini arıyor (M-19); `audit.ACTIONS` ile gerçek aksiyonlar arasında test yok.
6. `tests/test_architecture_guards.py::test_openapi_schema_ts_in_sync` Node yoksa **SKIP** (CI python job'ında Node yok; web job'ı `codegen --check` ile örtüyor).

---

## 5. Frontend

**Ölçümler:** 149 `.ts/.tsx` dosya, ~28 bin satır el yazması + 9,3 bin satır "generated" klasörü. `tsc --noEmit`: **0 hata**. `pnpm build`: **başarılı**.
`pnpm lint`: **çalışmıyor** (aşağıda). FE test dosyası: **0**.

### 5.1 tsc / lint / build

| Kontrol | Sonuç |
| --- | --- |
| `pnpm exec tsc --noEmit` | ✔ 0 hata (TypeScript 5.9.3, `strict` projede açık) |
| `pnpm build` (Next 14.2.5) | ✔ derlendi. İlk-yük JS: `/` ve `/cockpit` **528 kB**, `/dashboard` 142 kB (three.js + R3F ağır) |
| `pnpm lint` (`next lint`) | ✘ **ESLint yapılandırması yok**; `next lint` etkileşimli kurulum soruyor, `CI=1` ile exit 1. `package.json`'daki `lint` betiği kırık, CI'da çalıştırılmıyor; ESLint bağımlılığı da yok → "lint temiz" denemez |
| CI web job | `pnpm install --no-frozen-lockfile` → kilit dosyası zorlanmıyor (sürüm kayması); `packageManager: pnpm@9.0.0` yazıyor, kilit dosyası pnpm 10 ile okunuyor (bu denetimde `--frozen-lockfile` geçti) |

### 5.2 Kullanılmayan dosyalar (entry'lerden erişilemeyen)

| Dosya | Satır | Not |
| --- | --- | --- |
| `apps/web/lib/panel-registry.ts` | 180 | DASHBOARD_RULES "yeni panel registry'ye eklenir" diyor; dosya **hiçbir yerde import edilmiyor** → kural uygulanamaz durumda |
| `apps/web/hooks/useBriefChanges.ts` | 38 | import eden yok |
| `apps/web/lib/selectors/cockpit-diff.ts` | 120 | yalnız `useBriefChanges` import ediyor (ölü zincir) |
| `apps/web/lib/guards.ts` | 15 | import eden yok |

Yöntem: tüm `.ts/.tsx` import grafiği, `app/**/page|layout|route` giriş noktalarından BFS. 72 panel dizininin hepsi erişilebilir. **DELETE** adayları: yukarıdaki 4 dosya (353 satır).

### 5.3 Sözleşme-önce (contract-first) açığı

- `types/generated/schema.ts` (6369 satır) gerçek `openapi-typescript` çıktısı ve `make codegen-check` ile senkron doğrulanıyor — ama **hiçbir FE dosyası import etmiyor.**
- FE tipleri `types/generated/api.ts` (2928 satır) + `types/uncontracted.ts` (343) **el yazması**; `api.ts` başlığı "Generated … DO NOT EDIT" diyor ama kendi içinde "şu an manuel olarak yazıldı" diyor.
  Koruma yalnız `test_friendly_types_map_to_contract`: **tip adı** OpenAPI şemalarında var mı bakıyor, alan şeklini karşılaştırmıyor → alan düzeyinde kayma yakalanmaz.
- Sözleşmesiz route borcu: 28 (ratchet `tests/contract/contractless_routes.txt`, yalnız küçülebilir ✔).
- Öneri: FE tiplerini kademeli olarak `schema.ts`'ten türet (örn. `paths["/…"]["get"]["responses"]`); `api.ts` başlığını düzelt.

### 5.4 DASHBOARD_RULES uyumu

| Kural | Durum | Kanıt |
| --- | --- | --- |
| Ana ekran yalnız owner'ın baktığı paneller; diğerleri tek "Detaylar" sayfası | ✔ | `app/dashboard/page.tsx` ("Clean E-yAy · Detaylar"); `app/page.tsx` = `CockpitView` (5 satır) |
| Her panel `PanelFrame` (ErrorBoundary + telemetry) içinde | ✔ | 72 panel dizininin hepsi `PanelFrame` kullanıyor (kontrol betiği) |
| `app/page.tsx` büyütülmez | ✔ | 5 satır. Ancak devasa bileşenler başka yerde: `Layer2Labs.tsx` **2201**, `CockpitView.tsx` 1683, `Layer0ReporterAgent.tsx` 1574, `HolographicSignalDeck.tsx` 1488 satır |
| Yeni panel `lib/panel-registry.ts`'e eklenir | ✘ | registry kullanılmıyor (§5.2) |
| **Frontend hesap yapmaz; türetilmiş değerler `lib/selectors/`'tan** | ⚠ ihlaller | `panels/ScenarioPanel/index.tsx:18-60` senaryo olasılıklarını (varlık sınıfı ters-eşleme kuralı `assetBucket` + katman/varlık skorlarını toplama + yüzde normalizasyonu) **bileşende** hesaplıyor (backend'de `packages/scenarios` var); `cockpit/Layer0ReporterAgent.tsx:291` açık pozisyon `size_usd` toplamı; `panels/ExitForensicsPanel/index.tsx:38` toplama; `cockpit/HolographicSignalDeck.tsx:133` en yüksek skor seçimi; `panels/RiskDurumuPanel/index.tsx:78-82,159` olay listesini `(regime as any)` ile süzüp sıralıyor. Mimari guard bunları yakalamıyor (alan listesi dar: `size_usd ?? 0` kalıbı regex'e takılmıyor). |
| Veri kalitesi gösterilen yerde `DataQualityBadge` | ⚠ BELİRSİZ | yalnız 3 yerde kullanılıyor (`DecisionPanel`, `DataQualityPanel`, `CockpitView`); `dqs` alanını okuyan 7 panel (örn. `TradeTicketPanel`, `OptionsVolPanel`, `GovernorPanel`) rozet kullanmıyor — hepsi "kalite göstergesi" mi bilinmiyor |
| 3D sahneler + neon tema korunur | ✔ | `SpaceBrainScene`, `HoloHeadScene`, `QuantumBackplaneScene` mevcut |

### 5.5 Tip güvenliği / hijyen

- `any`/`@ts-expect-error`: 11 kullanım (`RiskDurumuPanel` 78-82,159; `TradeTicketPanel:112`; `HoloHeadScene:162`). `RiskDurumuPanel`'in `(regime as any).event_risk/catalysts` kullanması, bu alanların sözleşmede tiplenmediğini gösteriyor.
- `console.*` 1 kullanım; `dangerouslySetInnerHTML` yok ✔.
- Runtime mock: UI `MockModeBanner` ile uyarıyor; mock verisi FE kodunda yok ✔.

---

## 6. Mevcut durum — komut sonuçları

Ortam: Linux sandbox, **Python 3.13.16**, pytest 9.1.1, ruff 0.17.0, FastAPI 0.143.0, pydantic 2.14.1; Node 22, pnpm 10.28.0. (CI: Python 3.11, Node 20.)
Hepsi repo kopyasında çalıştırıldı; kaynak ağaçta `git status` denetim boyunca boştu (yalnız bu rapor eklendi).

| Komut | Sonuç |
| --- | --- |
| `make test` (= `pytest`, `--basetemp=.pytest_tmp`) | ✔ **2220 passed**, 1 warning, 66 sn. (Node kurulmadan önceki ilk koşu: 2219 passed, **1 skipped** — `test_openapi_schema_ts_in_sync`; Node kurulunca geçti.) Golden replay ve mimari guard'lar dahil. |
| `python -m tests.golden.golden_replay --check` | ✔ **BAYT-AYNI** |
| `make lint` (`ruff check packages apps/api apps/tick_worker apps/learning_worker apps/supervisor`) | ✔ All checks passed |
| `ruff check tests scripts conftest.py` (CI dışı) | ✘ 27 hata (22 `I001`, 4 `E741`, 1 `RUF005`) |
| `make codegen` | ✔ `schema.ts` yazıldı (223 434 bayt); `git diff` boş (senkron) |
| `make codegen-check` | ✔ "generated types match contracts/openapi.yaml" |
| `pnpm exec tsc --noEmit` | ✔ 0 hata |
| `pnpm build` | ✔ başarılı (Next 14.2.5) |
| `pnpm lint` | ✘ yapılandırılmamış, etkileşimli, exit 1 (§5.1) |
| `make smoke` | ✔ **PASS=8 FAIL=0** — API (`python -m apps.supervisor`, `RUN_WORKERS=false`, 127.0.0.1:9000): `health`, `system/health`, `cockpit/brief`, `data/snapshot`, `decision/matrix`, `replay/status`, `learning/summary` 200; `paper_safe=true · no_execution`; web SSR (`next start` :4000) 200. Sunucular koşudan sonra kapatıldı. |

**Smoke'un sınırı (dürüstlük notu).** Sandbox'ta piyasa-verisi sağlayıcılarına çıkış yok: `data/snapshot` → `dqs.score=19`, `status=BLOCKED`,
"veri yok: BTCUSD, ETHUSD, …"; `system/health` uyarıları `worker_stale`, `snapshot_store_empty`. Yani smoke yalnız HTTP/şema canlılığını doğruladı;
**veri kalitesi / karar içeriğini doğrulamadı** (ve DQS BLOCKED iken bile "SMOKE OK" döndü — bu da smoke'un zayıflığı). DQS<55 → KILL_SWITCH → "karar yok"
davranışı ise beklenen şekilde fail-closed çalıştı. Tick/learning worker'lar bu ortamda başlatılmadı (ağ yok → anlamlı çıktı üretmez); onların davranışı yalnız birim/entegrasyon testleriyle ve repro betikleriyle sınandı.

---

## 7. Önerilen iş sırası

Kurallar: **tek tema / küçük PR**, `golden_replay --check` bayt-aynı (bilinçli mantık düzeltmesi hariç, fark PR açıklamasına), Backend FREEZE → önce yalnız **P0 hotfix**,
gerisi owner onayı / freeze kalkışıyla. "Owner" sütunu: değişiklik bir kapıyı gevşetiyor ya da politika seçiyorsa onay şart. Hiçbir öneri PAPER_SAFE/RiskGate/LLM/sözleşme ilkelerini gevşetmez.

| PR | Başlık / kapsam | Tür | Risk | Golden | Owner kararı | Bağımlılık |
| --- | --- | --- | --- | --- | --- | --- |
| **PR-00** | Bu rapor (`AUDIT_REPORT.md`) | docs | Yok | — | — | — |
| **PR-01** | **M-01** günlük PnL gün dönümü: `_ensure_daily_anchor` tick başında + `RiskInput` okuma yollarında; regresyon testleri (canlı YAML) | **P0 hotfix** | Düşük-orta (RiskGate girdisi; dokümante davranışa dönüş) | Beklenen bayt-aynı (golden `decide_matrix`, sabit girdi) — doğrulanmalı | **Evet** (H11'in uygulanışı) | — |
| **PR-02** | **M-02** chat emir yolu: soru/koşul cümlelerini ayrıştırma, açık onay adımı, doğru yanıt metni, `_PENDING_ORDER` oturum-başı, halt/KILL_SWITCH altında red | **P0 hotfix** | Düşük (yalnız kısıtlıyor; UX'e +1 adım) | Etkilemez | Kısmen (onay adımı UX) | — |
| PR-03 | Test-only: `position_ops`, `manual_order`, `lifecycle` (short trailing, `ERROR_STATE`, gap dolumu), `state` (bozuk kayıt, çok-süreç), `recheck` | test | Yok | — | — | — |
| PR-04 | Test-only: **canlı-config entegrasyon kümesi** (pin'siz YAML, tick+halt+lifecycle senaryoları; M-01/M-03 regresyonları) | test | Yok | — | — | PR-01 |
| PR-05 | **M-08** chat ticket cevabı (`ticket.load_last()`), `packages→apps` bağımlılığını kaldır | düzeltme | Çok düşük | Etkilemez | — | — |
| PR-06 | **M-07** `halt.py`: atomik yazım + bozuk dosyada yedek/audit/fail-closed | düzeltme | Düşük-orta (bozuk dosyada davranış seçimi) | Etkilemez | Küçük (fail-closed seçimi) | — |
| PR-07 | **M-06** ortak `clamp_size()` (NaN/inf → 0) + yapısal guard | düzeltme | Düşük | Bayt-aynı beklenir (NaN yok) | — | — |
| PR-08 | **M-03** tek `risk_input_from_state()` fabrikası (MTM dahil) + MTM ihlali politikası | düzeltme | **Orta** (flatten davranışı değişebilir) | Etkilemez | **Evet** (MTM ne yapsın?) | PR-04 |
| PR-09 | **M-04** `halts/reset` için açık `rebase_peak` aksiyonu (audit'li) veya belgeyi düzelt | düzeltme | Orta (gate gevşetme) | Etkilemez | **Evet** | PR-08 |
| PR-10 | **M-05 / M-24** manuel emir politikası (A: RiskGate/halt/tavan uygula, B: belgeli muafiyet) + `max_position_usd` adı/semantiği | politika | Orta | Etkilemez | **Evet** | PR-02 |
| PR-11 | **M-09 / M-10** manual_ready: onayda kademe/güven taşı (additive alanlar), TTL, `purge_stale_rejection` bağla, eski fiyatla onayı reddet | düzeltme | Orta (state şeması additive) | Etkilemez | Kısmen (TTL süresi) | PR-03 |
| PR-12 | **M-11 / M-12 / M-13** `position_ops`: harmonik ortalama, miktar doğrulama, ağ I/O'yu kilit dışına | düzeltme | Düşük | Etkilemez | — | PR-03 |
| PR-13 | **M-19** atomik olmayan 7 store → `write_text_atomic` + ratchet'i `write_text` desenine genişlet | düzeltme | Düşük | Etkilemez | — | — |
| PR-14 | **M-14 / M-15 / M-16** state/lifecycle sağlamlık: yan etkileri commit sonrasına al, tek bozuk kayıtta tüm state'i sıfırlama, sıfıra bölme koruması | düzeltme | Orta | Etkilemez | — | PR-03 |
| PR-15 | Temizlik: ölü kod (6 çağrısız sembol, boş paket, `tf_size_cap`, FE 4 dosya) | temizlik | Düşük | **Bayt-aynı zorunlu** | — | — |
| PR-16 | Temizlik: tick'teki `news_prepared_setups` hattını (T-5) kaldır (state alanı additive-deprecate + 2 API alanı) | temizlik | Orta (sözleşme + state) | Etkilemez | **Evet** | PR-15 |
| PR-17 | FE hijyen: ESLint kur / `lint` betiğini düzelt, CI'ya ekle, `pnpm install --frozen-lockfile`, `any` temizliği | araç | Düşük | — | — | — |
| PR-18 | FE kural uyumu: `ScenarioPanel` ve diğer bileşen-içi hesapları backend/selector'a taşı; `panel-registry.ts` ya bağla ya sil; guard regex'ini genişlet | düzeltme | Düşük-orta | — | Kısmen | PR-17 |
| PR-19 | Sözleşme: FE tiplerini `schema.ts`'ten kademeli türet; `api.ts` başlığı/alan-şekil guard'ı | düzeltme | Orta (geniş yüzey, kademeli) | — | — | PR-18 |
| PR-20 | CI: Python 3.11+3.13 matrisi, bağımlılık sabitleme, `ruff` kapsamını `tests/`'e genişlet (`--fix` ile 22/27), `paper`/`risk` kapsam eşiği, smoke'a içerik doğrulaması | araç | Düşük | — | — | — |
| PR-21 | Docs: ARCHITECTURE §7.5/§8/§9, STATE.md (MTM, günlük sıfırlama), `audit.ACTIONS`, adlandırma (`TF_SCORING_V2_SHADOW` için alias planı) | docs | Yok | — | — | PR-08/PR-09 sonrası |
| PR-22 | Learning worker dayanıklılığı: adım-başı zaman aşımı + izolasyon, `run_once` bölme, `NameError` bağımlılığı, final `save/heartbeat` koruması | düzeltme | Orta | — | — | PR-04 |
| PR-23 | Owner kararı gerektiren konfigürasyon temizliği: T-3, W-10 (M-23), W-21, W-29, W-30, W-35 | politika | Düşük | — | **Evet** | — |

**Önerilen sıra:** PR-01 → PR-02 (hotfix, freeze içinde) → PR-03/PR-04 (güvenlik ağı) → PR-05 / PR-06 / PR-07 → owner kararları PR-08…PR-10 →
PR-11…PR-14 → temizlik PR-15/16 → FE/CI PR-17…PR-20 → docs PR-21 → PR-22/23.

---

## Ek A — Değişmez kurallar kontrolü

| Kural | Durum | Kanıt / not |
| --- | --- | --- |
| PAPER_SAFE yapısal: `place_order/submit_order/execute_order/ccxt/broker` yok | ✔ | Kodda yasak sembol yok (yalnız guard testlerinde geçiyor). `manual_order.place` paper pozisyon açar, broker çağrısı yok. |
| `/system/health` daima `paper_safe=true`, `no_execution=true` | ✔ | Canlı çağrıda doğrulandı; ama `ops/system_health.py:175-176` **sabit literal** (bir yapısal denetimden türetilmiyor). Paper keşif açılışı ayrıca `PAPER_ONLY`+`NO_EXECUTION` env'ine bağlı (`paper_policy.environment_allows`). |
| RiskGate final ve yalnız kısıtlayıcı; hiçbir gate gevşetilmez | ⚠ | Karar motorunda ✔ (`engine.py:406-438`). İhlal/zayıflık: M-05 (manuel yollar), M-06 (NaN fail-open), M-07 (halt kaybı), M-03 (MTM flatten yok). |
| LLM yalnız narrative üretir, karar vermez | ⚠ | LLM kararı etkilemiyor; ancak **narrative katmanı (chat) deterministik ayrıştırıcıyla paper state'i değiştiriyor** (M-02). |
| `contracts/openapi.yaml` tek doğruluk kaynağı; tipler `make codegen` ile | ⚠ | `schema.ts` senkron ✔ ama FE kullanmıyor; FE el yazması `api.ts` (§5.3). Route ratchet ✔ (28 borç). |
| Runtime'da mock yok | ⚠ | Mock opt-in env'leri var (`PRICE_USE_MOCK` vb.), varsayılan kapalı + UI uyarısı. |
| Backend FREEZE: yalnız P0 hotfix | ✔ (bu denetim) | Hiçbir kaynak değişmedi. Öneriler P0 hotfix'i (PR-01, PR-02) ayırdı. |

## Ek B — Repro betikleri (özet)

Tümü repo kopyasında, izole geçici dizinle (`PAPER_STATE_PATH`, `RISK_HALT_PATH`, … env'leri) çalıştırıldı; üretim `data/runtime`'a dokunmaz.

**B-1 (M-01)**
```python
# dünkü anchor, daily_pnl=-300, equity 9700, pozisyon yok, DAILY_LOSS dün açılmış
ps = S.load()
inp = RiskInput(dqs_score=90, equity_usd=ps.equity_usd, peak_equity_usd=ps.peak_equity_usd,
                daily_pnl_usd=ps.daily_pnl_usd, open_position_count=0)
H.sync(inp)        # -> [('DAILY_LOSS','RISK_REDUCE','<bugün>')]   (yeniden doğdu)
evaluate(inp)      # -> RISK_REDUCE
H.owner_reset(); H.sync(inp)   # -> yine DAILY_LOSS
lifecycle._ensure_daily_anchor(ps); ps.daily_pnl_usd  # -> 0.0
```

**B-2 (M-02 / M-05)**
```python
chat._parse_manual_order("eth'de satış baskısı var mı, 2000 dolar pozisyon açsam ne olur?")
# -> {'symbol':'ETHUSD','side':'short','size_usd':2000.0,'entry_price':None}
H.save(HaltState([HaltEvent(type="MAX_DRAWDOWN", level="KILL_SWITCH", ...)]))
manual_order.place("BTCUSD","long",20000.0)   # -> kind=market, size_usd=20000.0  (açıldı)
```

**B-3 (M-03)**
```python
# 25k long, fiyat -%40 ; risk_gates.mtm_equity_enabled=true (canlı YAML)
evaluate(RiskInput(..., mtm_equity_usd=90_000))  # -> KILL_SWITCH  'DD(mtm) 10.0% ≥ 8%'
H.sync(same_input)                               # -> []  (flatten tetiklenmez)
evaluate(RiskInput(...))                         # API girdisi (mtm yok) -> HOLD
```

**B-4 (M-04)**
```python
H.sync(inp_dd9pct)   # MAX_DRAWDOWN
H.owner_reset()      # temizlendi, aktif []
H.sync(inp_dd9pct)   # MAX_DRAWDOWN tekrar (peak aynı)
```

**B-5 (M-06)**
```python
sizing.compute_size_usd(float("nan"), max_position_usd=25000)  # 37500.0
max(0.0, min(1.5, float("nan")))                                # 1.5
```

**B-6 (M-07)** `risk_halts.json` içeriği yarım JSON → `H.active_halts()==[]` ve `H.sync(...)==[]`.

**B-7 (M-08)** `ticket.save_last([{… "status":"active" …}]); chat._tickets_answer(None)` → `['tickets:none']`.

**B-8 (M-09)** `route_to_manual_ready(size_multiplier=0.35)` → `approve(...)` → `tier='NEUTRAL', size_usd=8750.0, predicted_confidence=None, data_verified=False`; güven 0,25 (WEAK) otomatik yol ≈ 2625 USD.

*Not:* betikler kopya ağaçta ve scratch dizinde tutuldu; depoya eklenmedi (bu PR yalnız bu dosyayı içerir).
