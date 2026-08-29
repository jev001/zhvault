# zhvault C+D1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or executing-plans. Checkbox steps for tracking.

**Goal:** Migrate CLI to Typer without behavior changes; move `Main.py` to `legacy/`.

**Architecture:** Typer apps wrap existing `cmd_*` handlers via a thin context/namespace; packaging entry `cli:main` unchanged.

**Tech Stack:** Typer, existing pytest, Makefile.

## Global Constraints

- No async/httpx/storage redesign.
- Flags, exit codes, JSON events, account danger gates unchanged.
- `src/` import root; no `src/zhvault` directory.
- Commit per task; full pytest green.

---

### Task 1: Add Typer + migrate CLI surface

**Files:**
- Modify: `pyproject.toml` (add `typer`)
- Modify/rewrite: `src/cli/parser.py` → Typer app factory (or `src/cli/app.py` + thin parser re-export)
- Modify: `src/cli/__init__.py` `main()` to run Typer
- Modify: `tests/test_cli_*.py`, `tests/test_cli_package.py`, `tests/test_cli_entry.py` for Typer/CliRunner
- Keep: `cmd_*.py` handlers largely intact (accept Namespace-like object)

**Approach:**
- Create `cli.app:app` Typer root.
- Each command declares options matching current argparse defaults.
- Handler: `ns = SimpleNamespace(**kwargs); return cmd_foo(ns)` (or set attributes cmds already read).
- If cmds use `args.json`, `args.data_dir`, etc., Typer options must use same dest names.
- Remove argparse `build_parser` **or** implement `build_parser()` that returns a shim only if tests still need it — prefer updating tests to CliRunner.

- [ ] **Step 1:** Add failing/adjusted test using `typer.testing.CliRunner` invoking `status --help` exit 0
- [ ] **Step 2:** Add typer dep; implement Typer app mirroring all subcommands in current `parser.py`
- [ ] **Step 3:** Wire `main(argv=None)` → `app(argv)` / `typer.main.get_command`
- [ ] **Step 4:** Update all CLI tests; `make test` green
- [ ] **Step 5:** Commit `refactor: migrate zhvault CLI from argparse to Typer`

---

### Task 2: D1 legacy Main.py + doc scrub

**Files:**
- Move: `Main.py` → `legacy/Main.py` (+ `legacy/README.md` one paragraph)
- Modify: `README.md`, `AGENTS.md` if they still reference root Main.py as runnable
- Grep scrub user-facing leftovers

- [ ] **Step 1:** `git mv Main.py legacy/Main.py`; add `legacy/README.md`
- [ ] **Step 2:** Update docs
- [ ] **Step 3:** `make test`
- [ ] **Step 4:** Commit `chore: quarantine legacy Main.py`

---

### Task 3: Verify

- [ ] `zhvault --help`, `zhvault account apply --help` show Typer help
- [ ] Full pytest; account gate tests still pass
- [ ] No root `Main.py`
- [ ] Fixup commit if needed
