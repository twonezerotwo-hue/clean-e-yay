# CLAUDE.md — Clean E-yAy çalışma rehberi

Bu dosya, bu repoda çalışan Claude oturumları için kalıcı rehberdir (makine/hesap değişse bile geçerli).
Mimari için `ARCHITECTURE.md` + `README.md`; süregelen işlerin TEK kaynağı `docs/AUDIT_ROADMAP.md`.

## Proje ne yapar

Paper-trading **karar-destek** sistemi — otonom işlem motoru DEĞİL. Karar deterministik kod verir;
LLM yalnız anlatır. `PAPER_ONLY` / `NO_EXECUTION` kodda yapısal olarak zorlanır, gevşetilmez.
Üç süreç: HTTP API (`apps/api`), tick worker (30 sn döngü), learning worker (tek-seferlik, zamanlayıcıyla).

## Değişmez çalışma kuralları (owner kararları)

1. **Çalışan sistemi bozma.** Additive-only; eklenen her modül gerçekten kullanılmalı; ölü kod bırakma.
2. **Gölge-önce.** Yeni fikir → shadow modül + flag default KAPALI; canlıya terfi yalnız kanıt + owner
   onayıyla. Flag kapalıyken davranış **bayt-aynı** olmalı; rollback her zaman mümkün olmalı.
3. **Kısa pencere backteste güvenme.** Yeni edge fikri önce 5 yıllık çok-rejim backtestten geçer
   (2 aylık "zafer" örneklem şansı çıkabiliyor — bu ders pahalı ödendi).
4. **Shadow→yön terfisi KIRMIZI ÇİZGİ** (CP5): owner onayı olmadan gölge zekâyı yön kararına bağlama.
5. **Düz dille raporla.** Owner'a önce "ne işe yarıyor" günlük dille; sayıyı etkisiyle ver.
   Jargon commit mesajı ve roadmap'te kalsın.
6. **Lokal + AWS her zaman senkron.** Config/flag değişince ikisini birden uygula, ayrıca sorma.
   AWS .env'i `scripts/deploy-from-github.sh` `ensure_env` ile git üzerinden senkronlanır;
   YAML config-flag'leri zaten git ile taşınır.
7. **Efektif config'i oku.** Flag AÇIK/KAPALI iddiasından önce YAML'a bak; dataclass `= False`
   çoğu zaman config'te ezilir.
8. **Commit/push politikası.** Roadmap dilimlerinde otomatik roadmap-güncelle + commit + push
   (owner kararı, devir için). Roadmap dışı işlerde önce sor. Push öncesi tam doğrulama (test) ŞART.
9. **Yeni env-flag eklerken:** conftest'e `delenv` + `scripts/flag-sync-check.sh` SYNC_FLAGS listesine ekle.
   YAML flag ise flag-sync-check gerekmez (git taşır).
10. **PowerShell script'lerine ASCII dışı karakter YAZMA** (keep-alive zinciri kırılıyor).

## Test / ortam notları

- pytest Windows'ta Temp kilidine takılırsa (WinError 5): `--basetemp` ile yazılabilir dizin ver
  (örn. `.pytest_tmp/`). Baseline: ~939 test yeşil; ruff'ta 40 ESKİ hata var — yenisini ekleme.
- Fresh clone: `.\scripts\bootstrap.ps1` (Win) veya `./scripts/bootstrap.sh` — venv + bağımlılık + smoke.
- Dashboard prod: port 4000'de `next start` (`.next-prod`). FE değişince `.next-prod` rebuild +
  `scripts/start-dashboard.ps1`. Aynı portta `next dev` çalıştırma — çakışma beyaz ekran yapar.
- Lokalde YAML config-flag aktivasyonu worker restart ister (`lru_cache`).
- AWS: main'e merge = GitHub Actions self-hosted runner ile otomatik canlı deploy (worker'lar restart
  edilir). EC2'ye SSH YOK; kutuda komut koşturmak gerekirse pull_request tetiklemeli draft PR
  workflow'u kullanılır (workflow_dispatch branch'e 404 verir).
- **Deploy EC2 CI'ya bağlı: CI kırmızıysa deploy SESSİZCE skip → AWS drift (push "başarılı" görünür).**
  Push öncesi `.githooks/pre-push` (ruff guard, `git config core.hooksPath .githooks` ile aktif —
  bootstrap yapar) CI-red'in en yaygın sebebini yakalar. Push SONRASI `scripts/deploy-status.sh`
  remote HEAD gerçekten AWS'e gitti mi doğrular (senkron değilse sebebiyle uyarır). F1, 2026-07-12.
