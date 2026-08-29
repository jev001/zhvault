# Harness Engineering — zhvault

Agent / vibe-coding **constraint surface** for this repo. Not a runtime library.

## Layers

1. **Instructions** — this file, [AGENTS.md](AGENTS.md), [docs/harness/](docs/harness/), `.cursor/rules/`
2. **Mechanical green gate** — `make gate` (ruff + full pytest); pre-commit; GitHub Actions `harness-gate`
3. **Invariants** — architecture tests in `src/tests/test_harness_invariants.py`

## Green gate (required)

```bash
make gate    # ONLY declared local green: ruff check src && pytest
```

Remote: `.github/workflows/harness-gate.yml` runs the same command on push/PR.
Enable GitHub branch protection → require check **harness-gate** (human one-time).

## Anti-bypass

AI products **must not** magic past the gate. See [docs/harness/anti-bypass.md](docs/harness/anti-bypass.md).

Short list: no `git commit --no-verify`; no fake/empty tests; no gutting `ruff.toml` / deleting harness tests or CI; no claiming green without running `make gate`.

## Details

- [docs/harness/invariants.md](docs/harness/invariants.md)
- [docs/harness/verify.md](docs/harness/verify.md)
- [docs/harness/anti-bypass.md](docs/harness/anti-bypass.md)
- [docs/agent-runbook.md](docs/agent-runbook.md)
