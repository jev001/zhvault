# zhvault C + D1 — Typer CLI + Legacy Cleanup — Design

**Date:** 2026-08-29  
**Status:** Approved (continue after A+B)  
**Out of scope:** async pipeline, httpx rewrite, storage redesign (later D)

## Goal

1. **C:** Replace argparse with **Typer**; keep command surface, flags, exit codes, and JSON events the same for operators.
2. **D1:** Quarantine legacy `Main.py` under `legacy/`; scrub remaining user-facing `zhihu_backup` / `zhihu-backup` strings where they are not the intentional deprecated script alias.

## Non-goals

- Async / httpx migration
- Changing mutate danger gates or backup semantics
- Removing the `zhihu-backup` console-script alias (still deprecated, one more cycle)

## C — Typer

- Dependency: `typer>=0.12` (pulls click).
- Entry remains `zhvault = "cli:main"`; `main()` invokes Typer app.
- Nested apps: `auth`, `graph` (+ `edge`), `search`, `account`; top-level `status`, `backup`, `resume`.
- Prefer thin Typer wrappers that build a small namespace / kwargs and call existing `cmd_*` handlers (minimal churn).
- Tests: migrate `build_parser().parse_args(...)` to Typer `CliRunner` **or** keep `build_parser()` as a test-only adapter if cheaper; prefer CliRunner + `main` for new tests.
- Help `prog` / brand: `zhvault`.

## D1 — Legacy

- Move `Main.py` → `legacy/Main.py`; README note: historical only, not supported.
- AGENTS / rules: do not point new work at Main.py.
- Logger / error copy already mostly `zhvault`; finish stragglers in `src/` (except intentional deprecation).

## Verify

- `zhvault --help` and nested `--help` work
- Full `pytest` green
- `legacy/Main.py` exists; no root `Main.py`
- Danger account apply gates unchanged
