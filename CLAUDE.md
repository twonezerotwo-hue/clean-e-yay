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
- Lokal ↔ AWS runtime state AYRI (`data/runtime/` gitignored) — state git ile taşınmaz.
- LLM: lokalde `LLM_MODE=ollama` + qwen2.5:7b (Ollama kuruluysa); AWS'te remote fallback.
  Anahtar/Ollama yoksa sistem deterministik fallback ile sorunsuz çalışır.

## Güncel durum — 2026-07-11 devir anı (tarihli; eskiyebilir, güncelini roadmap'te ara)

- **reentry_guard** (`packages/paper/reentry_guard.py`, commit `5f0ebde`): owner'ın en büyük
  problemi — kârda kapatınca 30 sn'de aynı bayat sinyalle geri girme — için tekrar-giriş kilidi.
  SHADOW'da (`reentry_guard.enabled: false`), tick log'unda kanıt birikiyor; yeter kanıtta owner
  `true` yapar (iki ortam + tick_worker restart). Owner manuel açılışları MUAF.
- **Denetim yol haritası 2026-07 BİTTİ** (PR #49–#53 merge). Aktif: Paket 1, tf_platt,
  TF_CALIBRATION_AUTO_ONLY, TF_TARGET_AUTO_ONLY (watchdog ARM), E-9 trailing_tf_aware.
  `EDGE_GATE=0` KALIR (owner kararı).
- **Sinyal defteri** (`packages/signals`): 8 sinyal; yalnız 4h-structure ve 1d-trend hakiki edge.
  Bar arşivi + D4 per-TF trust kapısı AKTİF. Sıra: D5 karne otomasyonu → D6 tf_scoring_v2 gölge →
  D7 yarış+terfi (owner onayı).
- **Öğrenme katmanı** (I serisi) CANLI; LEARNING_INCLUDE_SHADOW aktif. learning_advisor GÖLGE
  (`LEARNING_ADVISOR_APPLY` default OFF). Sıra: context.py'ye bağlama + Şerit A.
- **Conflict gate:** POSITION HARD_MANUAL; INTRADAY/TACTICAL HARD; SCALP/SWING OFF.
  self_conflict_guard CANLI. Ağırlık auto-apply (G3) dar bantta AÇIK (outcome-rollback'li).
- **Çürütülen fikirler** (tekrar deneme): SMC setup dedektörü + yön yeniden-ağırlık — 5Y derin
  backtestte negatif, söküldü. Ham yön skoru yazı-tura; owner edge'i sabit formüle sığmıyor.
