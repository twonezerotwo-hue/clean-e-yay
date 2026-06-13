# Clean E-yAy

Clean rewrite of **E_YAY CODEX** — a paper-trading decision-support system that prepares trading-data agents for real execution through paper trading + calibrated heuristic learning.

> **Nihai mimari için → [ARCHITECTURE.md](ARCHITECTURE.md).** Yeni iş başlamadan önce o belge okunur.
>
> Status: **Backend Release Candidate** (A1 final audit PASS; P0 yok). Veri →
> DQS → consensus/decision → RiskGate → paper → learning → replay/LLM zinciri
> canlı; gerçek provider'lar + v2.7 deep data (türev/options/volatilite/catalyst)
> + LLM persona + 7/24 worker reliability. pytest 419/419, ruff/tsc/build/CI yeşil.
> Backend FREEZE — yalnızca P0 hotfix. Sıradaki: UX2 dashboard polish.

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

### Port çakışması (eski E_YAY CODEX LaunchAgent'ları)

Bu makinede eski `E_YAY CODEX` projesinden kalma LaunchAgent'lar (örn.
`com.eyay.backend` → `0.0.0.0:8000`, `com.eyay.frontend` → `:3000`)
KeepAlive ile çalışıyor olabilir; `kill` yetmez, login'de geri gelirler.

- Clean E-yAy API'sini `--host 127.0.0.1 --port 8000` ile başlat: eski agent
  `0.0.0.0:8000`'de dinlese bile `127.0.0.1` istekleri Clean E-yAy'e gider.
  `lsof -nP -iTCP:8000 -sTCP:LISTEN` iki dinleyici gösterebilir — kafa
  karıştırıcı ama çalışır. Doğrulama: `curl …/api/v1/health` → `version 2.0.0`
  (Clean E-yAy). Başka bir sürüm dönerse eski backend yanıtlıyordur.
