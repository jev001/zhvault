# Modernize A+B + Rename to zhvault — Design

**Date:** 2026-08-29  
**Status:** Approved  
**Follow-ups (out of scope):** C (Typer/Click), D (async / deep rewrite / drop Main.py)

## Goal

1. **Rename** the installable package and CLI from `zhihu_backup` / `zhihu-backup` to **`zhvault` / `zhvault`**.
2. **A — Tooling:** uv-friendly `pyproject`, `ruff`, `dev` extra, ignore egg-info noise; README install path modernized.
3. **B — Structure:** Split the ~1000-line `cli.py` into `zhvault/cli/` modules without changing CLI behavior.

## Non-goals (this iteration)

- Typer/Click migration (C)
- Async HTTP, storage redesign, deleting `Main.py` (D)
- Changing backup/mutate/graph/search semantics or flags
- Immediate hard-delete of old names (shim required)

## Rename

| Role | Old | New |
|------|-----|-----|
| Python package | `zhihu_backup` | `zhvault` |
| `python -m …` | `zhihu_backup` | `zhvault` |
| Console script | `zhihu-backup` | `zhvault` |
| PyPI / project name | `zhihu-backup` | `zhvault` |

**Deprecation shim (one cycle):**
- Keep a thin `zhihu_backup` package that re-exports `zhvault` and emits `DeprecationWarning` on import.
- Keep optional console script `zhihu-backup` → same `main` with warning once, or document as alias via shim entry.
- Tests and docs for *new* work use `zhvault` only.

## A — Scaffolding

- Keep setuptools + `pyproject.toml`; add `dev` optional deps: `ruff`, `pytest`.
- Commit `uv.lock` if present and consistent; remove or stub `requirements.txt` pointing at pyproject.
- `.gitignore`: `*.egg-info/`, `.ruff_cache/`.
- `[tool.ruff]`: target py310, line-length 100; check `zhvault` + `tests` (+ shim).
- No mypy this round. No runtime dependency changes.

## B — CLI layout

```
zhvault/
  cli/
    __init__.py       # main, build_parser re-exports
    common.py         # logging, paths, json print, fail helper
    parser.py         # build_parser()
    cmd_auth.py
    cmd_backup.py     # backup + resume
    cmd_graph.py
    cmd_search.py
    cmd_account.py
  ...                 # rest moved from zhihu_backup/
zhihu_backup/         # shim only
  __init__.py
  __main__.py         # warn + run zhvault
```

- Entry: `zhvault = "zhvault.cli:main"`.
- Behavior: identical argparse surface and exit codes.
- Verify: full `pytest`; existing CLI tests updated to `zhvault`.

## Docs

- Update `AGENTS.md`, `README.md`, `.cursor/rules` if present to say `zhvault`.
- Historical specs under `docs/superpowers/specs/` may keep old filenames; body references for *commands* should prefer `zhvault` in new/edited docs.

## Verify

- `python -m zhvault status --help` works after editable install
- `ruff check zhvault tests zhihu_backup`
- Full pytest green
- Importing `zhihu_backup` warns and still resolves `cli.main`
- No intentional flag/behavior regressions
