# zhvault Modernize A+B Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rename the package/CLI to `zhvault`, modernize tooling (uv/ruff/dev extra), and split the monolith CLI into `zhvault/cli/` without behavior changes; keep a deprecation shim for `zhihu_backup`.

**Architecture:** Physical move `zhihu_backup/` → `zhvault/`; thin `zhihu_backup` shim with `DeprecationWarning`; `cli.py` becomes package `zhvault/cli/` with `common`, `parser`, and `cmd_*` modules; `pyproject` entry `zhvault = "zhvault.cli:main"`.

**Tech Stack:** Python 3.10+, setuptools, argparse (unchanged), ruff, pytest, uv lockfile optional.

## Global Constraints

- Requires-python `>=3.10`; no new runtime deps; no Typer/async/Main.py deletion.
- CLI flags, exit codes, and JSON events must stay identical.
- New code/docs/tests use `zhvault`; shim warns on `import zhihu_backup`.
- Do not commit `Cookies.json` / `data/meta/**`.
- Prefer `git mv` for renames; frequent commits per task.
- Full suite must stay green (`pytest`); `ruff check zhvault tests zhihu_backup` clean or only pre-existing issues fixed if introduced by move.

---

### Task 1: Rename package to zhvault + tooling scaffold

**Files:**
- Move: `zhihu_backup/` → `zhvault/` (entire tree except create shim later)
- Modify: `pyproject.toml`, `.gitignore`, `README.md`, `requirements.txt`
- Create: `zhihu_backup/__init__.py`, `zhihu_backup/__main__.py` (shim)
- Modify: all `tests/**/*.py` imports `zhihu_backup` → `zhvault`
- Modify: any internal imports inside moved package
- Test: `tests/test_shim_zhvault.py` (new)

**Interfaces:**
- Produces: importable `zhvault`; `zhvault.cli:main` still works via temporary `zhvault/cli.py` until Task 2; shim `zhihu_backup` warns and re-exports.

- [ ] **Step 1: Write failing shim test**

```python
# tests/test_shim_zhvault.py
import warnings

def test_zhihu_backup_shim_warns():
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        import zhihu_backup  # noqa: F401
        assert any(issubclass(x.category, DeprecationWarning) for x in w)
```

- [ ] **Step 2: Run test — expect fail (no shim yet)**

```bash
pytest tests/test_shim_zhvault.py -q
```

- [ ] **Step 3: `git mv zhihu_backup zhvault` then fix imports**

```bash
git mv zhihu_backup zhvault
# Replace zhihu_backup → zhvault in zhvault/**/*.py and tests/**/*.py
# Keep logger names optional: logging.getLogger("zhvault...") preferred
```

Create shim:

```python
# zhihu_backup/__init__.py
import warnings
warnings.warn(
    "zhihu_backup is deprecated; use zhvault",
    DeprecationWarning,
    stacklevel=2,
)
from zhvault import *  # noqa: F403
from zhvault import __version__
```

```python
# zhihu_backup/__main__.py
import warnings
warnings.warn("python -m zhihu_backup is deprecated; use python -m zhvault", DeprecationWarning, stacklevel=2)
from zhvault.__main__ import main
raise SystemExit(main())
```

Ensure `zhvault/__main__.py` and `zhvault/__init__.py` keep `__version__`.

Update `pyproject.toml`:

```toml
[project]
name = "zhvault"
# ...
[project.optional-dependencies]
chroma = ["chromadb>=0.5"]
kuzu = ["kuzu>=0.4"]
search-ml = ["sentence-transformers>=3.0"]
dev = ["pytest>=8.0", "ruff>=0.6"]

[project.scripts]
zhvault = "zhvault.cli:main"
zhihu-backup = "zhvault.cli:main"  # deprecated alias

[tool.setuptools.packages.find]
include = ["zhvault*", "zhihu_backup*"]

[tool.ruff]
line-length = 100
target-version = "py310"

[tool.ruff.lint]
select = ["E", "F", "I", "UP"]
```

`.gitignore` add:

```
*.egg-info/
.ruff_cache/
```

`requirements.txt` → single comment line pointing to pyproject / `pip install -e ".[dev]"`.

README install section: `uv sync` or `pip install -e ".[dev]"` and `zhvault` commands.

- [ ] **Step 4: Reinstall editable + run shim test + full pytest**