- Oturum bazlı kapatma (plist'i silmeden):
  `launchctl bootout gui/$(id -u)/com.eyay.backend`
  (login'de geri gelir; kalıcı kaldırma kullanıcının kararı).

### Docker (node/pnpm lokalde yoksa)

```bash
docker compose -f docker-compose.dev.yml up --build
# api + web ayağa kalkar. Workers istiyorsan:
docker compose -f docker-compose.dev.yml --profile workers up --build
```

### Smoke testleri

Tek komut (çalışan API + opsiyonel web gerekir):

```bash
make smoke
# veya izole port:
API_BASE=http://127.0.0.1:8050 WEB_BASE=http://127.0.0.1:3050 ./scripts/smoke.sh
# yalnızca API:
SKIP_WEB=true ./scripts/smoke.sh
```

`scripts/smoke.sh` şunları 200 bekler: `/api/v1/health`, `/api/v1/system/health`
(+ `paper_safe=true` doğrular), `/api/v1/cockpit/brief`, `/api/v1/data/snapshot`,
`/api/v1/decision/matrix`, `/api/v1/replay/status`, `/api/v1/learning/summary` ve
web SSR `/`. Herhangi biri düşerse exit 1.

```bash
# Birim/sözleşme testleri + lint
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

## Deployment / 7-24 readiness (DEP1)

Backend Release Candidate — gerçek 7/24 local/production-like çalıştırma için
checklist. (Backend FREEZE: yalnızca P0 hotfix; yeni feature/data source yok.)

### Süreçler ve restart politikası

| Süreç | Tip | Restart |
|---|---|---|
| `apps.api.main:app` (uvicorn) | uzun-ömürlü HTTP | restart-always |
| `apps.tick_worker.main` | uzun-ömürlü daemon (`TICK_INTERVAL_SEC`, SIGTERM-aware) | restart-always |
| `apps.learning_worker.main` | **tek-seferlik** (`run_once`) | **zamanlayıcı** (cron/timer) — restart-always **YOK** (spin-loop yapar) |
| `apps/web` (next) | uzun-ömürlü SSR | restart-always |

Üç süreç birbirinden bağımsız (biri çökerse diğerleri etkilenmez); paylaşılan
state `data/runtime/` dosyaları. Local hepsi:

```bash
make dev       # API + web
make workers   # learning one-shot seed + tick daemon (ayrı terminal)
```

### Process supervision (öneri — minimal)

- **Docker compose** (en basit): `docker compose -f docker-compose.dev.yml --profile workers up --build`.
  learning_worker bir kez koşar ve çıkar — günlük için `restart: "no"` + dış
  scheduler ya da ayrı bir cron servisi.
- **macOS launchd**: `com.cleaneyay.api` / `com.cleaneyay.tick` → `KeepAlive=true`;
  `com.cleaneyay.learning` → `StartCalendarInterval` (günlük), `KeepAlive=false`.
  (Eski `com.eyay.*` agent'larıyla port çakışması için aşağıdaki bölüm.)
- **systemd**: api/tick → `Restart=always`; learning → `.timer` unit + `Restart=no`.
- **pm2**: api/tick → normal; learning → `pm2 start … --cron "0 0 * * *" --no-autorestart`.

### Health check & stale worker alert

- Liveness: `GET /api/v1/health` (uptime/version).
- Readiness/ops: `GET /api/v1/system/health` → `workers`, `stale_workers`,
  `last_successful_tick`, `last_learning_run`, `provider_summary`, `dqs_status`,
  `snapshot_store_status`, `risk_halt_status`, `warnings`. **Network-free** —
  STALE/UNKNOWN türetilir (tick > 120s, learning > 3600s eşik).
- Stale alert: `warnings` içinde `worker_stale` / `learning_worker_no_data` /
  `provider_degraded` / `dqs_blocked` / `snapshot_store_empty` / `active_halt`
  varsa owner'a bildir (rapor — yürütme alarmı değil).
- Smoke: `make smoke` (yukarı).

### Logs

Worker'lar stdout'a `logging` yazar (heartbeat cycle, FAILED istisnalar). Supervisor
stdout/stderr'i topla (compose logs / journald / pm2 logs). Paper olay izi ayrıca
append-only `data/runtime/paper_audit.jsonl`.

### Runtime dizinleri (kalıcılık)

Tümü `data/runtime/` altında ve **gitignored** (`data/runtime/`, `data/state/`):
snapshots, `paper_state.json`, `paper_audit.jsonl`, `risk_halts.json`,
`worker_heartbeats.json`, `learning_run.json`, `learning_summary.json`,
`calibration.json`, `rebalance.json`, `llm_budget.json`, `llm_cache.json`,
`ohlcv/`. **Prod**: `data/runtime/` kalıcı bir volume'a mount et (compose
`.:/app` bind-mount host'ta tutar). Tek tek yollar `.env.example`'daki `*_PATH`
ile override edilebilir.

### Environment

Tüm değişkenler + default'lar: [.env.example](.env.example). Uygulama `.env`'i
**otomatik yüklemez** — shell/compose/launchd/systemd ile export et. Kritikler:
`LLM_MODE`/`GROQ_API_KEY` (opsiyonel; yoksa deterministik fallback),
`FRED_API_KEY` (yoksa o quote'lar BLOCKED, mock yok), `PRICE_USE_MOCK=false`
(prod), `SSL_CERT_FILE` (certifi), `TICK_INTERVAL_SEC`, `*_PATH` (kalıcı volume),
`NEXT_PUBLIC_API_BASE_URL` (web).

### Güvenlik / PAPER_SAFE deploy checklist

Deploy etmeden önce doğrula (hepsi kodda yapısal — env ile gevşetilemez):

- [ ] **broker yok** — entegrasyon yok; tek "broker" tokeni LLM injection blocklist.
- [ ] **gerçek emir yok** — `place_order`/`submit_order`/`execute_order`/`ccxt` yok.
- [ ] **live execution yok** — replay/backtest emir üretmez, paper açmaz, refetch/look-ahead yok.
- [ ] **PAPER_ONLY / NO_EXECUTION** — `/system/health` `paper_safe=true`, `no_execution=true` (sabit).
- [ ] **RiskGate final** — DQS<55 → KILL_SWITCH; tüm gate'ler yalnızca kısıtlayıcı, bypass yok.
- [ ] **LLM yalnızca açıklayıcı** — karar yazmaz; injection/bypass → guard refusal.
- [ ] **runtime mock yok** — `PRICE_USE_MOCK=false`; provider fail → `DATA_UNAVAILABLE`.
- [ ] **owner approval** — weights yalnızca owner approve ile değişir.

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
