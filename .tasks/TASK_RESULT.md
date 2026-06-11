# TASK RESULT

Date: 2026-06-11
Task: L — Local live dev environment (API + web)
Status: completed

## Files changed

- `Makefile` — `dev` (scripts/dev.sh), `api-dev` (PYTHONPATH), `web-dev`,
  `compose-up`, `compose-down`.
- `scripts/dev.sh` (new) — tek komut: API (8000) + web (3000); env auto
  bootstrap; Ctrl+C clean shutdown.
- `apps/web/.env.example` (new) — `NEXT_PUBLIC_API_BASE_URL`.
- `apps/web/lib/api/client.ts` — `NEXT_PUBLIC_API_BASE_URL` tercih,
  `NEXT_PUBLIC_API_BASE` fallback, default `127.0.0.1:8000`.
- `apps/api/main.py` — CORS: `DEV_CORS=true` → "*"; whitelist 3000/3001 +
  `CORS_EXTRA_ORIGINS`.
- `docker-compose.dev.yml` (new) — api + web + (profil) tick_worker +
  learning_worker; tek bind-mount; PAPER_SAFE.
- `README.md` — "Run locally" bölümü: `make dev`, smoke testleri,
  docker-compose, env değişkenleri.
- `.gitignore` — `.claude/` (yerel ajan config gitignore).
- `apps/web/pnpm-lock.yaml` — pnpm install ile oluştu, commit (CI reproducibility).

## Smoke test (canlı)

API ✅ tüm 6 endpoint 200:
- `/api/v1/health` → 200
- `/api/v1/dashboard/state` → 200
- `/api/v1/learning/mistakes` → 200
- `/api/v1/learning/calibration` → 200
- `/api/v1/learning/rebalance/proposal` → 200
- `/api/v1/data/snapshot` → 200

Web ✅ `http://127.0.0.1:3000` HTTP 200 (~18.3 KB), Ready in 5.8s.

Render edilen paneller (`data-panel` markerları, 25 adet):
agent_votes, ai_report, calibration, capital_rotation, chat,
command_signals, data_quality, decision, event_calendar, learning,
market_data, mistake_memory, news, panel_audit, patterns,
position_checks, provider_status, replay_status, risk_gate, scenario,
snapshot, system_health, trading, weight_history, weight_proposal.

Görünür başlıklar: "Karar Merkezi", "Risk Kapısı", "Veri Kalitesi",
"Sağlayıcı Durumu", "Snapshot", "Piyasa Verisi", "Ağırlık Önerisi",
"Calibration", "Mistake Memory". HeroScene `<canvas>` ve `PAPER_ONLY`
banner doğrulandı.

Console error: yok (web log temiz, hata grep boş).

## Tests run

- `pytest -q` → 47/47 passed.
- `ruff check packages apps/api apps/tick_worker apps/learning_worker`
  → All checks passed.
- Web HTML SSR smoke ✅.

## Result

passed

## Notes

- Lokal node: ~/.local/node (Node 20 binary, brew failed Tier 2);
  corepack ile pnpm 9.0.0 aktif.
- Preview MCP sandbox `Clean E-yAy` directory'sini reddetti (harness
  E_YAY CODEX'e bağlı). Yine de web başarıyla başlatıldı (`nohup` +
  background Bash), SSR HTML doğrulandı.
- Browser screenshot için kullanıcı `http://127.0.0.1:3000` açar
  (klavyeden veya `open` ile).

## Next

- G4 — correlation-aware sizing. Live dev artık hazır; her panel
  değişikliği için ayrı doğrulama yapılır.