```bash
pip install -e ".[dev]"
pytest tests/test_shim_zhvault.py tests/ -q
ruff check zhvault tests zhihu_backup
```

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "refactor: rename package to zhvault with deprecation shim"
```

(Exclude Cookies.json / data secrets; leave egg-info untracked via gitignore.)

---

### Task 2: Split CLI into zhvault/cli/ package

**Files:**
- Create: `zhvault/cli/__init__.py`, `common.py`, `parser.py`, `cmd_auth.py`, `cmd_backup.py`, `cmd_graph.py`, `cmd_search.py`, `cmd_account.py`
- Delete: `zhvault/cli.py` (after move)
- Modify: `tests/test_cli_*.py` if imports need `from zhvault.cli import build_parser, main` (should still work)
- Test: existing CLI tests + optional `tests/test_cli_package.py`

**Interfaces:**
- Consumes: all current `cmd_*` functions and helpers from former `cli.py`
- Produces: `zhvault.cli.main`, `zhvault.cli.build_parser` identical behavior

- [ ] **Step 1: Add smoke test for parser subcommands**

```python
# tests/test_cli_package.py
from zhvault.cli import build_parser

def test_build_parser_has_core_commands():
    p = build_parser()
    # ensure subparsers exist by parsing known argv prefixes
    for argv in (
        ["status"],
        ["backup", "--source", "collection"],
        ["graph", "rebuild"],
        ["search", "index"],
        ["account", "plan", "--mode", "prune", "--source", "following"],
    ):
        args = p.parse_args(argv)
        assert callable(args.func)
```

- [ ] **Step 2: Run — may pass already against monolith; keep as regression**

- [ ] **Step 3: Split modules**

Move shared helpers to `zhvault/cli/common.py` (`_setup_logging`, `_data_paths`, `_json_print`, `_cmd_fail`, `ME_URL`, `log`, resolve helpers used by multiple cmds).

Move command functions into `cmd_*.py`. Move `build_parser` into `parser.py` importing cmds.

`zhvault/cli/__init__.py`:

```python
from zhvault.cli.parser import build_parser

def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    from zhvault.cli.common import setup_logging
    # same logging + args.func(args) as today
    ...
```

Ensure `from zhvault.cli import main, build_parser` works. Remove old `zhvault/cli.py` so the package wins.

- [ ] **Step 4: Full pytest + ruff**

```bash
pytest tests/ -q
ruff check zhvault tests zhihu_backup
```

- [ ] **Step 5: Commit**

```bash
git commit -m "refactor: split zhvault CLI into cli package modules"
```

---

### Task 3: Docs + AGENTS + agent rules for zhvault

**Files:**
- Modify: `AGENTS.md`, `README.md`, `.cursor/rules/zhihu-backup.mdc` (if exists — rename or update content)
- Modify: design/plan already written; optional one-line in `docs/agent-runbook.md`
- Test: none beyond grep sanity

- [ ] **Step 1: Update AGENTS.md commands** to `python -m zhvault ...` and note shim deprecated
- [ ] **Step 2: Update README** brand/commands to zhvault
- [ ] **Step 3: Update cursor rule / runbook** package paths
- [ ] **Step 4: `rg 'zhihu_backup' --glob '!docs/superpowers/**' --glob '!.git/**'`** — only shim + intentional deprecation mentions remain outside historical specs
- [ ] **Step 5: Commit**

```bash
git commit -m "docs: switch agent and user docs to zhvault"
```

---

### Task 4: Final verification

- [ ] **Step 1:** `pip install -e ".[dev]"` && `python -m zhvault status --help`
- [ ] **Step 2:** `pytest tests/ -q` → all pass
- [ ] **Step 3:** `ruff check zhvault tests zhihu_backup`
- [ ] **Step 4:** Confirm `python -c "import zhihu_backup"` emits DeprecationWarning
- [ ] **Step 5:** No commit unless fixes needed; if fixes, commit `fix: zhvault rename fallout`

---

## Spec coverage

| Spec item | Task |
|-----------|------|
| Rename to zhvault | 1 |
| Deprecation shim | 1 |
| ruff / dev / gitignore / README install | 1, 3 |
| CLI split | 2 |
| Docs AGENTS | 3 |
| Full verify | 4 |
| C/D excluded | — |
