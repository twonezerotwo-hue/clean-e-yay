# Clean E-yAy

Clean rewrite of **E_YAY CODEX** — a paper-trading decision-support system that prepares trading-data agents for real execution through paper trading + calibrated heuristic learning.

> **Nihai mimari için → [ARCHITECTURE.md](ARCHITECTURE.md).** Yeni iş başlamadan önce o belge okunur.
>
> Status: **v2.5-web** — dikey dilim canlı (mock veriyle uçtan uca yeşil, 8/8 test, CI yeşil). Sıradaki: v2.1 gerçek data hunter + validator.

## Felsefe

- **Karar-destek**, otonom işlem motoru değil. `PAPER_ONLY`, `REPLAY_ONLY`, `NO_EXECUTION`.
- AI açıklar; deterministic kod karar verir.
- Sözleşme-önce: `contracts/openapi.yaml` tek doğruluk kaynağı; tipler ve client codegen.
- Üç süreç: HTTP API, tick worker, learning worker — biri çökerse diğerleri etkilenmez.

## Mimari

```
apps/
├─ api/              # FastAPI — sadece HTTP yönlendirici, iş yok
├─ tick_worker/      # 30sn döngü, paper trading tick + scheduler
├─ learning_worker/  # walk-forward, kalibrasyon, ağırlık eğitimi
└─ web/              # Next.js — 3D temalı dashboard

packages/
├─ data/             # provider'lar + ingestion + DQS + kalite (TEK paket)
├─ regime/           # makro rejim sınıflandırıcı (4 katman)
├─ consensus/        # 5 modül + confluence + ağırlık motoru
├─ decision/         # consensus + aggregator + confidence (birleşik)
├─ risk/             # RiskEngine + trigger + hard gates (TEK kopya)
├─ paper/            # account, lifecycle, SL/TP, sizing
├─ learning/         # fingerprint + Platt kalibrasyon + walk-forward
└─ agent/            # LLM persona + tool + Groq budget

contracts/
└─ openapi.yaml      # tek doğruluk kaynağı — Pydantic + TS codegen
```

## Faz planı

| Sürüm | Kapsam | Bitiş ölçütü |
|---|---|---|
| v2.0-skeleton | Bu repo | `pytest` boş yeşil, `next build` yeşil |
| v2.1-data | Provider + DQS + 5 kalite katmanı | Eski sistemle aynı snapshot |
| v2.2-decision | Regime + consensus + decision + risk | Replay setiyle parite |
| v2.3-paper | Paper account + tick_worker ayrı process | 1 hafta paralel paper |
| v2.4-learning | learning_worker: fingerprint + kalibrasyon + walk-forward | Calibration grid frontend'de |
| v2.5-web | Next.js: codegen + 3D temayı koru + yeni paneller | Eski 3 endpoint replace |
| v2.6-agent | LLM persona quorum + Groq budget hard limit | Narrative-only |
| v2.7-data+ | Funding rate, options IV, realized vol, korelasyon | Eğitim verisi zenginleşir |

## Hedef sayısal kazanım (E_YAY CODEX karşısında)

- Servis sayısı: **130+ → ~25**
- API router: **60+ → ~12**
- `snapshot_replay` dosyaları: **150 → 5**
- Frontend ErrorBoundary: **6 → 1**
- Frontend Shell: **7 → 1 jenerik**
- Tip senkronizasyonu: **manuel → codegen**

## Hard gates (risk koruma)

- Max günlük zarar: `-2% equity` → yeni pozisyon yok, gün sonu reset
- Max DD: peak'ten `-8%` → KILL_SWITCH, manuel reset
- Korelasyon klasteri: 30g rolling, |ρ| > 0.7 olan iki parite aynı yön toplam ≤ %30
- Volatility regime: realized vol z-score > +2 → boyut çarpanı 0.5

## Öğrenme

- Fingerprint: `asset|regime|direction|score_bucket|confluence|dominant_module`
- Win-rate lookup → AVOID / NORMAL / BOOST
- **Platt scaling** ile confidence kalibrasyonu (`sigmoid(a·logit(p)+b)`)
- Walk-forward 70/30, ileri kayan pencere
- Ağırlık versiyonlu YAML (`weights_v1.x.yaml`), audit trail kalıcı

## Run locally

API + web tek komutla kalksın:

```bash
make dev
# → API  http://127.0.0.1:8000
# → Web  http://127.0.0.1:3000
```

`scripts/dev.sh` arkasından:
- API → `PYTHONPATH=. uvicorn apps.api.main:app --reload --port 8000`
- Web → `pnpm dev --port 3000` (ilk kez `pnpm install` çalıştırır)
- `apps/web/.env.local` yoksa `NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000`
  ile otomatik oluşturulur.
- Ctrl+C ikisini birlikte durdurur.

### Tek tek başlatmak

```bash
# API (FastAPI + reload)
make api-dev

# Web (Next.js dev)
make web-dev
```

### SSL sertifikaları (live provider'lar)

Bazı Python kurulumlarında sistem CA zinciri eksiktir; CoinGecko/Yahoo
çağrıları `CERTIFICATE_VERIFY_FAILED` ile düşer ve dashboard "VERİ YOK"
gösterir. `make api-dev` ve `scripts/dev.sh`, venv'de `certifi` kuruluysa
`SSL_CERT_FILE`'ı otomatik ayarlar. Elle çalıştırıyorsan:

```bash
pip install certifi
SSL_CERT_FILE="$(python -m certifi)" PYTHONPATH=. uvicorn apps.api.main:app --port 8000
```

### Docker (node/pnpm lokalde yoksa)

```bash
docker compose -f docker-compose.dev.yml up --build
# api + web ayağa kalkar. Workers istiyorsan:
docker compose -f docker-compose.dev.yml --profile workers up --build
```

### Smoke testleri

```bash
# Backend
curl http://127.0.0.1:8000/api/v1/health
curl http://127.0.0.1:8000/api/v1/dashboard/state
curl http://127.0.0.1:8000/api/v1/learning/mistakes
curl http://127.0.0.1:8000/api/v1/learning/calibration
curl http://127.0.0.1:8000/api/v1/learning/rebalance/proposal
curl http://127.0.0.1:8000/api/v1/data/snapshot

# Web (HTML)
curl -I http://127.0.0.1:3000

# Tests
make test
make lint
```

### Web ortam değişkenleri

`apps/web/.env.local`:

```env
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000
# Eski isim (NEXT_PUBLIC_API_BASE) hâlâ fallback olarak okunur.
```

### Sözleşme codegen

```bash
make codegen   # OpenAPI → Pydantic + TS (TODO: codegen pipeline)
```

## Agent Development Protocol

Yeni bir göreve başlamadan önce şunları oku:

- [docs/AGENT_CONTEXT.md](docs/AGENT_CONTEXT.md)
- [docs/SAFETY_RULES.md](docs/SAFETY_RULES.md)
- [docs/CURRENT_STATE.md](docs/CURRENT_STATE.md)
- [docs/ROADMAP.md](docs/ROADMAP.md)
- [docs/DASHBOARD_RULES.md](docs/DASHBOARD_RULES.md) (frontend dokunuluyorsa)
- [.tasks/NEXT_TASK.md](.tasks/NEXT_TASK.md)

Uzun mimari promptları tekrar tekrar yapıştırma. Her görev sonunda
`CURRENT_STATE.md` ve `TASK_RESULT.md` güncellenir.

## Lisans

Henüz tanımlanmadı (private repo).
