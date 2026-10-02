# CLAUDE.md — Clean E-yAy çalışma rehberi

Bu dosya, bu repoda çalışan Claude oturumları için kalıcı rehberdir (makine/hesap değişse bile geçerli).
Bugün sistem nasıl çalışıyor: `docs/STATE.md`. Sıradaki iş ve açık owner kararları: `docs/ROADMAP.md`
(tek ileriye dönük plan). Mimari derinlik: `ARCHITECTURE.md`. Eski yol haritaları ve görev kayıtları
`docs/archive/` altında — yalnız tarihçe, talimat değil.

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
11. **Dokümana eskiyen durum kopyalama.** Flag değeri, test sayısı, "X canlı" iddiası dokümana
    yazılmaz; `docs/STATE.md` nereden okunacağını söyler. Durum değişince STATE/ROADMAP güncellenir,
    tarihli "devir notu" bölümü açılmaz.
12. **Temizlik dönemi (2026-10):** yeni özellik/flag/veri kaynağı yok; her PR tek tema; golden
    replay bayt-aynı (bilinçli mantık düzeltmesi hariç). Ayrıntı: `docs/ROADMAP.md`.

## Test / ortam notları

- pytest `--basetemp=.pytest_tmp` (pyproject'te sabit) kullanır; başka basetemp VERME — C:\dev
  köküne `pytest-*` klasörü saçılıyordu. Tüm testler yeşil olmalı; CI-kapsamı ruff temiz.
- **Golden replay (temizlik güvenlik ağı):** `python -m tests.golden.golden_replay --check`.
  Canlı config ile karar matrisini dondurulmuş çıktıyla karşılaştırır (pytest'te de koşar).
  Davranış değiştirmemesi gereken PR'da fark = hata. Bilinçli mantık düzeltmesinde farkı PR
  açıklamasına yaz, sonra `--write` ile golden'ı güncelle.
- **Sözleşme ratchet'i:** yeni route önce `contracts/openapi.yaml`'a eklenir (+ `make codegen`);
  `tests/contract/contractless_routes.txt` yalnız küçülebilir.
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
