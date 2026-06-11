# Current State — Clean E-yAy

_Bu dosya kısa ve güncel tutulur. Her görev sonunda güncellenir._

## Last known status

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

- **v2.6** — LLM persona (Groq, narrative-only; bkz. `docs/ROADMAP.md`).
- `.tasks/NEXT_TASK.md` v2.6 için hazır.
