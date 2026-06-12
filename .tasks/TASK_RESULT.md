# TASK RESULT

Date: 2026-06-12
Task: OPS — contract/replay testleri + codegen drift güvencesi + operasyonel
      sağlamlaştırma (yeni trading feature YOK)
Status: completed

## Prensip

Bu tur sistemin temelini sağlamlaştırdı; karar zincirine dokunulmadı.
PAPER_SAFE / NO_EXECUTION; RiskGate/DQS/KillSwitch/halt sıfır diff.
OpenAPI = tek doğruluk kaynağı; tüm eklemeler additive.

## Ne yapıldı

### 1. Contract testleri (`tests/contract/`, daha önce boştu)
- `test_openapi_contract.py`: `contracts/openapi.yaml`'daki **her side-effect'siz
  GET** endpoint'i TestClient ile çağrılır, response şemaya göre doğrulanır
  (required alanlar + enum üyeleri + `$ref`/`oneOf` recursive; additive alanlara
  izin verilir). Self-maintaining: endpoint listesi spec'ten türetilir.
  - Kapsam: health, regime-report/current, dashboard/state, ai-report/current,
    paper-trading/state, learning/{summary,calibration,mistakes,rebalance/proposal},
    risk/{correlation,halts}, decision/matrix, data/snapshot, replay/status.
  - `test_all_documented_paths_have_router`: openapi'deki her path app'te kayıtlı
    (path drift guard).
  - **Yakaladığı gerçek drift**: `LLMMeta.mode` enum'unda bare `off` → YAML onu
    `False` boolean'ına çeviriyordu; `"off"` olarak tırnaklandı.

### 2. Codegen drift güvencesi (`tests/contract/test_codegen_drift.py`)
- `apps/web/types/generated/api.ts` el-senkron; bu test driftini CI'da yakalar:
  - Her OpenAPI component schema adının bir TS `export type` karşılığı var
    (alias: `TechnicalSnapshotTF→TechnicalTf`).
  - Her OpenAPI enum üyesi TS'te string-literal olarak mevcut.
  - **Yakaladığı gerçek drift**: TS `Trade.close_reason`'da `TIME_STOP_EXIT` ve
    `KILL_SWITCH_EXIT` eksikti → eklendi.
- Bu testler `testpaths=["tests"]` altında CI `pytest`'inde otomatik koşar →
  drift CI'ı kırar.

### 3. Snapshot / replay foundation (dürüst iskelet)
- Disk snapshot store YOK; snapshot'lar in-memory `_CACHE`. Sahte replay/backtest
  üretmedik. Bunun yerine **dürüst rezerve** endpoint'i:
  - `apps/api/routers/replay.py`: `GET /replay/status` (en son okunabilir snapshot
    id + `status: reserved_not_active`, `available: false`) ve
    `GET /replay/{snapshot_id}` (matches_latest döner, replay ÇALIŞTIRMAZ).
  - Web: `ReplayStatusPanel` artık dashboard meta yerine bu endpoint'e bağlı;
    "REZERVE · AKTİF DEĞİL" rozeti + dürüst reason gösterir (selector/hook üzerinden).

### 4. Dashboard/API consistency audit
- Tüm dokümante GET endpoint'leri 200 (contract test). Panel registry'deki her
  data hook'u bu endpoint'lerden birine bağlı; eksik/bozuk endpoint yok.
- page.tsx büyümedi; frontend hesap yapmıyor; selector + generated types.

### 5. OpenAPI ↔ runtime uyumu (additive reconciliation)
- API'de olup openapi'de eksik path'ler eklendi (response şemaları TS'te zaten
  vardı): `/data/snapshot`→DataSnapshot, `/learning/calibration`→CalibrationState,
  `/learning/calibration/retrain`, `/learning/mistakes`→MistakesState,
  `/learning/rebalance/proposal`→RebalanceState, `/paper-trading/reset`,
  `/replay/status`→ReplayStatus, `/replay/{snapshot_id}`→ReplaySnapshotStatus.
