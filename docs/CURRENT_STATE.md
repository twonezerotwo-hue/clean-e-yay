# Current State — Clean E-yAy

_Bu dosya kısa ve güncel tutulur. Her görev sonunda güncellenir._

## Last known status

- **Katman 0 chat — gerçek SSE streaming + kalite yeniden tasarımı** (2026-07-04,
  owner talebi: "eski yazı yeniden akıyor + cevaplar 1. sınıf değil"):
  - **Kök neden 1 (UX)**: Layer0ReporterAgent'taki sahte daktilo efekti
    `modelMode` değişince resetlenip ESKİ cevabı baştan akıtıyordu → efekt
    tamamen SİLİNDİ; klasik sohbet akışı (append-only transcript, yalnız aktif
    cevap akar, otomatik dibe kaydırma, caret sadece akan mesajda).
  - **Kök neden 2 (kalite)**: lokalde Ollama-first 7B + "parafraz" prompt'u →
    chat için `get_chat_client()` **Groq-önce** ([Groq, OpenRouter, Ollama];
    `CHAT_LLM_LOCAL_FIRST=1` eski sıra, lokal-only flag, conftest delenv'li).
    Persona raporları (`get_client`) lokal-önce KALDI. Prompt: gerçek çok-turlu
    messages (history user/assistant rolleriyle) + FAKT bloğu; `_PROMPT_VERSION=v3`.
  - **Yeni endpoint** `POST /api/v1/chat/stream` (SSE; additive, /chat durur):
    `status → meta → delta* → done` — done OTORİTE (FE biriken metni done.answer
    ile değiştirir; kesinti/bulgu-düşürme düzeltmesi böyle taşınır). Guard reddi /
    manuel emir–pozisyon op (artık LLM'e GİRMEZ, `deterministic_command`) /
    cache-hit / LLM-off → delta'sız tek done. Endpoint+generator bilerek sync def
    (threadpool; async'te blocking urllib loop'u kilitler).
  - **client.py**: Groq/OpenRouter (OpenAI SSE) + Ollama (NDJSON) + Mock
    `stream()`; FallbackLLMClient.stream ilk yield'den sonra kilitlenir.
  - **FE**: `apps/web/lib/api/chatStream.ts` (fetch+ReadableStream SSE parser);
    stream başlayamazsa non-stream /chat fallback. TTS done'da; PTT/sessiz mod
    korundu. globals.css: `layer0-chat-*` balonları; ölü transcript CSS silindi.
  - **Validation**: pytest 1401 (19 yeni: test_chat_stream, test_llm_client_stream)
    — tam koşuda 1 çakışan test (test_openapi_schema_ts_in_sync) Node OOM'du,
    tek başına geçiyor; make lint kapsamı temiz; codegen senkron; tsc + .next-prod
    build yeşil; smoke 8/8; canlı doğrulama (izole 9060/4101): curl'de token-token
    delta, UI'da eski mesaj sabitken yeni balon status→akış→final yaşam döngüsü.
  - **NOT (lokal deploy)**: canlı API (9000) hâlâ eski süreç — yeni endpoint için
    API restart + `.next-prod` zaten rebuild edildi, `next start` restart'ı yeter.

- **E serisi tamamlayıcı — aktivasyon güvenliği + görünürlük** (2026-07-03,
  rapor-üstü denetim; roadmap E-6/E-7/E-8). Rapor değerlendirmesinden çıkan 3
  gerçek eksik kapatıldı (geri kalan öneriler ya zaten vardı ya kapsam dışı —
  aşağıda):
  - **E-6 — aktivasyon izleme deliği**: E flag'leri (`TF_TARGET_AUTO_ONLY`,
    `TF_TARGET_EDGE_GATE`, `EXIT_FORENSICS_NUDGE`) `activation_watchdog.
    REGISTRY`'de yoktu → açılınca bozulma izlenmiyordu. Diğer 16 flag gibi
    kaydedildi. **Kritik sıralama**: watchdog yalnız `last_seen=False→ON`
    geçişinde baseline damgalar; bu yüzden kayıt (flag'ler OFF) ile aktivasyon
    AYRI commit/deploy — aksi halde ilk görüşte zaten-ON sayılıp monitör
    kurulmaz.
  - **E-7 — $ güvenilirlik göstergesi**: `dataset_health.coverage.
    size_usd_pct` + DatasetHealthPanel "$ boyutlu (çıkış tahmini)" çubuğu.
    Forensics dolar rakamlarının ne kadarı kesin (size_usd) vs notional-çıkarım
    vekili olduğunu gösterir. Rapor'un "Exit Coverage Monitor"ı — yeni panel
    değil, mevcut panele additive.
  - **E-8 — flag sapma guard'ı**: `scripts/flag-sync-check.sh` lokal `.env` ↔
    AWS `deploy-from-github.sh` davranış-flag sapmasını görünür kılar
    (ensure_env yalnız-yoksa-ekle olduğu için sapma mümkündü). `test_flag_sync`
    CI'da checker'ın kör-noktası olmadığını zorlar. Canlı: 11 flag, sapma yok.
  - **Rapor'dan REDDEDİLENLER** (kanıtla): "TRAIL_AUTOTUNE kapalı" YANLIŞ (iki
    ortamda da AÇIK); "Auto-only Scoreboard 10/10 acil" bu sabah zaten yapıldı
    (commit a87f4408, summary `cohorts` bloğu); "no_excursion MAE/MFE zorunlu
    takip" gereksiz (yeni pozisyonlarda zaten zorunlu, 40 eski miras);
    "Position Management modülü" KIRMIZI ÇİZGİ (yeni modül = owner "derinleştir,
    kurma" kararı ihlali). EDGE_GATE aktivasyonu da REDDEDİLDİ: kodu ON=kısıtla-
    yıcı, deploy bugün bilinçle `set_env 0` ("aktif çalışsın") — owner kapalı
    tutmayı onayladı.
  - **AKTİVASYON (ayrı, sıradaki commit)**: `TF_TARGET_AUTO_ONLY=1` (lokal .env
    + deploy ensure_env). EDGE_GATE=0 kalır. NUDGE 2 hafta shadow sonrası.
  - **Validation**: hedefli testler + contract 58 + tsc + ruff (CI scope) temiz;
    codegen idempotent (dataset-health kontratsız, friendly tip elle).

- **E serisi — Çıkış/Stop öğrenme makinesi derinleştirme** (2026-07-03,
  denetim paketi; bkz. docs/AUDIT_ROADMAP.md E-1…E-5): Otomatik sistem net
  −$864/133 AUTO işlem; zararın kaynağı çıkış kalitesi (SL_HIT 38 işlem
  −$1978 vs TP_HIT 22 işlem +$3313). Yeni modül kurulmadı — mevcut CP4
  makinesi (tf_target_trainer + entry_exit_quality + store/rollback)
  derinleştirildi. 5 dilim:
  - **D1 `size_usd`** (flag'siz additive): decision_log outcome bloğu +
    `CanonicalOutcome.size_usd` (legacy → None) — $ maliyeti tahmin yerine
    kesin (notional çıkarımı başabaş time-stop'ta çöker).
  - **D2 `packages/learning/exit_forensics.py`** — "Çıkış Otopsisi",
    salt-gözlem: yalnız AUTO kohort; TF × kapanış-kategorisi bucket;
    trailing give-back/capture, time-stop kaçan hareket (never_worked =
    giriş sorunu, çıkış maliyetine girmez), SL üçlü sınıf (roundtrip /
    straight-hariç / gray-atıfsız); tüm $ alanları `*_usd_est` (size_usd
    tercih → notional çıkarım |pnl_pct|≥0.05 → None); en pahalı 3 hata
    Türkçe düz-dil kart; kapanış-sonrası karşı-olgu YOK. Worker snapshot
    `data/runtime/exit_forensics.json` {latest, history≤60} + run meta
    `exit_forensics_status` (canlı: usable=133 buckets=16 top_costs=3).
  - **D3 API+kontrat+dashboard**: `GET /learning/exit-forensics`;
    `/learning/tf-targets`e additive `coverage` (status trainer'ın FİİLEN
    kullandığı sayıya bakar; canlı: 1d dürüstçe "EĞİTİLMEMİŞ 13/20" —
    havuzlama/eşik indirme REDDEDİLDİ) + `trainer_inputs`. YENİ
    `ExitForensicsPanel` (Cockpit grup 03, EntryExitQuality'den sonra);
    TfTargetsPanel coverage çipleri + flag rozetleri. Frontend hesap yapmaz.
  - **D4 `TF_TARGET_AUTO_ONLY`** (env, DEFAULT OFF=bayt-aynı): ON →
    trainer VE entry_exit_quality dataset'i yalnız AUTO kohort (verified
    MANUEL sızıntısı biter — sabah kapatılan TF_CALIBRATION deliğinin
    kardeşi; tek flag iki tüketici). `audit_note` dataset damgalı.
  - **D5 `EXIT_FORENSICS_NUDGE`** (env, DEFAULT OFF=sabit ±%10 bayt-aynı):
    ON → adım = 0.05 + 0.10×şiddet, klamp [0.05, 0.15] = AUTO_APPLY_BAND
    tavanı (hibrit kapı yapısal korunur); şiddet önce
    `exit_forensics.trainer_evidence()`, yoksa TfStats fallback;
    `TfNudge.step_source`+`evidence` additive.
  - **Rollout**: SHADOW ≥2 hafta (panel $ ↔ OutcomeLedger by_close_reason
    mutabakatı) → `TF_TARGET_AUTO_ONLY=1` → `TF_TARGET_EDGE_GATE=1` →
    `EXIT_FORENSICS_NUDGE=1`; hepsi lokal .env + deploy ensure_env birlikte.
  - **Yan bulgu/fix**: apps.api.main import'u .env'i os.environ'a yüklüyor;
    sabah açılan `TF_CALIBRATION_AUTO_ONLY=1` tam suite'te tf_calibration
    testlerine sızıp 8 testi kırıyordu — conftest'e delenv eklendi (aynı
    desen: testler baseline varsayar, flag testleri kendisi setenv yapar).
  - **Validation**: pytest tam suite **1376 passed** (+44 yeni: 15
    exit_forensics, D1 size_usd, D4/D5 trainer, coverage flag testi);
    contract 58 yeşil; ruff CI-scope temiz; codegen idempotent; tsc +
    `pnpm build` + `.next-prod` build yeşil; worker koşusu
    exit_forensics=OK; canlı :9000 exit-forensics/tf-targets 200 + :4000
    web 200 (API+web yeni kodla restart edildi).

- **Layer 0 hologram sohbet kalite paketi** (2026-07-03): owner şikayeti
  (robotik/aynı cevap, soru anlamama, İngilizce haber, jargonlu brifing) —
  4 kök neden düzeltildi; karar zinciri sıfır diff, anlatı katmanı only:
  - `briefing.py _executive`: "Patron/hücre/kanaat/skor 67/55/NEUTRAL" jargonu
    → düz kurumsal Türkçe; sinyalin YÖNÜ (alış/satış) ve sayıların anlamı
    (eşik açıklaması) artık söyleniyor. Sembol/TF/rejim TR haritaları eklendi.
  - `llm/chat.py answer()`: LLM artık hazır cevabı papağanlamıyor — soruya
    kendi cevabını üretiyor; anahtar kelime eşleşmeyen sorular "intent:overview"
    işaretiyle "bağlamdan kendin yanıtla" talimatı alıyor. Chat temperature 0.5
    (client'lara opsiyonel `temperature` parametresi; persona raporları 0.2'de).
  - Canlı web (Tavily) bulguları için prompt'a TÜRKÇEYE ÇEVİR talimatı —
    "son 1 saat haberleri"nin İngilizce okunması bitti (LLM yolunda).
  - Sohbet geçmişi uçtan uca: `ChatTurn` şeması (openapi + codegen), router
    `history[]` kabul eder, 3 FE yüzeyi (Layer0/ChatPanel/NotificationBell)
    son 6 turu gönderir → takip soruları bağlamıyla anlaşılır. Cache anahtarına
    history hash'i eklendi. `guard.SYSTEM_RULES` üslubu: soruya-doğrudan-cevap.
  - Follow-up (owner canlı testi): "btc nin verilerini ver" → yanlış rota
    (bare-symbol → why_no_trade → "verileri yok" saçmalığı). Fix: `_ANALYZE_INTENT`
    veri-isteme kelimeleri (veri/göster/durum/bilgi/detay/özet) + çıplak sembol
    default'u teknik analize döndü; cache anahtarına `_PROMPT_VERSION` eklendi
    (eski üslup 2 saat cache'ten dönmesin).
  - Kök neden (canlı): **Ollama süreci ölüydü** — chat sessizce deterministik
    şablona düşüyordu ("robotik" şikayetinin ana kaynağı). start-dashboard.ps1
    artık 11434 sağlıksızsa `ollama serve` başlatır (keeper 20sn döngüsü).
  - **Validation**: pytest 1332 passed (tam suite; test_ai_report_no_actionable_
    when_dqs_blocked tek-koşumda ortam bağımlı flake — main'de de aynı, gdelt/
    no_network); ruff temiz; codegen senkron; tsc temiz; `.next-prod` build yeşil;
    canlı uçtan uca doğrulama (briefing + history'li chat + haber çevirisi + BTC verisi).

- **F2-1 (gözlem fazı) — Mark-to-market SALT-GÖZLEM alanları** (2026-07-02):
  denetim yol haritasının (docs/AUDIT_ROADMAP.md) F2-1 ilk yarısı. RiskGate
  bugüne dek yalnız realized `equity_usd` görüyordu; açık pozisyonların MTM'i
  hiçbir yerde toplu raporlanmıyordu. **Davranış sıfır diff — gate'e bağlama
  YOK**, yalnız gözlem:
  - `PaperState.unrealized_pnl_usd` / `mtm_equity_usd` türetilmiş property
    (persist edilmez; değerleme tek kaynak `execution_sim.unrealized_pnl`).
  - tick_worker: snapshot `paper_state_summary`'ye + cycle-sonu heartbeat'e
    `unrealized_pnl_usd`/`mtm_equity_usd` yazar (FAILED/learning → None).
  - `system/health` worker view alanları geçirir (legacy heartbeat → None);
    `WorkerHealth` sözleşmesine additive nullable alanlar + codegen.
  - Bant gözlemi: snapshot store'daki `mtm_equity_usd` serisi izlenecek;
    RiskInput'a bağlama ayrı tarihli owner kararı (flag'li) — F2-1 ikinci yarı.
  - **Validation**: pytest **1189 passed** (+7 yeni: `test_mtm_observation.py`
    + tick entegrasyonu); ruff değişen dosyalarda temiz; codegen çalıştı.

- **GOVERNOR — Self-Managing (observe-only) katman tamamlandı** (2026-06-28):
  raporda istenen 4 parça eklendi; var olan modüller (learning/shadow/mode) ÜSTÜNE
  ince orkestrasyon — yeni karar/risk motoru DEĞİL. **Additive; mevcut hiçbir şey
  bozulmadı.** PAPER_SAFE / NO_EXECUTION; RiskGate/DQS/KillSwitch/halt sıfır diff.
  - **Part 1 — Öneri Defteri** (`packages/governor/proposals.py`): her tipte
    owner-onaylı öneri + kanıt. **DEĞİŞMEZ:** approve YALNIZCA defter kaydını
    günceller; canlı config (weights/thresholds/risk/mode) değişmez — uygulama
    mevcut owner-gated yollardan (rebalance/mode store). Testle kilitli.
  - **Part 2 — Görev Kuyruğu** (`packages/governor/tasks.py`): P0–P4 observe-only
    görevler; **`can_change_policy` yapısal olarak hep False**, handler'lar yalnızca
    read-only özet okur (config/paper/RiskGate'e yazamaz). `generate()` mevcut
    store sinyallerinden görev üretir (dedup'lu, crash-safe).
  - **Part 3 — Governor Worker** (`apps/governor_worker/` + `run_store.py`):
    4. süreç, learning_worker deseni (run_once + zamanlayıcı, restart-always DEĞİL).
    **`attempt_open` ASLA çağrılmaz** (import bile etmez — testli); açılış tek kapıda
    (tick_worker) kalır. Supervisor'a bağlandı (`RUN_GOVERNOR`/`GOVERNOR_INTERVAL_SEC`,
    default 900s; üç-süreç bağımsızlığı korunur, çökerse diğerlerini etkilemez).
  - **Part 4 — Dashboard + sözleşme**: openapi.yaml governor path/şemaları +
    `make codegen` (schema.ts) + api.ts friendly types (drift guard yeşil). Yeni
    "Governor" paneli grubu: GovernorPanel (özet + görev üret) / ProposalPanel
    (onayla/reddet) / TaskQueuePanel (koştur). page.tsx büyütülmedi (PanelGroup);
    frontend hesap yapmaz.
  - `packages/governor/report.py`: read-only aggregator (best-effort; bir kaynak
    patlasa rapor düşmez) — "ne öğrendi / buldu / öneriyor / onay bekliyor / hangi
    veriye güvenmiyor".
  - **Validation**: pytest **1000 passed** (+28 governor, +3 sözleşme GET);
    ruff yeni dosyalar temiz (baseline değişmedi); codegen-check OK; mimari guard'lar
    yeşil; `tsc` temiz; `next build` ✓ (`/dashboard` 44.3 kB).

- **SOAK1 + FULL SYSTEM AUDIT tamamlandı** (2026-06-14): production-like local
  dry-run + uçtan uca sistem denetimi. **Çalıştırma/gözlem/audit — KOD SIFIR DİFF**
  (docs hariç). Stack izole portlarda (`API 8060` / `Web 3060`); eski `E_YAY CODEX`
  LaunchAgent (`com.eyay.backend → *:8000`) tespit + **dokunulmadı**.
  - **SOAK1** (~25 dk izlenen / ~28 dk uptime, 11 sample): snapshot_count **8→53**
    (ring buffer cap 500), tick cycle **6→51**, **stale yok**, dqs **OK** sabit,
    api/web http **200** sabit, halt persistent (seeded 2026-06-13). Loglarda **0
    error/traceback**; tek tekrarlı uyarı `active halts` (beklenen). Disk 3.9M
    (sınırlı). Smoke **8/8** ×2. learning one-shot startup seed (restart-always
    değil; >1h için zamanlayıcı gerekir).
  - **AUDIT** (13 başlık): Git `main`/HEAD `dfe6c0f`/origin sync/clean. Safety:
    broker/exec grep **0**; `paper_safe`/`no_execution` yapısal `True`; replay
    stored-only (refetch yok, paper açmaz); LLM explanatory-only (state-write 0,
    injection guard); weights owner-gated; 1w paper kapalı. RiskGate: matrix
    **20/20 hücre `risk_gate` KILL_SWITCH ile blocked** (global uniform, aday ham
    sinyal korunur). Modül sınırları temiz (data↛decision/risk/paper, risk↛decision,
    service↛apps.api, wildcard yok). Validation: pytest **419/419**, ruff/tsc
    **clean**, next build **✓** (`/` 334 kB), contract+codegen drift **yeşil**.
  - **Sonuç: release-ready. P0 yok · P1 yok · P2 = gözlem** (provider degraded
    coingecko/fred [FRED_API_KEY yok + BTCUSD/ETHUSD veri yok, mock'a düşmez];
    aktif halt taze baseline için owner reset ister; learning 7/24 scheduler;
    eski LaunchAgent port çakışması). Backend FREEZE korundu.
  - Commit: `docs(release): record full system audit results`.

- **UX4 — Live Feedback Polish tamamlandı** (2026-06-14): canlı cockpit
  okunabilirlik cilası — yeni panel/veri yok, mevcut componentler sadeleştirildi.
  **Frontend-only**; backend FREEZE korundu (packages/ + apps/* SIFIR diff;
  openapi/TS değişmedi → codegen drift otomatik yeşil). Frontend hesap yapmaz;
  selector/brief korundu. 7 panel dokunuldu:
  - **Market structure impact-first** (OptionsVol · Volatilite · Kripto Türevleri):
    kartın üstünde tek belirgin "karar etkisi: …" satırı; teknik sayılar (ATM IV /
    rv / funding-OI / skew / term) altta + daha küçük (white/60). Alttaki **duplicate
    impact rozeti kaldırıldı** (önce yalnızca OptionsVol'deydi → 3 panele yayıldı).
  - **TimeframeMatrix**: market-structure banner özetleri `capList` ile ilk 3 etki +
    "+K" (detay expert panelde); global gate'te hücreler gate'i tekrar etmez (üstte
    tek banner; UX1 davranışı korundu).
  - **News**: ilk 6 başlık görünür, kalanlar `<details>` altında collapsed; ham
    haber Macro/Catalyst expert grubunda kalır; uzun başlık `break-words`.
  - **Catalyst**: expired / unknown / context-only (rumor dahil) muted (opacity-50);
    aktif CAUTION / NO_POSITION_INCREASE sol kenar renkli vurgu ile daha belirgin.
  - **AgentBrief**: hard-stop (HALT/DQS_BLOCKED/PROVIDER_DOWN) ilk ekranda
    yüksek-görünür ⛔ banner ("YENİ İŞLEM YOK — {main_blocker.label}"); soft RISK_GATE
    ⚠ magenta. `main_blocker` backend cockpit'ten (frontend hesap yok).
  - Copy/Learning zaten temizdi (UX1/UX2): AIReport/DecisionPanel tek `main_blocker`
    (stale "DQS BLOCKED veya risk gate" yok), LearningPanel insufficient tek satır +
    muted metrik → **dokunulmadı**.
  - tsc temiz; next build ✓; SSR (prerendered + live izole 3100) HTTP 200, AgentBrief
    görünür, expert `<details>` collapsed, grup başlıkları (Karar/Risk/Uzman) görünür,
    PAPER_ONLY + NO_EXECUTION + HeroScene canvas korundu, "karar etkisi" client
    bundle'da. Backend dosyası değişmedi; backend testleri çalıştırılmadı (gerekmez).
  - Commit: `feat(web): polish live dashboard readability`.

- **UX3 — Dashboard Information Architecture tamamlandı** (2026-06-13): dashboard
  önem sırasına göre **gruplu IA**'ya geçti. **Frontend-only**; backend FREEZE
  korundu (packages/ + apps/* SIFIR diff; openapi/TS değişmedi → codegen drift
  otomatik yeşil). Frontend hesap yapmaz; selector/brief korundu.
  - Simple 5 önem-sıralı bölüm: Agent Command Center (AgentBrief hero + Karar
    Merkezi + AI Analist) → Risk & Yürütme Donması (KILL_SWITCH/HALT matristen
    ÖNCE) → Karar İzi/Aday Matrisi → İzlenecek Koşullar → Agent'a Sor. Expert
    (collapsed) 5 grup: Data Quality & Providers · Market Structure · Macro/Catalyst ·
    Paper & Learning · Ops/System. Ortak `PanelGroup` helper; page.tsx şişmedi.
  - `panel-registry.ts` yeni `PanelGroupId` + her panel doğru gruba. Replay/
    Provider/MarketData/Snapshot/Learning ana ekrandan expert'e; Macro'da Catalyst
    önce, ham haber geri planda. LearningPanel yetersiz örnekte tek satır.
  - tsc temiz; next build ✓; SSR (prerendered + live izole 3061) HTTP 200,
    AgentBrief görünür, expert `<details>` collapsed, 5 grup başlığı görünür,
    PAPER_ONLY + HeroScene canvas korundu. Backend testleri çalıştırılmadı (gerekmez).
  - Commit: `feat(web): reorganize dashboard information architecture`.

- **REL1 — Release Packaging / Local Production Runbook tamamlandı** (2026-06-13):
  tek komutla, arka planda, tekrar edilebilir local production. **Devops/scripts/
  docs**; backend FREEZE korundu (packages/ + apps/* runtime kodu SIFIR diff;
  scriptler yalnızca mevcut süreçleri başlatır). PAPER_SAFE/NO_EXECUTION; canlı
  paper_safe=true doğrulandı.
  - Yeni `scripts/_prod_common.sh` + `prod_up.sh` / `prod_down.sh` /
    `prod_status.sh` (+ Makefile `prod-up`/`prod-down`/`prod-status`/`prod-smoke`).
    prod_up API+web (next start, prod build)+tick daemon'ı background başlatır
    (pid `data/runtime/run/`, log `data/runtime/logs/`) + learning one-shot seed.
    Port-conflict → açık hata + **eski E_YAY CODEX LaunchAgent tespiti**
    (`com.eyay.backend → *:8000`) + bootout ipucu. learning restart-always DEĞİL.
  - README "Local production runbook (REL1)" bölümü (first run/start/stop/status/
    smoke/common failures/port conflict/SSL certifi/stale/cleanup). smoke.sh aynı.
  - Validation: bash -n 7/7 ✓; canlı prod lifecycle (izole 8060/3060, TEST_USE_MOCK):
    prod_up→status→smoke(8/8)→down temiz; tsc temiz; next build ✓; pytest 419/419.
  - Commit: `chore(release): add local production runbook`.

- **UX2 — Dashboard Polish / Usability Pass tamamlandı** (2026-06-13): Agent
  Operating Cockpit okunabilirlik cilası. **Frontend-only**; backend FREEZE
  korundu (packages/ + apps/api + worker SIFIR diff; openapi/TS değişmedi → codegen
  drift otomatik yeşil). RiskGate/DQS/KillSwitch/halt/paper/learning/replay
  dokunulmadı; PAPER_ONLY/NO_EXECUTION rozetleri korundu.
  - Uzman bölümü 6 okunur başlığa gruplandı (Karar & Analiz / Risk / Piyasa Yapısı /
    Veri / Öğrenme / Ops) — `app/page.tsx` + yeni `ExpertGroup` helper; simple
    layout + collapsed `<details>` aynı.
  - Vague copy fix: AIReportPanel "DQS BLOCKED **veya** risk gate" → tek
    `main_blocker` (useCockpitBrief). AgentBrief "Önerilen duruş" callout. Chat
    başlık "Agent'a Sor" + "BTC 1h neden hold?" önerisi. TimeframeMatrix tablo
    overflow-x-auto (responsive).
  - tsc temiz · next build ✓ (`/` 334 kB static) · canlı SSR smoke (izole API 8050 +
    web 3050, TEST_USE_MOCK): smoke.sh 8/8 PASS; SSR'da Agent Brief + HeroScene canvas +
    PAPER_ONLY + gruplu başlıklar; `<details>` open YOK; eski "veya" copy kaldırıldı.
    Backend testleri çalıştırılmadı (gerekmez — backend sıfır diff).
  - Commit: `feat(web): polish agent cockpit usability`.

- **DEP1 — Deployment / DevOps Checklist tamamlandı** (2026-06-13): backend RC
  gerçek 7/24 local/production-like çalıştırmaya hazır. Yalnızca **docs/devops**;
  packages/ + apps/ runtime kodu **SIFIR diff** (backend FREEZE korundu).
  - **`.env.example`** doğru + tam yeniden yazıldı: phantom var fix
    (`GROQ_DAILY_BUDGET_TOKENS`→`LLM_DAILY_TOKEN_BUDGET`; `ANTHROPIC_API_KEY`/
    `API_HOST`/`API_PORT`/`*_CACHE_TTL_SEC` kod okumuyor → kaldırıldı); eklendi
    `LLM_MODE`/`PRICE_USE_MOCK`/`DEV_CORS`/`TICK_INTERVAL_SEC`/`SSL_CERT_FILE` +
    tüm runtime `*_PATH`. `.env` otomatik yüklenmez (doc); PAPER_ONLY/NO_EXECUTION
    yapısal.
  - **`scripts/smoke.sh`** (+`make smoke`): health/system-health/cockpit/snapshot/
    decision-matrix/replay-status/learning-summary + web SSR; fail→exit 1.
    **`scripts/workers.sh`** (+`make workers`): tick daemon + learning one-shot.
  - **README**: stale "v2.5-web" → Backend RC; script tabanlı smoke; yeni
    "Deployment / 7-24 readiness" (süreç tablosu: api/tick restart-always,
    learning **zamanlayıcı** — restart-always değil = spin-loop; supervision
    launchd/systemd/pm2/compose; health check + stale alert + logs + volume) +
    açık PAPER_SAFE deploy checklist.
  - Validation: pytest **419/419** (regresyon yok), ruff/tsc/build temiz, scripts
    syntax ✓. Canlı smoke (izole API 8050 + web 3050, TEST_USE_MOCK): smoke.sh
    **8/8 PASS** (paper_safe=true + web SSR 200); learning one-shot exit 0; tick
    daemon cycle OK + SIGTERM temiz. PAPER_SAFE/NO_EXECUTION; kod sıfır diff.
  - Commit: `chore(devops): add deployment readiness checklist`.

- **A1 — Final Backend Architecture Audit tamamlandı → BACKEND RELEASE CANDIDATE**
  (2026-06-13): backend uçtan uca "bitirme kontrolü"nden **PASS** ile geçti.
  Gerçek **P0 bug yok**, gerçek sözleşme/runtime/TS drift yok, kritik test boşluğu
  yok. **Sıfır runtime diff** (kod değiştirilmedi; görev kuralı: P0 yoksa kod yazma,
  docs + RC işaretle). PAPER_SAFE / NO_EXECUTION her katmanda doğrulandı.
  - **Module boundaries temiz**: packages→apps / provider→decision-risk-paper /
    risk→decision importu yok; wildcard yok; service logic api router import
    etmiyor. LLM katmanı decision/paper state'i yalnızca OKUR (mutasyon yok;
    `.record()` yalnızca token budget).
  - **Decision/Risk order doğru**: RiskGate hard gate'leri ÖNCE; sonraki gate'ler
    yalnızca kısıtlayıcı (size küçültür ≤1.0 / block; asla artırmaz); 1w paper
    açmaz; candidate↔final ayrımı korunuyor. `risk/engine.py` max-priority havuzu →
    bypass yapısal imkânsız; DQS<55 → KILL_SWITCH veto.
  - **PAPER_SAFE doğrulandı**: broker/order/execute/ccxt yürütme tokeni hiçbir yerde
    yok (tek "broker" = llm injection guard blocklist). Paper fiyatsız fake kapanış
    yok; backtest look-ahead/refetch/emir yok; weights yalnızca owner approve ile;
    runtime mock yok (`get_quote` → DATA_UNAVAILABLE).
  - **Validation**: pytest **419/419**, ruff CI-scope temiz, tsc temiz, next build ✓.
    In-process smoke (offline): 10 kritik GET 200; /system/health paper_safe=true;
    /replay empty + backtest insufficient_snapshots (dürüst); POST /chat bypass
    probe → guard refusal.
  - **P1 hardening (opsiyonel, freeze sonrası)**: H1 5 düşük-churn store atomik
    değil (risk/halt, rebalance, calibration, llm budget/cache — güvenlik açığı
    değil, corrupt→güvenli default); H2 schema_version dağınık; H3 ARCHITECTURE.md
    çok-agent yapısı aspirasyonel (kod bilinçli consensus+llm sade); H4 codegen
    drift tek yönlü/gevşek; H5 `decide_all` test-only.
  - Commit: `docs(backend): mark backend release candidate after final audit`.

- **O1 — 7/24 Worker Reliability tamamlandı** (2026-06-13): Clean E-yAy artık
  gözlemlenebilir 7/24 agent servisi — worker heartbeat + stale tespiti + crash
  raporlama + system health. Yeni data source / dashboard redesign / intelligence
  / trading logic YOK; RiskGate/DQS/KillSwitch/halt sıfır diff. PAPER_SAFE/
  NO_EXECUTION; worker reliability trade iznini artırmaz.
  - **Heartbeat store** (yeni `packages/ops/heartbeat.py`): file-backed
    `worker_heartbeats.json` (atomik, corrupt/missing→default). cycle_count
    terminal'de artar; last_success_at OK/DEGRADED/NO_DATA'da güncellenir,
    FAILED/RUNNING'de korunur.
  - **System health VM** (yeni `packages/ops/system_health.py`): network-free —
    STALE/UNKNOWN türetilir (TICK_STALE_SEC=120 / LEARNING_STALE_SEC=3600),
    provider_summary / dqs_status / snapshot_store_status / risk_halt_status +
    owner warning'leri (rapor; execution alert değil).
  - **Endpoint** (yeni `apps/api/routers/system.py`): `GET /api/v1/system/health`;
    `/health` korundu.
  - **tick_worker**: her cycle RUNNING→OK/DEGRADED; istisnada FAILED (loop ölmez).
    **learning_worker**: L1 run metadata heartbeat'e bağlandı (NO_DATA = alive).
  - **Sözleşme/frontend** additive: openapi SystemHealth+WorkerHealth+/system/health;
    TS api.ts + useSystemHealth; SystemHealthBar worker/stale/last-tick/snapshot/
    warning + NO_EXECUTION. codegen drift + contract yeşil.
  - **419 pytest** (+11 +1 contract param), ruff CI-scope + tsc + pnpm build yeşil.
    Live smoke (izole API 8023 + web 3102): system/health tick DEGRADED fresh +
    learning NO_DATA, provider 8ok/3deg, snapshot 1, halt yok, warnings
    provider_degraded+learning_worker_no_data; web SSR 200 "Sistem Sağlığı".

- **L1 — Learning Loop Finalization tamamlandı** (2026-06-13): learning loop
  kapalı paper trade outcome'larından **doğru, timeframe-aware, gate-aware ve
  owner-approval-safe** öğreniyor. Yeni veri kaynağı / dashboard redesign /
  trading logic YOK; RiskGate/DQS/KillSwitch/halt sıfır diff. PAPER_SAFE/
  NO_EXECUTION; active weights owner approval olmadan değişmez.
  - **BUG FIX**: `auto_weight_trainer._parse_dominant_module` artık
    `fingerprint.dominant_module` (v2→parts[7], legacy→parts[5], malformed→None).
    Eski kod hep parts[5] → v2'de score_bucket'ı module sanıyordu. Canlı
    doğrulandı: by_dominant_module=touche (S55 değil).
  - **Canonical outcome** (yeni `packages/learning/outcomes.py`): `CanonicalOutcome`
    (trade_id…paper_only) + `build_outcome` (legacy default, crash yok) +
    timeframe-aware `breakdowns`/`bucketize`/`distribution`.
  - **Timeframe-aware summary** (`summary.py` additive): outcomes_total/
    verified_outcomes/by_timeframe/by_symbol/by_regime/by_dominant_module/
    by_close_reason/worker_last_run/proposal_status. Global metrikler korundu;
    **15m outcome 1d bucket'ını etkilemez**.
  - **Worker metadata** (yeni `run_store.py` + `learning_worker/main.py`):
    run_id/started_at/completed_at/status/skipped_reason/outcomes_seen/
    proposals_generated/calibration_status/errors. Boş veri → NO_DATA; hata →
    COMPLETED_WITH_ERRORS (worker patlamaz).
  - **Trainer** verified canonical outcome timeframe/regime/module dağılımını
    proposal evidence'ına yazıyor; min sample guard + owner approval korundu.
    **Mistake memory** full-fingerprint (timeframe içerir) korundu; **calibration**
    aktif davranışı değişmedi.
  - **Sözleşme/frontend** additive: openapi LearningSummary L1 alanları; TS api.ts
    (+OutcomeBucket/LearningWorkerRun); LearningPanel timeframe ayrımı + worker
    last run + proposal status. codegen drift + contract yeşil.
  - **407 pytest** (+14), ruff CI-scope + tsc + pnpm build yeşil. Live smoke
    (izole API 8021 + web 3101): health/learning-summary/rebalance-proposal/
    cockpit-brief 200; by_timeframe 15m≠1d; module=touche; active_version 1.0.0
    (owner gate); web SSR 200 "Öğrenme" + PAPER_ONLY.

- **P1 — Paper Lifecycle Finalization tamamlandı** (2026-06-13): paper trading
  yaşam döngüsü backend'de net, güvenli, **audit edilebilir** ve öğrenmeye hazır.
  PAPER_SAFE / NO_EXECUTION sıfır diff; fiyat yoksa **fake kapanış yok**;
  RiskGate/DQS/KillSwitch/halt bypass yok.
  - **Lifecycle state machine** (`packages/paper/`): Position `lifecycle_status`
    OPEN → EXPIRED_PENDING_PRICE / EXIT_PENDING / ERROR_STATE → terminal Trade
    (CLOSED / FORCE_CLOSED). `time_stop_expired`, `pending_exit_reason` additive.
    Time-stop: fiyat varsa TIME_STOP_EXIT, yoksa EXPIRED_PENDING_PRICE (sonraki
    tick'te fiyat gelince kapanır; negatif geri sayım yok).
  - **Tek açılış yolu** `lifecycle.attempt_open` (tick_worker + paper router ortak,
    drift yok): duplicate/scale-in politikası — aynı (symbol, timeframe) yön fark
    etmeksizin bloklanır (no hedge/flip); farklı TF serbest; `scale_in=True`
    explicit'te açılır.
  - **Audit trail** (yeni `packages/paper/audit.py`, append-only
    `data/runtime/paper_audit.jsonl`): OPEN_ATTEMPT/OPENED/OPEN_BLOCKED/
    TIME_STOP_EXPIRED/EXIT_PENDING/CLOSED/KILL_SWITCH_EXIT/STATE_REPAIRED;
    best-effort (lifecycle'ı patlatmaz), bozuk satır okumada atlanır.
  - **State robustness** (`packages/paper/state.py`): `schema_version`, atomik
    yazım (temp+os.replace), corrupt → yedek + temiz default (crash yok),
    legacy/forward-uyumlu yükleme (bilinmeyen alan atlanır, eksik default'a düşer).
  - **Learning handoff**: Trade'e `open_reason`/`snapshot_id`/`lifecycle_status`
    additive (mevcut learning okuyucuları bozulmadı).
  - **API additive**: `/paper-trading/state` → `new_entries_disabled`,
    `duplicate_warning`, `audit_summary`, `recent_audit_events`; Position/Trade
    lifecycle alanları. openapi + TS api.ts senkron (codegen drift yeşil).
    PaperActionPanel: EXPIRED/EXIT_PENDING "fiyat bekleniyor" + duplicate uyarısı.
  - **393 pytest** (+18), ruff CI-scope + tsc + pnpm build yeşil, live smoke
    (health/tick/paper-state/dashboard/cockpit + web SSR 200) OK.

- **R2 — Deterministic Rolling Backtest Runner tamamlandı** (2026-06-13): kayıtlı
  snapshot serisi (`packages/data/snapshot_store.py`) üzerinde **deterministik**
  outcome ölçümü. Live provider refetch YOK, sahte geçmiş YOK, look-ahead YOK
  (outcome yalnızca GERÇEK gelecek snapshot'larla; karar zamanından sonraki İLK
  gözlemle ölçülür). PAPER_SAFE / NO_EXECUTION: backtest emir üretmez, paper
  açmaz, RiskGate bypass etmez, decide_matrix'i yeniden çalıştırmaz.
  - **Runner** (`packages/data/backtest.py`, saf fonksiyon): 15m/1h/4h/1d horizon;
    metrikler `hit_rate / false_positive / false_negative / avg_return /
    max_drawdown / blocked_decision_accuracy`, `per_timeframe / per_symbol /
    per_horizon`; bloklanmış aday-açılışlar counterfactual (blok doğru muydu?).
    Yetersiz örnekte oran null (uydurma 0 değil). `snapshot_store.all_docs()`
    kronolojik okuma helper'ı eklendi.
  - **Endpoint**: `GET /api/v1/replay/backtest` + `GET /api/v1/replay/backtest/{run_id}`
    (literal route, `{snapshot_id}` catch-all'undan ÖNCE). Dürüst durum: boş store
    → `insufficient_snapshots`, ölçülebilir gelecek yok → `insufficient_future_data`
    (ikisi de 200). `run_id` store üzerinde deterministik; sahte geçmiş run
    saklanmaz (eşleşmezse 404 + current_run_id).
  - **Sözleşme additive**: openapi `/replay/backtest(/{run_id})` +
    `ReplayBacktest`/`ReplayBacktestMetrics`; TS api.ts senkron (codegen drift
    yeşil). **375 pytest**, ruff CI-scope + tsc + pnpm build yeşil, live smoke
    (`/replay/status`, `/replay/backtest`, `/dashboard/state`) OK.

- **UX1 — Agent Operating Cockpit tamamlandı** (2026-06-13): dashboard "veri
  çöplüğü"nden operating cockpit'e çevrildi — ilk ekranda agent'ın beyni okunur
  (işlem açabilir mi, açamıyorsa **tek** ana sebep ne, ne yapmak istedi, neden
  değişti, ne izliyor). Yeni trading feature / data provider / intelligence
  module YOK; RiskGate/DQS/KillSwitch/halt SIFIR diff. Frontend hesap yapmaz —
  tüm türetilmiş alanlar backend ViewModel'inden. PAPER_SAFE / NO_EXECUTION.
  - **Backend ViewModel** (`packages/decision/cockpit.py`, saf fonksiyonlar):
    `compute_main_blocker` TEK ana engel ("veya" YOK; öncelik DQS_BLOCKED/
    PROVIDER_DOWN > HALT/kill-switch > RISK_GATE > NONE), `compute_data_mode`
    (LIVE_VERIFIED/LIVE_DEGRADED/PARTIAL_FALLBACK/SIMULATION/BLOCKED),
    `compute_status` (ACTIONABLE/NO_ACTION/WATCHING/FROZEN/BLOCKED),
    `agent_brief_view` (status/can_act/main_blocker/summary/data_mode/dqs/risk/
    top_blockers/top_candidates/next_watch_conditions/recommended_stance/
    paper_state_summary), `decision_trace_view` (candidate→final/blocked_by/
    restrictive_gates/paper_action/evidence_refs), `next_watch_conditions`.
  - **Endpoint**: `GET /api/v1/cockpit/brief` → {agent_brief, decision_trace}
    (decide_matrix+matrix_view'i diğerleriyle aynı okur, yalnızca ÖZET üretir).
  - **Tek ana engel**: report.py no_actionable/change_mind + DecisionPanel artık
    tek main_blocker yazar ("DQS BLOCKED veya risk gate kısıtlayıcı" silindi).
  - **Paper time-stop**: paper_trading `_time_stop_status` (NONE/ACTIVE/EXPIRED +
    remaining ≥0) — additive serileştirme, negatif geri sayım YOK (logic değişmedi).
  - **Learning**: summary `min_sample=20`/`sample_sufficient` → INSUFFICIENT SAMPLE.
  - **Sözleşme additive**: openapi /cockpit/brief + CockpitBrief/AgentBrief/
    DecisionTrace/MainBlocker/WatchCondition + enum'lar; Position time_stop_*;
    LearningSummary min_sample/sample_sufficient. TS api.ts senkron (drift yeşil).
  - **Frontend**: lib/selectors/cockpit.ts + useCockpitBrief. Yeni paneller
    AgentBriefPanel (üstte tek ana kart, HeroScene üzerinde) / DecisionTracePanel /
    WatchConditionsPanel / PaperActionPanel; Ask the Agent = ChatPanel. page.tsx
    Simple grid + "Uzman / Detaylar" `<details>` collapsed; registry tier
    simple|expert. TimeframeMatrix global-suspended tek banner + sade hücre;
    AgentVotes → evidence chain; CommandSignals → "Aday Sinyalleri" +
    NOT_ACTIONABLE; Replay → Uzman/Detaylar.
  - **366/366 pytest** (+16 cockpit), CI-scope ruff + tsc + pnpm build yeşil.
    **Live smoke** (izole API 8011 gerçek veri + web SSR 3100 prod build):
    cockpit/brief WATCHING/RiskGate tek engel (no "veya"); ai-report no_actionable
    tek engel; learning INSUFFICIENT SAMPLE; matrix 20/20 suspended; SSR 200
    "Agent Brief" üstte + HeroScene + PAPER_ONLY + Uzman/Detaylar + 36 panel.
    RiskGate/DQS/KillSwitch/halt sıfır diff, bypass yok.
  - Açık (NEXT): R2 deterministic rolling replay/backtest runner VEYA cockpit
    cilası (panel drag-drop düzeni, görünürlük tercih kalıcılığı).

- **R1 — Real Snapshot Replay / Backtest Foundation tamamlandı** (2026-06-13):
  replay artık `reserved_not_active` değil — gerçek **disk snapshot store**
  üzerinden çalışan minimal, dürüst replay foundation. Sahte backtest / uydurma
  geçmiş performans YOK. PAPER_SAFE / NO_EXECUTION: replay emir üretmez, paper
  pozisyon açmaz, RiskGate'i bypass etmez, LLM'e bağlanmaz, live provider çağırmaz.
  - **Store** (`packages/data/snapshot_store.py` — ARCHITECTURE §3'te zaten tanımlı
    olan dosya; yeni katman değil): atomik write (temp + `os.replace`), bozuk dosya
    → crash yok (okunurken atlanır), `latest()`/`get(id)`/`status()`/`count()`,
    zaman-sıralı dosya adı (`<ts>__<safe_id>.json`), ring-buffer prune
    (`SNAPSHOT_STORE_MAX`, default 500), aynı id en güncelse duplicate yazmaz.
    Path: `data/runtime/snapshots/` (env `SNAPSHOT_STORE_PATH`; testte temp dir).
    Kayıt alanları: schema_version, snapshot_id, generated_at, mode (provenance),
    dqs, provider_status, data_snapshot (compact prices+warnings), decision_matrix
    (matrix_view tam çıktısı — risk_gate + cells + options/vol/türev/catalyst/
    event_risk özetleri), risk_state, paper_state_summary.
  - **Producer**: `apps/tick_worker/main.py::run_once()` her tick'te matrix_view'i
    store'a kaydeder (store yazımı ASLA tick'i patlatmaz — try/except + log).
  - **Endpoint'ler** (`apps/api/routers/replay.py`, live refetch YOK):
    `GET /replay/status` → active/empty + mode (active_snapshot_replay /
    insufficient_snapshots / reserved_not_active) + snapshot_count + latest id/zaman;
    `GET /replay/{id}` → kayıtlı snapshot zarfı (yoksa 404 not_found);
    `GET /replay/{id}/decision-trace` → kayıtlı decision_matrix'ten karar izi
    (snapshot_id/generated_at/mode/DQS/RiskGate/top candidates/final decisions/
    blocked_by/paper actions/provider issues/catalyst+options+vol+türev özetleri).
    Hepsi yalnızca store'dan okur; yeni karar HESAPLAMAZ.
  - **Sözleşme** (additive + drift-safe): openapi `ReplayStatus` güncellendi +
    yeni `ReplaySnapshot` / `ReplayDecisionTrace` + `/replay/{id}/decision-trace`
    path; `ReplaySnapshotStatus` kaldırıldı. TS api.ts senkron (`ReplayStoreStatus`/
    `ReplayMode`/`ReplayExecution` enum literalleri + tipler). Codegen drift + contract
    testleri yeşil (eski reserved testi → 404 not_found testine güncellendi).
  - **Frontend**: ReplayStatusPanel artık store status + mode rozeti +
    snapshot_count + latest id/zaman + "NO LIVE EXECUTION" rozeti + "Replay does
    not execute trades" notu gösterir. Selector `lib/selectors/replay.ts`; page.tsx
    büyümedi (mevcut GridCell).
  - **349/349 pytest** (+15: store atomik/latest/by-id/missing/corrupted/dedup/
    prune/status, endpoint empty+active, found+404, decision-trace stored-matrix,
    "replay live refetch yapmaz" (pipeline boom guard), tick_worker producer
    offline; +2 contract 404 testi). CI-scope ruff + tsc + pnpm build yeşil.
    **Live smoke** (izole API 8011, gerçek veri + bir gerçek snapshot seed'lendi):
    /health /data/snapshot /decision/matrix /dashboard/state 200; /replay/status
    active (count=1, active_snapshot_replay); /replay/{id} 200 (decision_matrix
    dahil); /replay/{id}/decision-trace 200 (regime NEUTRAL, risk_gate
    NO_POSITION_INCREASE, 8 top candidate, 20 final, deep_data 5 anahtar); missing →
    404. Web SSR (izole 3100) 200 / 32 panel + replay_status paneli + HeroScene +
    PAPER_ONLY. İzole server'lar kapatıldı; data/runtime gitignore'lu (snapshot
    diske yazıldı ama commit'lenmez). RiskGate/DQS/KillSwitch/halt sıfır diff.
  - Açık (NEXT): UX1 Agent Operating Cockpit veya R2 deterministic rolling
    replay/backtest runner (replay foundation gerçek çalışıyor — yeni veri kaynağı
    gerekmez).

- **v2.6.1 — LLM Persona deep-data derinleşme tamamlandı** (2026-06-13): v2.6
  persona/chat/AI-report katmanı, v2.6'dan SONRA eklenen v2.7 deep-data
  dimensiyonlarına (D2 türev / D3 options / D4 volatilite / D5 catalyst
  half-life + event riski + rotation) **state-grounded** olarak bağlandı.
  LLM hâlâ karar VERMEZ — yalnızca açıklar; karar zinciri sıfır diff.
  - **Kök neden**: `matrix_view` bu özetleri zaten üretiyordu ama LLM kompakt
    bağlamı (`packages/agent/llm/context.py`) bunları DROP ediyordu → persona/chat
    options/vol/türev/catalyst/rotation göremiyordu.
  - **context.py**: `_deep_data_summary(view, snap)` → kompakt `deep_data` bloğu
    (options regime/ATM IV/IV-RV/skew+proxy, volatilite regime/state/z-skor, türev
    squeeze/funding+proxy, catalyst event_type/actionability/half-life, event_risk
    level/restrictive, rotation status/score/direction/evidence). Digest stabil
    (cache güvenli — hours_until gibi volatil alan girmez).
  - **report.py**: Risk Officer kanıt+itirazları options stresi / volatilite
    rejimi / türev squeeze / catalyst kapılarını içerir; Macro Strategist rotation
    + volatilite + options stresini senaryoya katar. `evidence_used` HÂLÂ koddan
    (LLM uyduramaz); deep-data yoksa boş (uydurma yok). Persona briefleri deep-data'ya
    atıf yapar (LLM yolu da görür).
  - **chat.py**: yeni intent handler'ları — "Options risk ne diyor?", "Volatility
    neden kısıtladı?", "Funding/türev ne diyor?", "Rotasyon ne durumda?", "Catalyst
    etkisi var mı?". RiskGate/why fallback'inden ÖNCE çalışır; "RiskGate neyi
    engelledi?" hâlâ risk_gate handler'ına gider (yanlış yönlenme testli). Veri
    yoksa "kısıt üretmiyor" der, uydurmaz. Injection/bypass guard değişmedi.
  - **Frontend** (additive, şema değişmedi): AIReportPanel persona `evidence_used`
    satırı + "Açıklayıcı katman · yürütme yetkisi yok — final karar deterministik
    engine + RiskGate" rozeti; ChatPanel'e options/volatility/türev öneri soruları.
    Persona/chat response şekli değişmedi → openapi/TS sıfır diff → codegen drift
    otomatik yeşil.
  - **334/334 pytest** (+11: deep-data summary filtresi, persona fallback grounding,
    boş-state'te kanıt uydurmama, 5 chat intent, risk_gate yanlış-yönlenme yok,
    endpoint state-grounded; testlerde live network yok), CI-scope ruff + tsc +
    pnpm build yeşil. **Live smoke** (izole API 8011, gerçek Deribit): risk_officer
    `options:ETHUSD PUT_SKEW_STRESS` + `volatility` + `catalyst`; macro
    `rotation:bearish 39.0`; chat 5 deep-data intent gerçek değerlerle grounded
    (BTC ATM IV 0.41 CHEAP_VOL, proxy uyarısı); bypass → guard refusal. Web SSR
    (izole 3100) 200 / 32 panel + HeroScene + PAPER_ONLY. PAPER_SAFE/NO_EXECUTION;
    RiskGate/DQS/KillSwitch/halt sıfır diff, bypass yok.
  - Açık (NEXT): gerçek replay/backtest motoru (disk snapshot store) ve/veya kalan
    deep-data slice / asset-universe genişletme.

- **v2.7 D3 — Options IV / Skew / Term Structure Intelligence tamamlandı**
  (2026-06-13): BTC/ETH options implied volatility, 25Δ skew (proxy), term
  structure ve realized-vs-implied spread karar zincirine **yalnızca kısıtlayıcı**
  eklendi. Yeni provider `packages/data/providers/options/` (saf-python engine +
  Deribit public adapter + offline fixtures + orchestrator). Live Deribit
  `get_book_summary_by_currency` → ATM IV / OTM call-put IV / OI / underlying;
  instrument_name parse (strike/expiry/call-put). Live fail → DEGRADED, chain boş
  → UNAVAILABLE (runtime mock YOK; fixture verified=false, karar dışı).
  - **Engine** (`options/engine.py`): ATM IV (ön vade, en yakın strike), 25Δ skew
    **proxy** (`is_proxy=True`; moneyness tabanlı OTM call IV − OTM put IV; gerçek
    greeks DEĞİL), put/call OI oranı, term structure (front/next/long ATM IV +
    slope), IV-RV spread (D4 realized vol 1d ile). Rejim: NORMAL / RICH_VOL /
    CHEAP_VOL / PUT_SKEW_STRESS / CALL_SKEW_EUPHORIA / TERM_STRESS. DQS = tazelik ×
    bileşen tamlığı.
  - **Gate** (`packages/risk/options_risk.py`): yalnızca verified+OK + BTC/ETH.
    PUT_SKEW_STRESS/CALL_SKEW_EUPHORIA + long aday → CAUTION ×0.5 (short/contrarian
    yalnızca WATCH bağlam); TERM_STRESS → NO_POSITION_INCREASE (block); RICH_VOL →
    CAUTION; CHEAP_VOL → WATCH (yalnızca bağlam, **boost YOK**). size_factor ≤ 1.0.
    Timeframe ağırlıklı: options 4h/1d/1w bağlamı (tam etki); 15m/1h düşük (0.25/
    0.4) → block CAUTION'a yumuşar. RiskGate hard gate'inden SONRA, yalnızca açılış
    adayına.
  - **Entegrasyon**: pipeline `MarketSnapshot.options` (Deribit chain + D4 realized
    vol; ekstra ağ yalnızca Deribit); decision engine options gate (catalyst'ten
    sonra) + `options_report` + blocked_by `options_risk:*`; matrix `options`
    özeti (rejim ≠ NORMAL); `/data/snapshot` options alanı.
  - **Sözleşme** additive: openapi `OptionsSnapshot` / `OptionsSummary` +
    `OptionsRegime` / `OptionsStatus` enum + DataSnapshot.options +
    DecisionMatrix.options. TS api.ts senkron (codegen drift yeşil).
  - **Frontend**: `OptionsVolPanel` (selector `selectOptions` + registry, page.tsx
    tek GridCell) — symbol / ATM IV / realized karşılaştırma / IV-RV / 25Δ skew
    (proxy rozeti) / put-call OI / term structure / rejim / source / freshness /
    status / karar etkisi. TimeframeMatrixPanel options banner + hücre "OPTIONS"
    rozeti. VolatilityPanel/DerivativesPanel/CatalystPanel bozulmadı.
  - **323/323 pytest** (+36 D3; live network yok), CI-scope ruff + tsc + pnpm
    build yeşil. Live smoke OK (gerçek Deribit: BTC ATM IV ~41% CHEAP_VOL, ETH
    ~23% PUT_SKEW_STRESS, verified=true, FRESH; matrix options banner; RiskGate
    suspended/DQS BLOCKED iken options hücreyi bypass etmiyor). Eski E_YAY CODEX
    `com.eyay.backend` launch agent'ı `*:8000`'de duruyor — Clean E-yAy API
    `127.0.0.1:8000`'de ayrı kalkıyor (127.0.0.1 istekleri Clean'e gider).
    PAPER_SAFE/NO_EXECUTION; RiskGate/DQS/KillSwitch/halt sıfır diff, bypass yok.
  - Açık (NEXT): gerçek replay/backtest motoru ve/veya v2.6 LLM persona derinleşme.

- **v2.7 D5 — Real News Feed + Catalyst Half-Life Intelligence tamamlandı**
  (2026-06-12): mevcut RSS haber feed'i gerçek catalyst zekâ katmanına çevrildi.
  Her başlık kural tabanlı (deterministik, **LLM YOK**, network YOK) bir
  `event_type`'a sınıflandırılır ve event_type'a göre asset × timeframe etki
  haritası + yarı-ömür + `valid_until` + actionability üretir.
  - **Sınıflandırma + motor** (`packages/data/providers/news/catalyst.py`):
    13 event_type (geopolitical de/escalation, inflation_data, jobs_data,
    central_bank, oil_supply/inventory, crypto_etf_flow, funding_oi_squeeze,
    earnings, exchange_outage, rumor_unverified, unknown). Sıralı kural seti;
    rumor → `verified=False` (trade'e dönüşmez). `build_impact` → CatalystImpact
    (affected_assets = event default ∪ başlıktan tespit; surprise_level işaretli;
    valid_until = ts + half_life×3; confidence = verified+freshness+relevance).
  - **Gate** (`packages/risk/catalyst_risk.py`): yalnızca `verified` + yarı-ömrü
    dolmamış + symbol/TF eşleşen impact'ler. CONTEXT_ONLY→NONE, WATCH→bağlam,
    CAUTION→×0.5, NO_POSITION_INCREASE→block. Yön bağımsız; size_factor ≤ 1.0.
    RiskGate hard gate'lerinden SONRA, yalnızca açılış adayına.
  - **Entegrasyon**: pipeline `MarketSnapshot.catalyst_impacts` (başlıklardan,
    ekstra ağ yok); decision engine catalyst gate (volatility'den sonra) +
    `catalyst_report` + blocked_by `catalyst_risk:*`; matrix `catalysts` özeti;
    `/data/snapshot` catalyst_impacts alanı.
  - **Sözleşme** additive: openapi `CatalystImpact` genişletildi (headline_id /
    actionability / verified / evidence / …) + `CatalystEventType` /
    `CatalystActionability` enum + `CatalystSummary` + DataSnapshot.catalyst_impacts
    + DecisionMatrix.catalysts. TS api.ts senkron (codegen drift yeşil).
  - **Frontend**: `CatalystImpactPanel` (selector `lib/selectors/catalyst.ts` +
    registry, page.tsx tek GridCell) — event_type / affected assets+TF / yarı-ömür
    countdown / valid_until / actionability / evidence / rumor rozeti. NewsPanel
    (unscheduled news) + EventCalendarPanel (scheduled) ayrı kalır.
    TimeframeMatrixPanel catalyst banner + hücre "CATALYST" rozeti.
  - **287/287 pytest** (+21 D5; live network yok), CI-scope ruff + tsc + pnpm
    build yeşil. Live smoke OK (gerçek RSS → central_bank/geopolitical/
    funding_squeeze/etf_flow/rumor sınıfları; rumor verified=false; matrix
    catalyst banner; RiskGate suspended iken catalyst hücreyi bypass etmiyor).
    PAPER_SAFE/NO_EXECUTION; RiskGate/DQS/KillSwitch/halt sıfır diff, bypass yok.
  - Açık (NEXT): D3 (options IV/skew Deribit) ve/veya gerçek replay/backtest motoru.

- **v2.7 D4 — Realized Volatility / Volatility Regime Intelligence tamamlandı**
  (2026-06-12): realized vol + rejim + squeeze/expansion/shock karar zincirine
  **yalnızca kısıtlayıcı** eklendi. Yeni provider `packages/data/providers/
  volatility/` (saf-python engine + orchestrator; mevcut OHLCV cache'inden, EKSTRA
  AĞ YOK; log-getiri annualize realized vol short/medium/long + z-skoru + rejim
  LOW/NORMAL/ELEVATED/EXTREME + squeeze/expansion/shock; bar yetersiz →
  DEGRADED/`insufficient_bars`; runtime mock yok; fixture barlar verified=false).
  - **Gate** (`packages/risk/volatility_risk.py`): yalnızca verified+OK; EXTREME→
    NO_POSITION_INCREASE, ELEVATED→CAUTION ×0.5, shock→en az CAUTION (rejim
    yüksekse block), LOW/squeeze→WATCH (yalnızca bağlam, boost yok). Yön bağımsız.
    size_factor ≤ 1.0 (asla artırmaz). RiskGate hard gate'inden SONRA, yalnızca
    açılış adayına. Timeframe ağırlıklı (15m/1h tam → shock daha etkili; 1d/1w
    block CAUTION'a yumuşar = rejim bağlamı; 1w off).
  - **Entegrasyon**: pipeline `MarketSnapshot.volatility` (symbol→tf); decision
    engine `volatility_report` + blocked_by `volatility_risk:*`; matrix
    `volatility` özeti; `/data/snapshot` volatility alanı; thresholds `volatility.*`.
  - **Sözleşme** additive: openapi `VolatilitySnapshot`/`VolatilitySummary`/
    `VolatilityRegime`/`VolState` + DataSnapshot/DecisionMatrix.volatility + TS
    api.ts senkron (codegen drift yeşil).
  - **Frontend**: `VolatilityPanel` (selector+registry, page.tsx tek GridCell) +
    TimeframeMatrixPanel vol rejim banner + hücre "VOLATİLİTE" rozeti.
  - **266/266 pytest** (+28 D4; live network yok), CI-scope ruff + tsc + pnpm
    build yeşil. Live smoke OK (gerçek OHLCV → verified vol; BTC 1d EXTREME/
    expansion z=2.53). PAPER_SAFE/NO_EXECUTION; RiskGate/DQS/KillSwitch/halt sıfır
    diff, bypass yok.
  - Açık (NEXT): D3 (options IV/skew Deribit), D5 (gerçek haber feed + T3 catalyst
    half-life) ve/veya gerçek replay/backtest motoru.

- **v2.7 D2 — Crypto Derivatives Intelligence tamamlandı** (2026-06-12): kripto
  türev zekâsı (funding / OI / squeeze proxy) karar zincirine **yalnızca
  kısıtlayıcı** eklendi. Yeni provider `packages/data/providers/derivatives/`
  (Binance public futures + deterministik squeeze proxy engine + fixtures +
  orchestrator; crypto-only BTCUSD/ETHUSD, runtime mock yok, live fail →
  DEGRADED). `squeeze_proxy` is_proxy=true — GERÇEK liquidation API'si değil.
  - **Gate** (`packages/risk/derivatives_risk.py`): yalnızca verified+OK; HIGH→
    NO_POSITION_INCREASE, ELEVATED→CAUTION ×0.5, funding-chase→CAUTION,
    contrarian→NONE. size_factor ≤ 1.0 (asla artırmaz). RiskGate hard gate'inden
    SONRA, yalnızca açılış adayına. Timeframe ağırlıklı (15m/1h tam, 1d softens,
    1w off).
  - **Entegrasyon**: pipeline `MarketSnapshot.derivatives`; decision engine
    `derivatives_report` + blocked_by `derivatives_risk:*`; matrix `derivatives`
    özeti; `/data/snapshot` derivatives alanı; thresholds `derivatives.*`.
  - **Sözleşme** additive: openapi `DerivativesSnapshot`/`DerivativesSummary`/
    `SqueezeLevel`/`FundingBias` + TS api.ts senkron (codegen drift yeşil).
  - **Frontend**: `CryptoDerivativesPanel` (selector+registry, page.tsx
    büyümedi) + TimeframeMatrixPanel türev banner + hücre "TÜREV" rozeti.
  - **238/238 pytest** (+29 D2; live network yok), CI-scope ruff + tsc + pnpm
    build yeşil. Live smoke OK. PAPER_SAFE/NO_EXECUTION; RiskGate/DQS/KillSwitch/
    halt sıfır diff, bypass yok.
  - Açık (NEXT): D2 kalan slice'ları (options IV/skew Deribit, realized vol,
    gerçek haber feed + catalyst half-life) ve/veya gerçek replay/backtest motoru.

- **OPS tamamlandı**: contract/replay testleri + codegen drift güvencesi +
  operasyonel sağlamlaştırma. Yeni trading feature YOK; karar zinciri sıfır diff.
  - **Contract testleri** (`tests/contract/`, eskiden boştu): OpenAPI'deki her
    side-effect'siz GET endpoint'i TestClient ile çağrılıp şemaya doğrulanıyor
    (required + enum + `$ref`/`oneOf` recursive; additive serbest). Path drift
    guard (openapi↔router). **Gerçek drift yakaladı**: `LLMMeta.mode` enum'unda
    bare `off`'u YAML `False`'a çeviriyordu → `"off"` tırnaklandı.
  - **Codegen drift guard**: openapi component şema adları + enum üyeleri
    `apps/web/types/generated/api.ts` ile eşleşiyor mu (el-senkron). **Gerçek
    drift yakaladı**: TS `Trade.close_reason`'da `TIME_STOP_EXIT`/`KILL_SWITCH_EXIT`
    eksikti → eklendi. CI `pytest`'i bu testleri otomatik koşar → drift CI'ı kırar.
  - **Replay foundation (dürüst)**: disk snapshot store yok (in-memory `_CACHE`);
    sahte replay üretmedik. `apps/api/routers/replay.py`: `GET /replay/status` +
    `GET /replay/{snapshot_id}` → `status: reserved_not_active`, `available:false`,
    en son okunabilir snapshot id. `ReplayStatusPanel` bu endpoint'e bağlandı
    ("REZERVE · AKTİF DEĞİL" rozeti, dürüst reason).
  - **OpenAPI ↔ runtime reconciliation (additive)**: API'de olup openapi'de eksik
    path'ler + 16 component schema eklendi (TS ile birebir): /data/snapshot,
    /learning/{calibration,calibration/retrain,mistakes,rebalance/proposal},
    /paper-trading/reset, /replay/*. TS: OHLCVBar + replay tipleri; DataSnapshot.mode
    → gerçek `ProvenanceMode` (7 alan).
  - **Dev reliability**: README'ye eski `com.eyay.backend` LaunchAgent (0.0.0.0:8000)
    port çakışması troubleshooting'i + `launchctl bootout`; smoke listesine
    decision/matrix + replay/status. SSL_CERT_FILE/certifi zaten dokümante.
  - **209/209 pytest** (+18 contract/drift; live network yok), ruff (CI scope +
    tests/contract) + tsc + `pnpm build` yeşil. Canlı smoke: Clean API 127.0.0.1:8000
    tüm endpoint 200 (replay reserved), web SSR 200 / 28 panel.
  - PAPER_SAFE/NO_EXECUTION; RiskGate/DQS/KillSwitch/halt sıfır diff.
  - Açık (NEXT): gerçek replay/backtest motoru (disk snapshot store gerekli) ve/veya
    asset-universe 2. slice + v2.7 deep data.

- **P0 intelligence parity (kalan kapsam) tamamlandı**: asset universe
  (rotation bacakları) + news/geo/calendar birim testleri + event risk →
  RiskGate (yalnızca kısıtlayıcı) + dashboard görünürlüğü.
  - **Asset universe**: `ohlcv/yfinance` map'ine TLT/HYG/LQD eklendi
    (source_registry kind: rotation). Rotation motoru artık 9/9 seriyle
    çalışıyor → TAHVİL sınıfı + GLD/TLT + TLT/SPY savunma + HYG/LQD kredi
    oranları **canlıda aktif** (smoke'ta TAHVİL & TLT/SPY evidence göründü).
    DEFAULT_SYMBOLS değişmedi. (JNK/IWM/SMH/XLF/FXI + CoinGecko dominance +
    FRED spread'leri bilinçli ertelendi — engine rolü yok = ölü veri.)
  - **Event risk** (`packages/risk/event_risk.py`): yaklaşan **doğrulanmış**
    yüksek etkili takvim olayı → WATCH / NO_POSITION_INCREASE. `RiskEngine.
    evaluate(event_candidates=...)` aynı havuzda max-priority → DQS KILL_SWITCH
    / halt event'i **her zaman ezer** (bypass yok), event riski gate gevşetmez
    / size artırmaz. `decide_all`/`decide_matrix` `snap.catalysts`'ten besler;
    `matrix_view`+`regime-report` additive `event_risk` bloğu + per-catalyst
    `event_level`. thresholds: `event_risk.{block:24h, watch:72h, high:[high,
    critical]}`.
  - **Dashboard** (selector+registry, page.tsx büyümedi): EventCalendarPanel
    actionability rozeti + banner; NewsPanel etkilenen-sembol rozetleri /
    "yalnızca bağlam" + freshness; CapitalRotationPanel "gerçek 30g momentum +
    oran" + UNAVAILABLE durumu; TimeframeMatrixPanel event-risk banner + hücre
    blocked_by rozeti. OpenAPI + TS tipleri additive (`EventRiskView`).
  - **191/191 pytest** (36 yeni: 17 event_risk + 19 news_calendar; testlerde
    live network yok), ruff (CI scope) + tsc + `pnpm build` yeşil; canlı smoke
    OK. RiskGate/DQS/KillSwitch/halt yalnızca kısıtlayıcı yönde; PAPER_SAFE
    korunuyor.
  - Açık kalan (NEXT): **OPS** (contract/replay + codegen drift); sonra
    asset-universe ikinci slice (sektör/EM/kredi modülleri) ve v2.7 deep data.

- **P0 intelligence parity (çekirdek) tamamlandı**: gerçek rotation engine +
  news/calendar pipeline entegrasyonu.
  - Hash-mock rotation kaldırıldı. `packages/data/providers/rotation/engine.py`
    Clean 1d OHLCV cache üstünde 30g momentum + çapraz oran (GLD/TLT, BTC/GLD,
    TLT/SPY, HYG/LQD, BTC/DXY, GLD/DXY) + sınıf para-akışı (legacy _FLOW_SIGNALS
    parity) hesaplar (deterministik, pure python). `rotation/__init__.
    get_rotation()` motoru OHLCV'ye bağlar: veri yetersiz → RotationView.status=
    UNAVAILABLE + nötr 50 + provider DEGRADED (mock yok). "SPY" slotu registry'deki
    SP500'e (^GSPC) eşli — hisse bacağı canlıda aktif.
  - Pipeline `provider_status`'a news/geo_news/calendar/rotation eklendi;
    news_unavailable / calendar_unavailable / rotation_unavailable warning'leri.
  - Consensus: rotation UNAVAILABLE → quantum modülü düşer, ağırlık
    `_redistribute` ile dağılır (mock skor karar zincirine giremez).
  - 155/155 pytest (5 yeni rotation testi), ruff (CI scope) + tsc yeşil;
    canlı smoke OK (API 200, rotation gerçek momentum/oran evidence; web SSR
    200). RiskGate/DQS/KillSwitch/halt sıfır diff; PAPER_SAFE korunuyor.
  - Açık kalanlar (NEXT): asset universe expansion (TLT/HYG/LQD/JNK/IWM/SMH/
    XLF/FXI + CoinGecko dominance + FRED HY spread/real yield/M2/PPI);
    news/geo/calendar birim testleri; event risk RiskGate bağı.

- **v2.6 tamamlandı**: LLM persona katmanı (Groq, narrative-only).
  LLM karar VERMEZ — sadece state'i açıklar/eleştirir/özetler.
  - `packages/agent/llm/` — client (`LLM_MODE=off|mock|groq`; anahtar
    yoksa network'süz fallback), budget (`data/runtime/llm_budget.json`,
    günlük token bütçesi + per-request limit), cache (2 saat, içerik-digest
    anahtarlı), context (kompakt state — raw market data prompt'a girmez),
    guard (injection/bypass → güvenli ret), report (3 persona: analyst /
    risk_officer / macro_strategist; summary/concerns/evidence_used/
    missing_data/actionability/what_would_change_my_mind; evidence_used
    HER ZAMAN backend'den), chat (state-grounded; sembol/TF/intent algılı
    deterministik grounded yanıt; LLM sadece anlatımı akıcılaştırır).
  - API: `/ai-report/current` additive — personas + llm meta +
    timeframe_summary (TF farkları, candidate vs final, blocked_by,
    paper_actions) + no_actionable_decision (DQS BLOCKED / kısıtlayıcı
    risk gate → verdict no_trade). Yeni **`POST /api/v1/chat`**.
  - Web: AIReportPanel persona bölümleri + LLM_GENERATED/DETERMINISTIC
    rozeti + NO ACTIONABLE banner; ChatPanel gerçek endpoint'e bağlı
    (öneri soruları, evidence satırı, GUARD damgası). Selector
    `lib/selectors/ai.ts`, hook `useChat`; page.tsx büyümedi.
  - Hard kurallar testli: decision matrix LLM'li/LLM'siz birebir aynı;
    bypass talebi → refusal; DQS BLOCKED → no actionable; testlerde
    network çağrısı yok (urlopen bekçi).
  - Pytest **150/150** (18 yeni); ruff (CI scope) + tsc + build yeşil.
  - Not: GROQ_API_KEY env'de yoksa sistem deterministik fallback ile tam
    çalışır; anahtar eklenince kod değişikliği gerekmez.

- **T2 tamamlandı**: timeframe consensus + decision matrix + paper
  time-stop + TimeframeMatrixPanel. Sinyal uzayı (symbol, timeframe).
  - Consensus `build(..., timeframe="1d")` — touche `technicals_by_tf`
    okur (DEGRADED → nötr 50); default'la legacy davranış birebir.
  - Decision: `decide_matrix` 5 TF × symbol; `TradeDecision` candidate_action/
    blocked_by/actionable taşır. **RiskGate önce, timeframe sonra**:
    çarpanlar ≤1.0 clamp (15m ×0.25, 1h ×0.5), 1w paper_execution=false →
    asla open (sadece bias); 1w bias çelişkisi alt TF'i ×0.5 küçültür.
    `matrix_view` ViewModel: hücre rozeti ACTIONABLE/NOT_ACTIONABLE/
    SUSPENDED backend'de; DQS BLOCKED veya kısıtlayıcı risk gate →
    `suspended=true`, tüm hücreler SUSPENDED.
  - Paper: `Position.valid_until` (TF time_stop_hours; 15m→6sa);
    tick'te `TIME_STOP_EXIT` (fiyatsız kapanmaz); Trade timeframe taşır;
    (symbol, tf) bazlı açık-pozisyon dedup; legacy kayıtlar "1d"/None.
  - Learning: fingerprint v2 gerçek TF segmenti — 15m hatası 1d'yi
    cezalandırmaz; router/worker duplicate fingerprint üretimi kaldırıldı
    (d.fingerprint kullanılır). Trainer/calibration global kaldı (bilinçli).
  - API: yeni `GET /api/v1/decision/matrix`; paper tick decide_matrix'e
    geçti (aksiyonlar timeframe taşır). OpenAPI dolduruldu.
  - Web: **TimeframeMatrixPanel** (registry `timeframe_matrix`, span 3) —
    candidate→final, blocked_by tooltip, SUSPENDED banner; DecisionPanel
    mini TF strip; TradingPanel pozisyon TF rozeti + valid_until.
    Selector `lib/selectors/decision.ts`; page.tsx tek GridCell.
  - Env: `make api-dev` + `scripts/dev.sh` certifi varsa `SSL_CERT_FILE`
    otomatik; README'de bölüm.
  - Pytest **132/132** (19 yeni T2); ruff + tsc + build yeşil.

- **T1 tamamlandı**: OHLCV provider + gerçek multi-timeframe technicals.
  - `packages/data/providers/ohlcv/` — CoinGecko market_chart (BTC/ETH) +
    Yahoo chart (XAU/XAG/DXY/VIX/...) adapter'ları; disk cache
    (`data/runtime/ohlcv/`, TTL: 15m→5dk ... 1d→6sa); live fail → stale
    cache → boş liste (runtime'da mock/fixture bar ASLA yok).
  - Resample: **4h = 1h bucket**, **1w = 1d ISO hafta** (kripto; yfinance
    1w native); resampled barlar `source="resampled:<base>"`.
  - Gerçek indikatörler: RSI(14)/ATR(14) Wilder, MACD(12/26/9) histogram
    normalize (hist/close×100), EMA stack 20/50/200. Yetersiz bar →
    alanlar None + `TechnicalSnapshot.status="DEGRADED"`, score nötr 50.
  - TF bazlı freshness: 15m>30dk, 1h>2sa, 4h>8sa, 1d>48sa, 1w>10g →
    DEGRADED. Global DQS (fiyat bazlı) ve RiskGate davranışı değişmedi.
  - `MarketSnapshot.technicals_by_tf` dolu (5 TF × DEFAULT_SYMBOLS[:4]);
    legacy `technicals` = 1d snapshot'ın kendisi (geriye uyum).
    `/data/snapshot` additive `technicals_by_tf` döner; OpenAPI'ye
    `OHLCVBar` + `TechnicalSnapshotTF` eklendi.
  - Frontend minimum görünürlük: `MarketDataPanel` TF chip satırı,
    `SnapshotPanel` "TF teknikleri x/y OK"; selector'lar
    `lib/selectors/snapshot.ts`. Panel/page.tsx büyümedi
    (TimeframeMatrixPanel T2'de).
  - Consensus/decision hâlâ yalnızca legacy 1d okur — multi-TF karar T2.
  - Pytest **113/113** (19 yeni T1); ruff + tsc + build yeşil.

- **T0 tamamlandı**: timeframe-first contracts + schema seeding (runtime
  davranış değişmedi, tamamı additive/backward-compatible).
  - `Timeframe = Literal["15m","1h","4h","1d","1w"]` (`data/types.py`);
    `TechnicalSnapshot.timeframe` genişledi; provider passthrough.
  - `Position`/`Trade`/`TradeDecision` → `timeframe` alanı (default "1d";
    legacy JSON kayıtları default ile yüklenir).
  - `MarketSnapshot.technicals_by_tf` opsiyonel taslak (None — T1 doldurur).
  - **Fingerprint v2**: `asset|v2|tf|regime|...` — legacy ile çakışmaz;
    eski kayıtlar doğal karantinada (NEUTRAL fallback).
  - `thresholds.timeframe_risk`: 15m scout ×0.25 / 1h ×0.5 / 4h ×1.0 /
    1d ×1.0 / 1w ×0.0 + `paper_execution: false` (1w trade açamaz).
    Tüm çarpanlar ≤1.0 — sadece risk azaltıcı.
  - `CatalystImpact` contract'ı (Pydantic + OpenAPI) tanımlı — motor
    v2.7'de. `TimeframeDecision`/`DecisionMatrix` OpenAPI taslakları T2 için.
  - Frontend: sadece types (Timeframe/CatalystImpact/TimeframeDecision/
    DecisionMatrix + Position/Trade.timeframe) — panel T2/T4'te.
  - Pytest **94/94** (9 yeni T0); ruff + tsc + build yeşil.
- **v2.6 LLM persona ertelendi** → T1+T2 sonrası (bkz. ROADMAP).

- **G5 tamamlandı**: daily-loss / max-DD halt — file-backed, sadece risk
  azaltıcı.
  - `packages/risk/halt.py` — breach tespiti tick yollarında
    `sync(risk_input)` ile persist edilir (`RISK_HALT_PATH`, default
    `data/runtime/risk_halts.json`). DAILY_LOSS → KILL_SWITCH seviyesi,
    MAX_DRAWDOWN → RISK_REDUCE seviyesi. **Otomatik reset yok** — halt
    sticky; yalnızca `POST /api/v1/risk/halts/reset` (owner) kapatır.
  - `packages/risk/engine.py` — aktif halt ek candidate olarak okunur
    (sadece kısıtlayıcı; mevcut gate'ler değişmedi).
  - KILL_SWITCH halt → `flatten_all` (KILL_SWITCH_EXIT) paper tick +
    tick_worker'da; fiyatı olmayan pozisyon kapatılmaz (mock fiyat yok).
    RISK_REDUCE halt → yeni açılış yok, SL/TP yönetimi sürer.
  - `GET /api/v1/risk/halts` — aktif halt + timeline + gauge metrikleri
    (daily_loss_ratio, drawdown_ratio — frontend hesap yapmaz).
- **Frontend (G5)**: `DrawdownGuardPanel` — DailyLossGauge + MaxDDGauge
  (oran bazlı bar gauge) + KillSwitchTimeline + Owner Reset butonu;
  `TradingPanel` "RISK FREEZE" badge. Selector `lib/selectors/halts.ts`;
  registry `drawdown_guard`; page.tsx'e tek GridCell.
- Pytest: **85/85** yeşil (13 yeni G5 testi). Ruff + tsc + build yeşil.
- Canlı: `/api/v1/risk/halts` 200; SSR'de **27 panel**
  (`drawdown_guard` dahil), HeroScene + PAPER_ONLY korunuyor.

- **G4 tamamlandı**: correlation-aware sizing — sadece risk azaltıcı.
  - `packages/risk/correlation.py` — verified kapalı trade'lerin günlük
    PnL serisinden 30g pencerede pairwise rho (`computed`); ortak gün <
    `correlation_min_overlap_days` (5) → config `correlation_baseline`
    (`baseline`, örn. BTC↔ETH=0.75, XAU↔XAG=0.80); o da yoksa `neutral`
    (rho=0, `insufficient_correlation_data` uyarısı, adjustment yok).
  - `cluster_exposure(open_positions, aday)` — işaretli hizalama
    rho×side×side ≥ 0.7 → aynı risk cluster; ≤ -0.7 → hedge (ayrı
    raporlanır, cap'e girmez). Cluster toplamı ≥ `max_cluster_pct`
    (0.30 equity) → size_factor 0 (hold); ≥ yarısı → ×0.5. **Asla
    artırmaz** (factor ≤ 1.0).
  - `packages/decision/engine.py` — mistake gate'ten sonra cluster cap;
    TradeDecision `cluster_report` taşır. decide_all `open_positions`
    parametresi aldı (paper_trading router + tick_worker geçirir).
  - **Hard kural**: correlation sizing **RiskGate'i bypass etmez**.
    KILL_SWITCH→blocked, RISK_REDUCE/NO_POSITION_INCREASE→hold; DQS<55
    BLOCKED → trade yok.
  - `GET /api/v1/risk/correlation` — matris + open-position cluster'ları
    (union-find, OK/WARNING/BREACH) + insufficient_pairs.
- **Frontend**: `CorrelationPanel` — matrix heatmap (cyan=+, magenta=-)
  + cluster exposure uyarıları; `TradingPanel` flagged cluster satırları
  gösterir. Yeni selector `lib/selectors/correlation.ts`; panel-registry
  `correlation` girişi; page.tsx'e tek GridCell.
- Ayrıca commit'lendi: **provenance mode block** (önceki oturumdan) —
  LIVE/MOCK_MODE/SIMULATION/INSUFFICIENT_DATA damgası dashboard/ai-report
  endpoint'lerinde.
- Pytest: **72/72** yeşil (14 yeni G4 testi: neutral/baseline/computed
  fallback sırası, verified filtresi, REDUCED/CAPPED, hedge, engine cap→
  hold, size×0.5, hedge full size, KILL_SWITCH > correlation, DQS
  BLOCKED → trade yok, endpoint 200 + BREACH cluster).
- Ruff (CI scope): yeşil. Web: `tsc --noEmit` + `pnpm build` yeşil.
- Canlı doğrulandı: `/api/v1/risk/correlation` 200; web SSR'de **26
  panel** (`data-panel="correlation"` dahil), HeroScene canvas +
  PAPER_ONLY banner korunuyor.

- **Local live dev**: `make dev` → API (8000) + web (3000).
  Docker alternatifi: `docker compose -f docker-compose.dev.yml up`.

## Next task

- A1 (audit) + DEP1 (deploy) + UX2 (polish) + REL1 (prod runbook) + UX3 (IA) bitti.
  Backend RC + tek-komut local production + önem-sıralı gruplu cockpit; backend
  FREEZE (yalnızca P0 hotfix).
- Sıradaki (öneri, bkz. `.tasks/NEXT_TASK.md`): **UX4 live feedback polish** VEYA
  **Production dry-run / long-running soak test** VEYA **only P0 backend hotfix mode**.
  Yeni data source / dashboard redesign / intelligence / trading logic YOK.
  Opsiyonel: A1 P1 hardening (H1–H5).
- `.tasks/NEXT_TASK.md` güncellendi.
