.PHONY: help sync install test lint fmt build zhvault
.DEFAULT_GOAL := help

help:
	@echo "Targets: sync install test lint fmt build zhvault ARGS=..."

sync install:
	pip install -e ".[dev]"

test:
	pytest

lint:
	ruff check src

fmt:
	ruff check --fix src

build:
	python -m build

zhvault:
	zhvault $(ARGS)
