# ARGUS developer command surface (M0 spec §13).
#
# One obvious interface for setup, quality gates, Docker build and hooks. Every
# target is a thin wrapper over uv / the already-selected M0 tooling — no shell
# framework, no logic. pyproject.toml owns tool config (Ruff, mypy, pytest,
# coverage threshold); this file never duplicates it.

# Local-only, predictable dev image tag. Never pushed anywhere (M0 spec §12).
IMAGE ?= argus:dev

.PHONY: help sync lint format format-check typecheck test check audit security \
        docker-build hooks-install hooks-run clean

help: ## Show this help.
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "} {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

sync: ## Install locked deps (fails on a stale uv.lock; never updates it).
	uv sync --frozen

lint: ## Ruff lint.
	uv run ruff check .

format: ## Apply Ruff formatting (modifies files).
	uv run ruff format .

format-check: ## Verify Ruff formatting without modifying files.
	uv run ruff format --check .

typecheck: ## Strict mypy over src and tests.
	uv run mypy src tests

test: ## Run pytest (coverage gate enforced by pyproject.toml).
	uv run pytest

# Fail-fast local quality gate, cheap-to-expensive (mirrors CI, M0 spec §10).
# Coverage threshold is NOT repeated here — pytest config owns it.
check: sync lint format-check typecheck test ## Full local quality gate.

# Python dependency vulnerability audit (M0 spec §11; pip-audit owns this layer).
# Audits the locked/synced environment against the PyPA/OSV advisory DB. Needs
# network. NOT part of `make check` (keeps the dev gate fast + offline) and NOT a
# pre-commit hook (M0 spec §8). Reports findings; never auto-fixes or ignores.
audit: ## pip-audit the locked Python environment (needs network).
	uv run pip-audit

# Full security scan surface (M0 spec §13): gitleaks detect + pip-audit. Secrets
# first (Gitleaks owns that layer, §10), then dependency CVEs (reuses `audit`).
# NOT part of `make check` (§13 keeps the pre-PR gate fast/offline) and NOT a
# pre-commit hook. Gitleaks is a separate binary, not a uv dep: if it is not
# installed we fail honestly with the install pointer instead of silently
# downloading a binary. Local prerequisite: https://github.com/gitleaks/gitleaks#installing
security: ## gitleaks detect + pip-audit (requires gitleaks installed locally).
	@command -v gitleaks >/dev/null 2>&1 || { echo "gitleaks not installed; install it: https://github.com/gitleaks/gitleaks#installing"; exit 1; }
	gitleaks detect --source . --redact --verbose
	$(MAKE) audit

docker-build: ## Build the production image with the local dev tag.
	docker build -t $(IMAGE) .

hooks-install: ## Install the pre-commit git hook (explicit; never run by sync/check).
	uv run pre-commit install

hooks-run: ## Run all pre-commit hooks across the whole repo.
	uv run pre-commit run --all-files

clean: ## Remove safe generated caches/artifacts only.
	rm -rf .ruff_cache .mypy_cache .pytest_cache .coverage htmlcov build dist
	find . -path ./.venv -prune -o -type d -name '__pycache__' -exec rm -rf {} +
	find . -path ./.venv -prune -o -type d -name '*.egg-info' -exec rm -rf {} +
