.PHONY: help codegen codegen-check lint test web-dev api-dev dev workers smoke \
        prod-up prod-down prod-status prod-smoke compose-up compose-down

help:
	@echo "Clean E-yAy — make targets"
	@echo "  dev          Start API (9000) + web (4000) together (Ctrl+C kapatır)"
	@echo "  api-dev      FastAPI --reload (9000)"
	@echo "  web-dev      Next.js dev (4000)"
	@echo "  workers      tick_worker daemon + learning_worker one-shot (scripts/workers.sh)"
	@echo "  smoke        Health smoke (API + web SSR; scripts/smoke.sh)"
	@echo "  prod-up      Local production: API+web+tick (background) + learning seed"
	@echo "  prod-down    Stop supervised prod processes"
	@echo "  prod-status  Prod process + port + system/health durumu"
	@echo "  prod-smoke   Health smoke against prod ports (API_PORT/WEB_PORT)"
	@echo "  compose-up   docker-compose dev (api+web+workers)"
	@echo "  compose-down"
	@echo "  codegen      OpenAPI → TS contract types (apps/web/types/generated/schema.ts)"
	@echo "  codegen-check  Fail if generated types are stale vs openapi.yaml"
	@echo "  lint         ruff packages + apps"
	@echo "  test         pytest"

codegen:
	python scripts/codegen.py

codegen-check:
	python scripts/codegen.py --check

lint:
	ruff check packages apps/api apps/tick_worker apps/learning_worker

test:
	pytest

# SSL_CERT_FILE: bazı Python kurulumlarında sistem CA zinciri yok →
# live provider'lar CERTIFICATE_VERIFY_FAILED alır. certifi kuruluysa
# otomatik kullan; env'de zaten set ise ona dokunma.
api-dev:
	PYTHONPATH=. SSL_CERT_FILE="$${SSL_CERT_FILE:-$$(python3 -m certifi 2>/dev/null || python -m certifi 2>/dev/null || true)}" \
		uvicorn apps.api.main:app --reload --host 127.0.0.1 --port 9000

web-dev:
	cd apps/web && pnpm dev --port 4000

dev:
	./scripts/dev.sh

# 7/24 local: tick_worker uzun-ömürlü daemon; learning_worker tek-seferlik
# (prod'da zamanlayıcıyla — restart-always değil).
workers:
	./scripts/workers.sh

# Health smoke — çalışan API (+web) gerekir. İzole port: API_BASE/WEB_BASE override.
smoke:
	./scripts/smoke.sh

# Local production runbook (background pid+log data/runtime/ altında).
# İzole port: API_PORT=9060 WEB_PORT=4060 make prod-up
prod-up:
	./scripts/prod_up.sh

prod-down:
	./scripts/prod_down.sh

prod-status:
	./scripts/prod_status.sh

prod-smoke:
	API_BASE="http://127.0.0.1:$${API_PORT:-9000}" WEB_BASE="http://127.0.0.1:$${WEB_PORT:-4000}" ./scripts/smoke.sh

compose-up:
	docker compose -f docker-compose.dev.yml up --build

compose-down:
	docker compose -f docker-compose.dev.yml down -v
