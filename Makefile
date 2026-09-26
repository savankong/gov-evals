# Aegis Eval — development tasks.
.DEFAULT_GOAL := help
VENV := .venv
PY := $(VENV)/bin/python

.PHONY: help
help: ## Show this help
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

$(VENV):
	python3 -m venv $(VENV)
	$(VENV)/bin/pip install --quiet --upgrade pip

.PHONY: install
install: $(VENV) ## Install API, SDK and web dependencies
	$(VENV)/bin/pip install -e "apps/api[dev]"
	$(VENV)/bin/pip install -e "packages/sdk[dev]"
	cd apps/web && npm install

.PHONY: api
api: ## Run the API on :8000
	cd apps/api && ../../$(VENV)/bin/uvicorn aegis.main:app --reload --port 8000

.PHONY: web
web: ## Run the web UI on :3000
	cd apps/web && npm run dev

.PHONY: worker
worker: ## Run an evaluation worker (needs AEGIS_QUEUE_BACKEND=redis)
	cd apps/api && ../../$(PY) worker.py

.PHONY: test
test: ## Run the API test suite
	cd apps/api && ../../$(VENV)/bin/pytest -q

.PHONY: bench-demo
bench-demo: ## Rebuild the Acquisition Bench demonstration report in docs/examples
	$(PY) scripts/bench_demo.py

.PHONY: typecheck
typecheck: ## Typecheck the web UI
	cd apps/web && npx tsc --noEmit

.PHONY: lint
lint: ## Lint the Python packages
	$(VENV)/bin/ruff check apps/api/aegis packages/sdk/aegis_sdk

.PHONY: check
check: test typecheck ## Everything CI runs

.PHONY: build
build: ## Build the web UI
	cd apps/web && npm run build

.PHONY: up
up: ## Start the whole platform with Docker
	docker compose up --build

.PHONY: clean
clean: ## Remove local state and build output
	rm -rf apps/api/data apps/web/.next $(VENV)
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
