# Harness Engineering — zhvault

Agent / vibe-coding **constraint surface** for this repo. Not a runtime library.

## Protocol taxonomy

| Bucket | Path | Role |
|--------|------|------|
| **Python** | [docs/harness/python/invariants.md](docs/harness/python/invariants.md) | StorageEngine, mutate, `src/` import root, filenames |
| **Frontend** | [docs/harness/frontend/README.md](docs/harness/frontend/README.md) | Stub — no UI; do not invent a frontend stack |
| **Build** | [docs/harness/build/gate.md](docs/harness/build/gate.md) | `make gate`, pre-commit, CI `harness-gate` |
| **Config** | [docs/harness/config/inventory.md](docs/harness/config/inventory.md) | Where tool files live (root) and why |

Shared:

- [docs/harness/anti-bypass.md](docs/harness/anti-bypass.md)
- [docs/harness/verify.md](docs/harness/verify.md)
- [AGENTS.md](AGENTS.md) · [docs/agent-runbook.md](docs/agent-runbook.md) · `.cursor/rules/`

## Layers

1. **Instructions** — this file + taxonomy above
2. **Mechanical green gate** — `make gate` (ruff + full pytest); pre-commit; GitHub Actions `harness-gate`
3. **Invariants** — architecture tests in `tests/test_harness_invariants.py`

## Green gate (required)

```bash
make gate    # ONLY declared local green: ruff check src && pytest
```

Details: [docs/harness/build/gate.md](docs/harness/build/gate.md).

## Anti-bypass

AI products **must not** magic past the gate. See [docs/harness/anti-bypass.md](docs/harness/anti-bypass.md).

Short list: no `git commit --no-verify`; no fake/empty tests; no gutting `ruff.toml` / deleting harness tests or CI; no claiming green without running `make gate`.
