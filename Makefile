.PHONY: help codegen codegen-check lint test web-dev api-dev dev run smoke

help:
	@echo "Clean E-yAy — make targets"
	@echo "  dev          Start API (9000) + web (4000) together (Ctrl+C kapatır)"
	@echo "  api-dev      FastAPI --reload (9000)"
	@echo "  web-dev      Next.js dev (4000)"
	@echo "  run          Supervisor: API + tick + learning tek süreçte (canlıdaki gibi)"
	@echo "  smoke        Health smoke (API + web SSR; scripts/smoke.sh)"
	@echo "  codegen      OpenAPI → TS contract types (apps/web/types/generated/schema.ts)"
	@echo "  codegen-check  Fail if generated types are stale vs openapi.yaml"
	@echo "  lint         ruff packages + apps"
	@echo "  test         pytest"

codegen:
	python scripts/codegen.py

codegen-check:
	python scripts/codegen.py --check

lint:
	ruff check packages apps/api apps/tick_worker apps/learning_worker apps/supervisor

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

# Canlıdaki çalışma şekli (lokal keeper ve AWS ile aynı süreç).
run:
	PYTHONPATH=. API_HOST=127.0.0.1 python -m apps.supervisor

# Health smoke — çalışan API (+web) gerekir. İzole port: API_BASE/WEB_BASE override.
smoke:
	./scripts/smoke.sh
