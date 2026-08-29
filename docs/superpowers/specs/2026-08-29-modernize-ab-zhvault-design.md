# Modernize A+B + zhvault project — Design

**Date:** 2026-08-29  
**Status:** Approved (amended: `src/` as import root; no `src/zhvault` or `src/zhihu_backup`)  
**Follow-ups:** C (Typer), D (async / Main.py) — out of scope

## Goal

1. **Project / CLI name:** `zhvault` (PyPI name + console script). **Not** used as a directory under `src/`.
2. **Code root:** `src/` is the setuptools import root (`package-dir "" = "src"`). Top-level imports are `cli`, `storage`, `pipeline`, …
3. **A — Tooling:** ruff, `dev` extra, simple **Makefile**, installable **`zhvault`** command via `[project.scripts]`.
4. **B — CLI split:** monolith → `src/cli/` package; behavior unchanged.

## Non-goals

- Typer/async/deep rewrite; deleting `Main.py`
- Directory named `zhvault` or `zhihu_backup` under `src/`
- Keeping an importable `zhihu_backup` package (only optional deprecated **script** alias)

## Layout

```
src/                      # import root (not a package name "src")
  __init__.py             # empty or omit if find discovers only subpackages — prefer empty namespace via packages only
  cli/
    __init__.py           # main, build_parser
    common.py
    parser.py
    cmd_auth.py
    cmd_backup.py
    cmd_graph.py
    cmd_search.py
    cmd_account.py
  storage/
  sources/
  writers/
  search/
  mutate/
  auth.py
  models.py
  pipeline.py
  http_client.py
  graph.py
  graph_kuzu.py
  parse.py
  __main__.py             # python -m cli  OR project uses only zhvault script — prefer entry via script; optional `python -m cli`
tests/
pyproject.toml
Makefile
README.md
AGENTS.md
Main.py                   # legacy reference (unchanged this round)
```

**Import style:** `from storage import open_engine`, `from cli import main`, `from mutate.plan import build_plan`.

**No** `import zhvault`. Project name is documentation / distribution / CLI only.

## Packaging

```toml
[project]
name = "zhvault"

[project.scripts]
zhvault = "cli:main"
zhihu-backup = "cli:main"   # deprecated alias only; no zhihu_backup package

[tool.setuptools.package-dir]
"" = "src"

[tool.setuptools.packages.find]
where = ["src"]
```

After `make sync` / editable install, shell command **`zhvault`** works.  
`python -m cli …` works if `cli` is a package with `__main__` or via `cli.__main__`; document primary UX as `zhvault`.

## Makefile (simple)

| Target | Action |
|--------|--------|
| `help` | default |
| `sync` / `install` | `pip install -e ".[dev]"` |
| `test` | `pytest` |
| `lint` | `ruff check src tests` |
| `fmt` | `ruff check --fix src tests` |
| `build` | `python -m build` |
| `zhvault` | `zhvault $(ARGS)` |

## A — Scaffolding

- `dev`: pytest, ruff, build
- gitignore: `*.egg-info/`, `.ruff_cache/`, `dist/`, `build/`
- ruff: py310, line-length 100, `src = ["src"]`
- Stub/remove `requirements.txt` → point at pyproject
- No mypy; no runtime dep changes

## B — CLI

Split former `cli.py` into `src/cli/*`. Entry `cli:main`. Tests: `from cli import build_parser, main`.

## Migration from today

1. Move `zhihu_backup/*` → `src/` (flatten: contents of package become top-level under `src/`).
2. Rewrite imports `zhihu_backup.X` → `X` (or `from storage…`).
3. Delete old package dir; do **not** create `src/zhvault` or `src/zhihu_backup`.
4. Tests update imports; docs use `zhvault` CLI + `make`.

## Verify

- `make sync && make test && make lint`
- `zhvault status --help`
- `make build` wheel installs script `zhvault`
- No `src/zhvault`, no `src/zhihu_backup`
- Full pytest green; flags/behavior unchanged
