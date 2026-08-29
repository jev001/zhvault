.PHONY: help sync install test lint fmt build gate zhvault
.DEFAULT_GOAL := help

help:
	@echo "Targets: sync install test lint fmt build gate zhvault ARGS=..."
	@echo "gate  REQUIRED green check (ruff + full pytest)"

sync install:
	pip install -e ".[dev]"

test:
	pytest

lint:
	ruff check src

fmt:
	ruff check --fix src

gate:
	ruff check src
	pytest

build:
	python -m build

zhvault:
	zhvault $(ARGS)