- Lokal ↔ AWS runtime state AYRI (`data/runtime/` gitignored) — state git ile taşınmaz.
- LLM: lokalde `LLM_MODE=ollama` + qwen2.5:7b (Ollama kuruluysa); AWS'te remote fallback.
  Anahtar/Ollama yoksa sistem deterministik fallback ile sorunsuz çalışır.

## Güncel durum — 2026-07-11 devir anı (tarihli; eskiyebilir, güncelini roadmap'te ara)

- **2026-07-19 — T serisi tamir hattı BİTTİ (owner talimatı: "random ilerleme yok,
  önem sırasına göre tamir").** 17 Temmuz dış denetiminin P0/P1'leri kapatıldı
  (roadmap "T serisi" tablosu): T0 test zemini (2027→2048 test, 0 kırmızı) →
  T1 yan kapı söküldü (tek tick yolu worker; ticket/recheck/bildirim worker'a
  taşındı — prod'da fiilen ölüydü) → T2 kimlik kilidi (API Bearer + Worker parola;
  AKTİVASYON owner secret'larına bağlı) → T3 defter transaction'ı (süreçler-arası
  kilit + revision; lost-update bitti) → T4 pending dolum tazeliği (halt/anomali/
  duplicate beklemesi) → T5 fırtına kuralı tamiri (gates'te, flag default KAPALI =
  izleme; aktivasyon owner'da). Sonraki tur sırası roadmap'te sabit: masraf
  muhasebesi → anons taşınımı → sinyal kimliği → tek karne.
- **reentry_guard** (`packages/paper/reentry_guard.py`, commit `5f0ebde`): owner'ın en büyük
  problemi — kârda kapatınca 30 sn'de aynı bayat sinyalle geri girme — için tekrar-giriş kilidi.
  SHADOW'da (`reentry_guard.enabled: false`), tick log'unda kanıt birikiyor; yeter kanıtta owner
  `true` yapar (iki ortam + tick_worker restart). Owner manuel açılışları MUAF.
- **Denetim yol haritası 2026-07 BİTTİ** (PR #49–#53 merge). Aktif: Paket 1, tf_platt,
  TF_CALIBRATION_AUTO_ONLY, TF_TARGET_AUTO_ONLY (watchdog ARM), E-9 trailing_tf_aware.
  `EDGE_GATE=0` KALIR (owner kararı).
- **Teknik oy = tf_scoring_v4 CANLI (2026-07-12 owner kararı, sürüm çorbası bitirildi).**
  Kademe: `consensus.touche_v4=true` → v4 owner formülü BİRİNCİL; v4 çekimserse
  **touche_backup** (tf_scoring_v2 rejim-anahtarlı, yalnız EDGE-kanıtlı — 06-12 Tem arası canlı
  motordu) konuşur; ikisi de yoksa zemin teknik motor (snapshot). Üretici
  `tf_scoring_shadow.py` (env-flag `TF_SCORING_V2_SHADOW` tarihsel ad) artifact'ı 3 saatten
  bayatsa otomatik zemine düşülür. Her hücrede `touche_observe:base=..:backup=..:v4=..:used=..`.
  Geri-alma tek satır: `touche_v4: false`. NOT: v4 kanıtı backtest-only (kural #3'e owner'ın
  gözü-açık istisnası) → `tf_scoring_race` DOĞRULAMA KARNESİ canlı ölçer (v4 vs backup vs
  al-tut; COLLECTING/V4_AHEAD/V4_BEHIND — otomatik aksiyon YOK, karar owner'ın). v3 + eski
  yarış/terfi tasarımları söküldü. Sinyal defteri (`packages/signals`, 8 sinyal) + bar arşivi +
  D4 per-TF trust + karne otomasyonu AKTİF (backup'ın ağırlık kaynağı).
- **Öğrenme katmanı** (I serisi) CANLI; LEARNING_INCLUDE_SHADOW aktif. learning_advisor GÖLGE
  (`LEARNING_ADVISOR_APPLY` default OFF). Sıra: context.py'ye bağlama + Şerit A.
- **Conflict gate:** POSITION HARD_MANUAL; INTRADAY/TACTICAL HARD; SCALP/SWING OFF.
  self_conflict_guard CANLI. Ağırlık auto-apply (G3) dar bantta AÇIK (outcome-rollback'li).
- **Çürütülen fikirler** (tekrar deneme): SMC setup dedektörü + yön yeniden-ağırlık — 5Y derin
  backtestte negatif, söküldü. Ham yön skoru yazı-tura; owner edge'i sabit formüle sığmıyor.
