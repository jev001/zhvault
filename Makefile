.PHONY: help sync install sync-all test test-live lint fmt build gate zhvault clean clean-cache clean-all docs-arch
.DEFAULT_GOAL := help

UV ?= uv

help:
	@echo "Targets: sync install sync-all test test-live lint fmt build gate zhvault clean clean-cache clean-all docs-arch ARGS=..."
	@echo "sync uses uv (fallback: pip). gate = REQUIRED green check"
	@echo "test-live = optional real Zhihu network (ZHVAULT_LIVE_USER + cookie; not in gate)"
	@echo "clean = dist/build/egg-info; clean-cache += caches; clean-all += .venv (never data/)"
	@echo "docs-arch = regenerate docs/harness/ops/architecture.md from src/"

# Django-ish layout: src/ = package, tests/ = suite at repo root
sync install:
	@if command -v $(UV) >/dev/null 2>&1; then \
		$(UV) sync --extra dev; \
	else \
		pip install -e ".[dev]"; \
	fi

sync-all:
	@if command -v $(UV) >/dev/null 2>&1; then \
		$(UV) sync --all-extras; \
	else \
		pip install -e ".[dev,chroma,kuzu,rocksdb,search-ml]"; \
	fi

test:
	@if command -v $(UV) >/dev/null 2>&1; then $(UV) run pytest; else pytest; fi

# Clears addopts so -m live is not AND-ed with "not live". Requires cookie + ZHVAULT_LIVE_USER.
test-live:
	@if command -v $(UV) >/dev/null 2>&1; then \
		ZHVAULT_LIVE=1 $(UV) run pytest -m live -o addopts= $(ARGS); \
	else \
		ZHVAULT_LIVE=1 pytest -m live -o addopts= $(ARGS); \
	fi

lint:
	@if command -v $(UV) >/dev/null 2>&1; then $(UV) run ruff check src tests; else ruff check src tests; fi

fmt:
	@if command -v $(UV) >/dev/null 2>&1; then $(UV) run ruff check --fix src tests; else ruff check --fix src tests; fi

gate:
	@if command -v $(UV) >/dev/null 2>&1; then \
		$(UV) run ruff check src tests && $(UV) run pytest; \
	else \
		ruff check src tests && pytest; \
	fi

build:
	@if command -v $(UV) >/dev/null 2>&1; then $(UV) build; else python -m build; fi

zhvault:
	@if command -v $(UV) >/dev/null 2>&1; then $(UV) run zhvault $(ARGS); else zhvault $(ARGS); fi

# Layered cleanup; never touch data/ or Cookies.json
clean:
	rm -rf dist/ build/
	rm -rf *.egg-info src/*.egg-info

clean-cache: clean
	rm -rf .pytest_cache/ .ruff_cache/
	find . -type d -name __pycache__ -not -path './.venv/*' -not -path './.review-venv/*' -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name '*.pyc' -not -path './.venv/*' -not -path './.review-venv/*' -delete 2>/dev/null || true

clean-all: clean-cache
	rm -rf .venv/ .review-venv/

docs-arch:
	python3 scripts/gen_architecture_docs.py
