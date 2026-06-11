.PHONY: help codegen lint test web-dev api-dev

help:
	@echo "Clean E-yAy — make targets"
	@echo "  codegen   Regenerate Pydantic + TypeScript types from contracts/openapi.yaml"
	@echo "  lint      Run ruff on Python packages"
	@echo "  test      Run pytest"
	@echo "  web-dev   Start Next.js dev server"
	@echo "  api-dev   Start FastAPI with reload"

codegen:
	@echo "[codegen] OpenAPI → Pydantic + TS (not yet implemented)"

lint:
	ruff check packages apps/api apps/tick_worker apps/learning_worker

test:
	pytest

web-dev:
	cd apps/web && pnpm dev

api-dev:
	cd apps/api && uvicorn main:app --reload
