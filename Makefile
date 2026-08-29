.PHONY: help sync install sync-all test lint fmt build gate zhvault
.DEFAULT_GOAL := help

UV ?= uv

help:
	@echo "Targets: sync install sync-all test lint fmt build gate zhvault ARGS=..."
	@echo "sync uses uv (fallback: pip). gate = REQUIRED green check"

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
