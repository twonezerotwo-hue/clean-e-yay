.PHONY: help codegen lint test web-dev api-dev dev compose-up compose-down

help:
	@echo "Clean E-yAy — make targets"
	@echo "  dev         Start API (8000) + web (3000) together (Ctrl+C kapatır)"
	@echo "  api-dev     FastAPI --reload (8000)"
	@echo "  web-dev     Next.js dev (3000)"
	@echo "  compose-up  docker-compose dev (api+web+workers)"
	@echo "  compose-down"
	@echo "  codegen     OpenAPI → Pydantic + TS"
	@echo "  lint        ruff packages + apps"
	@echo "  test        pytest"

codegen:
	@echo "[codegen] OpenAPI → Pydantic + TS (not yet implemented)"

lint:
	ruff check packages apps/api apps/tick_worker apps/learning_worker

test:
	pytest

# SSL_CERT_FILE: bazı Python kurulumlarında sistem CA zinciri yok →
# live provider'lar CERTIFICATE_VERIFY_FAILED alır. certifi kuruluysa
# otomatik kullan; env'de zaten set ise ona dokunma.
api-dev:
	PYTHONPATH=. SSL_CERT_FILE="$${SSL_CERT_FILE:-$$(python3 -m certifi 2>/dev/null || python -m certifi 2>/dev/null || true)}" \
		uvicorn apps.api.main:app --reload --host 127.0.0.1 --port 8000

web-dev:
	cd apps/web && pnpm dev

dev:
	./scripts/dev.sh

compose-up:
	docker compose -f docker-compose.dev.yml up --build

compose-down:
	docker compose -f docker-compose.dev.yml down -v
