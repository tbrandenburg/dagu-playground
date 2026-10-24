SHELL := /bin/sh
.DEFAULT_GOAL := help
PORT ?= 8100
WORKERS ?= 2
PYTHON ?= python3
export PORT

.PHONY: help up spawn-up down spawn-down scale ready demo recipe test-recipe validate test test-unit test-scale test-lifecycle lint check logs status reset

help: ## Show the playground commands
	@awk 'BEGIN {FS = ":.*## "} /^[a-zA-Z_-]+:.*## / {printf "  %-20s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

up: ## Start server and two workers (PORT=8100 WORKERS=2)
	$(PYTHON) -m scripts.manage up --workers "$(WORKERS)" --port "$(PORT)"

spawn-up: up ## Alias for up

down: ## Stop this playground; keep server history
	docker compose down --timeout 20

spawn-down: down ## Alias for down

scale: ## Resize workers: make scale WORKERS=3 (1..5)
	$(PYTHON) -m scripts.manage scale --workers "$(WORKERS)" --port "$(PORT)"

ready: ## Wait for worker registration
	$(PYTHON) -m scripts.manage ready --port "$(PORT)"

demo: up validate ## Run and verify distributed, filesystem, parallel, retry, and local demos
	$(PYTHON) -m scripts.demo

recipe: up ## Refresh upstream recipe, validate, deploy, and run it on a worker
	$(PYTHON) -m scripts.recipe

test-recipe: up ## Check recipe refresh and real HTTP failure/retry behavior
	$(PYTHON) -m scripts.recipe --test

validate: ## Validate workflow definitions using the actual Dagu binary
	docker compose exec -T dagu sh -c 'for dag in /var/lib/dagu/dags/*.yaml; do dagu validate "$$dag" || exit; done'

test-unit: ## Run dependency-free tooling regression tests
	$(PYTHON) -m unittest discover -s tests -v

test: test-unit demo ## Run the demo plus real negative acceptance tests (leaves stack running)
	$(PYTHON) -m scripts.verify failures

test-scale: up ## Exercise 1 and 3 workers, restoring the original replica count
	$(PYTHON) -m scripts.verify scaling

test-lifecycle: demo ## Recreate the stack and verify retained history and logs
	$(PYTHON) -m scripts.verify persistence

lint: ## Check Python style/format and YAML/Markdown formatting (requires uv and npx)
	uvx ruff==0.14.2 check scripts tests
	uvx ruff==0.14.2 format --check scripts tests
	npx --yes prettier@3.6.2 --check '**/*.yaml' '**/*.md'

check: lint test ## Run local quality gates and real Docker acceptance tests

status: ## Show containers and registered workers
	docker compose ps
	$(PYTHON) -m scripts.manage ready --port "$(PORT)"

logs: ## Follow server and worker logs
	docker compose logs --follow --tail 100

reset: ## Delete playground history (requires CONFIRM=reset)
	@test "$(CONFIRM)" = reset || { echo 'Destructive: use make reset CONFIRM=reset'; exit 1; }
	docker compose down --volumes --timeout 20