- Yeni component şemalar eklendi (TS ile birebir): ProviderStatus, DqsBreakdown,
  LivePrice, ProvenanceMode, DataSnapshot, CalibrationParams, CalibrationState,
  MistakeRecord, MistakeVerdict, MistakesState, WeightDelta, ModulePerf,
  RebalanceProposalRecord, RebalanceState, ReplayStatus, ReplaySnapshotStatus.
- TS tarafı: `OHLCVBar` + replay tipleri eklendi; `DataSnapshot.mode` gerçek
  runtime şekline (`ProvenanceMode`, 7 alan) düzeltildi (eski `SnapshotMode` subset'ti).

### 6. Dev reliability
- README: eski `E_YAY CODEX` LaunchAgent port çakışması (`com.eyay.backend` →
  `0.0.0.0:8000`) için troubleshooting bölümü + `launchctl bootout` çözümü;
  smoke listesine `decision/matrix` + `replay/status` eklendi.
- SSL_CERT_FILE/certifi zaten dokümante (`make api-dev`/`scripts/dev.sh` otomatik).

## Files changed

- `apps/api/routers/replay.py` — yeni (dürüst rezerve replay endpoint'i).
- `apps/api/main.py` — replay router register.
- `contracts/openapi.yaml` — eksik path'ler + 16 yeni component schema; `off`→`"off"`.
- `apps/web/types/generated/api.ts` — OHLCVBar + replay tipleri; DataSnapshot.mode→
  ProvenanceMode; Trade.close_reason enum tamamlandı.
- `apps/web/lib/api/client.ts`, `lib/queries/{keys,hooks}.ts` — replayStatus wiring.
- `apps/web/components/panels/ReplayStatusPanel/index.tsx` — dürüst rezerve görünüm.
- `tests/contract/{__init__.py,test_openapi_contract.py,test_codegen_drift.py}` — yeni.
- `README.md` — port çakışması + smoke.

## Tests run

- `pytest` → **209 passed** (191 → +18 contract/drift). Live network yok.
- `ruff check packages apps/api apps/tick_worker apps/learning_worker` + `tests/contract`
  → **All checks passed**.
- web `tsc --noEmit` → **exit 0**; `pnpm build` → **✓ Compiled successfully**.

## Live dashboard smoke

- Clean E-yAy API `127.0.0.1:8000` (eski `0.0.0.0:8000` agent'ın yanında, SSL_CERT_FILE
  ile, live network): health `version 2.0.0`; data/snapshot, dashboard/state,
  decision/matrix, regime-report/current, risk/correlation, risk/halts,
  learning/{summary,calibration,mistakes} → **hepsi 200**.
- `replay/status` → `reserved_not_active`, `available:false`, latest snapshot id;
  `replay/{id}` → matches_latest false, replay çalıştırmaz.
- Web `127.0.0.1:3000` (next dev): SSR **200**, **28 panel** (Replay Durumu dahil),
  HeroScene canvas + PAPER banner korunuyor.

## PAPER_SAFE check

- broker: none · real order: none · live execution: none · replay: rezerve (sahte yok).
- RiskGate/DQS/KillSwitch/halt: sıfır diff. LLM karar motoruna dokunulmadı.
- Frontend hesap yapmıyor; page.tsx büyümedi; tüm şema değişiklikleri additive.

## SKIPPED / NEXT (bilinçli)

- Gerçek replay/backtest motoru YAPILMADI (sahte replay yasak; rezerve dürüstçe
  raporlandı). Gerçek deterministik replay → disk snapshot store + replay engine
  gerektirir; ayrı slice.
- `openapi-typescript` ile gerçek codegen otomasyonu kurulmadı; drift guard testi
  bu boşluğu CI'da kapatıyor (manuel sync güvenli).
- NEXT: v2.6 LLM persona derinleştirme **veya** v2.7 deep data — bkz. NEXT_TASK.md.
