.PHONY: install dev api web build test types enrich cache eval

install:            ## Python + web dependencies
	uv sync
	cd web && pnpm install

dev:                ## API on :8000 and Vite on :5173 (proxying /api)
	@trap 'kill 0' INT; uv run uvicorn backend.main:app --reload --port 8000 & (cd web && pnpm dev) & wait

build:              ## Build the frontend into web/dist (served by FastAPI)
	cd web && pnpm build

start: install build  ## One command: install, build the UI, serve UI + API on :8000
	uv run uvicorn backend.main:app --port 8000

test:
	uv run pytest -q

types:              ## Regenerate TypeScript types from the Pydantic models
	uv run python -c "import json; from backend.main import app; print(json.dumps(app.openapi()))" > /tmp/offer-planner-openapi.json
	cd web && npx openapi-typescript /tmp/offer-planner-openapi.json -o src/api/schema.gen.ts

enrich:             ## OFFLINE: re-tag the catalog with the LLM, diff against reviewed tags
	uv run python -m scripts.enrich

cache:              ## Run all sample briefs live and save them for instant replay
	uv run python -m scripts.cache_examples

eval:               ## Golden-set evals (N=repeats)
	uv run python -m evals.run --repeats $${N:-1}
