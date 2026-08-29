# Config inventory (agent protocol)

Where tooling lives and **why** it stays at the repo root. Agents must not relocate these without a design change that also updates every consumer.

| File | Bucket | Why at root |
|------|--------|-------------|
| `pyproject.toml` | python / packaging | setuptools / uv / pip expect project root |
| `uv.lock` | python / packaging | uv lockfile (committed) |
| `ruff.toml` | python / lint | default discovery; gate + invariants assert path |
| `requirements.txt` | python | thin pointer to `uv sync` / `pip install -e ".[dev]"` |
| `.pre-commit-config.yaml` | build | pre-commit only loads from git root |
| `Makefile` | build | conventional entry; `make gate` / `make docs-arch` |
| `.github/workflows/harness-gate.yml` | build | GitHub Actions convention |
| `HARNESS.md` / `AGENTS.md` | agent protocol | agent entrypoints |
| `.cursor/hooks.json` | build / ops | Cursor harness hooks (ops context + deny `--no-verify`) |
| `scripts/gen_architecture_docs.py` | ops | regenerate `docs/harness/ops/architecture.md` |

## Classified elsewhere (docs only)

- Python invariants → [python/invariants.md](../python/invariants.md)
- Build gate narrative → [build/gate.md](../build/gate.md)
- Frontend (none) → [frontend/README.md](../frontend/README.md)
- Ops flows / runbook → [ops/README.md](../ops/README.md)

Do **not** move the table’s root files into `docs/harness/` — protocol documents point at them.
