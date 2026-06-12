# NEXT TASK — OPS: contract/replay testleri + operasyonel sağlamlaştırma

Önerilen sıra (v2.6 sonrası): **OPS önce**, v2.7 deep data sonra.
Gerekçe: 16+ endpoint var ve `apps/web/types/generated/api.ts` elle
senkronize ediliyor (`make codegen` "not yet implemented") — OpenAPI ↔
backend ↔ frontend drift'ini hiçbir test yakalamıyor. v2.7 provider
yüzeyini (funding/OI/options IV/gerçek haber) büyütmeden önce sözleşme
güvencesi kurulmalı.

## Scope

- **Contract tests** (`tests/contract/` — şu an boş): her OpenAPI path'i
  için response'un şemayla uyumunu doğrula (required alanlar, enum
  değerleri, tip uyumu). OpenAPI'de olmayan endpoint CI'da fail etsin.
- **Codegen**: `make codegen` gerçek implementasyon (openapi-typescript
  veya eşdeğeri) VEYA minimum: TS tipleriyle OpenAPI şemasını karşılaştıran
  drift testi.
- **Snapshot replay**: `data/snapshots/`'tan diskten replay akışını test
  altına al (`GET /api/v1/replay/{snapshot_id}` contract'ta vardı —
  mevcut durumla hizala veya kapsam dışıysa belgele).
- **Telemetry**: `POST /api/v1/telemetry/panel-error` hattını doğrula
  (frontend panel crash → backend log).
- CI: contract job eklenir; pytest + ruff + tsc + build yeşil kalır.

## Hard rules

- PAPER_SAFE / NO_EXECUTION; RiskGate/DQS/KillSwitch/halt sıfır diff.
- Endpoint path'leri ve response alan adları DEĞİŞMEZ (additive olabilir).
- Testlerde live network yok.

## Sonra

- **v2.7 deep data** + **T3 catalyst half-life motoru** (funding, OI,
  options IV, gerçek haber feed'i + CatalystImpact engine).
