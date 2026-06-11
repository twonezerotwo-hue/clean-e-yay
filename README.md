# Clean E-yAy

Clean rewrite of **E_YAY CODEX** — a paper-trading decision-support system that prepares trading-data agents for real execution through paper trading + calibrated heuristic learning.

> Status: **v2.0-skeleton** — monorepo iskeleti. Hiçbir paket henüz implement edilmedi. Endpoint'ler stub.

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

## Geliştirme

```bash
# Backend
cd apps/api && uv sync && uvicorn main:app --reload

# Frontend
cd apps/web && pnpm install && pnpm dev

# Sözleşme codegen
make codegen
```

(Henüz hiçbiri çalışmaz — iskelet aşaması.)

## Lisans

Henüz tanımlanmadı (private repo).
