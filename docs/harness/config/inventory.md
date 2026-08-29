# Config inventory (agent protocol)

Where tooling lives and **why** it stays at the repo root. Agents must not relocate these without a design change that also updates every consumer.

| File | Bucket | Why at root |
|------|--------|-------------|
| `pyproject.toml` | python / packaging | setuptools / uv / pip expect project root |
| `requirements.txt` | python | thin pointer to `uv sync` / `pip install -e ".[dev]"` |
| `uv.lock` | python / packaging | uv lockfile (committed) |
| `.pre-commit-config.yaml` | build | pre-commit only loads from git root |
| `Makefile` | build | conventional entry; `make gate` |
| `.github/workflows/harness-gate.yml` | build | GitHub Actions convention |
| `HARNESS.md` / `AGENTS.md` | agent protocol | agent entrypoints |

## Classified elsewhere (docs only)

- Python invariants → [python/invariants.md](../python/invariants.md)
- Build gate narrative → [build/gate.md](../build/gate.md)
- Frontend (none) → [frontend/README.md](../frontend/README.md)

Do **not** move the table’s root files into `docs/harness/` — protocol documents point at them.
