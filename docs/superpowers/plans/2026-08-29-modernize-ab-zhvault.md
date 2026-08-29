# zhvault Modernize A+B Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Project/CLI named `zhvault`; code under `src/` as setuptools import root (no `src/zhvault` / `src/zhihu_backup`); Makefile + console script; split CLI into `src/cli/`.

**Architecture:** `[tool.setuptools.package-dir] "" = "src"`; move current `zhihu_backup` package body to `src/`; imports become top-level (`cli`, `storage`, …); script `zhvault = "cli:main"`.

**Tech Stack:** Python 3.10+, setuptools, argparse, ruff, pytest, build, Makefile.

## Global Constraints

- No directory `src/zhvault` or `src/zhihu_backup`.
- No importable `zhvault` or `zhihu_backup` package; CLI/project name is `zhvault` only.
- CLI flags/exit codes/JSON events unchanged.
- No Typer/async/Main.py deletion; no new runtime deps.
- Do not commit secrets; commit per task; `make test` green.

---

### Task 1: Flatten into src/ + packaging + Makefile

**Files:**
- Move: `zhihu_backup/*` → `src/` (result: `src/cli.py`, `src/storage/`, …)
- Delete: empty `zhihu_backup/` after move
- Create: `Makefile`, update `pyproject.toml`, `.gitignore`, `README.md`, `requirements.txt`
- Modify: all imports in `src/**` and `tests/**`: `zhihu_backup.` → strip prefix
- Create: `tests/test_cli_entry.py` (import `cli` works after install)

**Interfaces:**
- Produces: `from cli import main`; console scripts `zhvault`, deprecated `zhihu-backup`; `make sync|test|lint|build`

- [ ] **Step 1: Failing test for top-level cli import**

```python
# tests/test_cli_entry.py
def test_cli_main_importable():
    from cli import main, build_parser
    assert callable(main)
    assert callable(build_parser)
```

- [ ] **Step 2: `pytest tests/test_cli_entry.py -q` — fail until layout exists**

- [ ] **Step 3: Move + rewrite imports + pyproject + Makefile**

```bash
mkdir -p src
git mv zhihu_backup/auth.py zhihu_backup/models.py ... src/   # or mv whole tree then flatten
# Prefer: git mv zhihu_backup src/zhihu_backup_tmp && git mv src/zhihu_backup_tmp/* src/ && rmdir ...
```

Rewrite every `from zhihu_backup.` / `import zhihu_backup` in `src/` and `tests/` to top-level (`from storage…`, `from cli…`, `from mutate…`, etc.). Logger names may become `"zhvault.cli"` string only (not a package).

`pyproject.toml`:

```toml
[project]
name = "zhvault"
# dependencies unchanged

[project.optional-dependencies]
dev = ["pytest>=8.0", "ruff>=0.6", "build>=1.2"]
# chroma, kuzu, search-ml unchanged

[project.scripts]
zhvault = "cli:main"
zhihu-backup = "cli:main"

[tool.setuptools.package-dir]
"" = "src"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
pythonpath = ["src"]   # so tests collect without install in some runners; still prefer make sync

[tool.ruff]
line-length = 100
target-version = "py310"
src = ["src"]
```

`Makefile` as in spec (`help`, `sync`/`install`, `test`, `lint`, `fmt`, `build`, `zhvault`).

`.gitignore`: `*.egg-info/`, `.ruff_cache/`, `dist/`, `build/`.

- [ ] **Step 4: `make sync && make test && make lint`**

- [ ] **Step 5: Commit** `refactor: flatten package into src/ import root as zhvault project`

---

### Task 2: Split `src/cli.py` into `src/cli/` package

**Files:**
- Create: `src/cli/__init__.py`, `common.py`, `parser.py`, `cmd_*.py`
- Delete: `src/cli.py`
- Optional: `src/cli/__main__.py` → `raise SystemExit(main())`
- Test: `tests/test_cli_package.py` + existing `tests/test_cli_*.py`

- [ ] **Step 1: Parser smoke test** (status/backup/graph/search/account argv)
- [ ] **Step 2: Run smoke**
- [ ] **Step 3: Split modules; `zhvault = "cli:main"` still valid (`cli/__init__.py` exports `main`)**
- [ ] **Step 4: `make test && make lint`**
- [ ] **Step 5: Commit** `refactor: split src/cli into package modules`

---

### Task 3: Docs (AGENTS, README, cursor rules)

- [ ] Commands → `zhvault` / `make sync|test|lint`
- [ ] Explain: project name zhvault; imports are top-level from `src/`
- [ ] Deprecated script `zhihu-backup` only
- [ ] Commit `docs: zhvault project with src import root`

---

### Task 4: Verify

- [ ] `make sync && make test && make lint`
- [ ] `zhvault status --help`
- [ ] `make build` — wheel has `zhvault` script
- [ ] Confirm no `src/zhvault` or `src/zhihu_backup` directories
- [ ] Fixup commit only if needed

---

## Spec coverage

| Spec | Task |
|------|------|
| src as import root | 1 |
| No zhvault/zhihu_backup dirs under src | 1 |
| Makefile + scripts + build | 1, 4 |
| CLI split | 2 |
| Docs | 3 |
