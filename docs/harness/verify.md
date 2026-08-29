# Verify contract (agents)

Before claiming a task complete or opening a PR:

1. Run from repo root (venv activated):

   ```bash
   make gate
   ```

2. Require **exit code 0**. Both ruff and full pytest must pass.
3. Do not substitute `make test` alone, a subset of tests, or a different cwd.
4. If gate fails: fix root cause; do not use anti-bypass magic ([anti-bypass.md](./anti-bypass.md)).
5. Product behavior changes still need design under `docs/superpowers/specs/` when applicable ([AGENTS.md](../../AGENTS.md)).
6. Protocol map: [HARNESS.md](../../HARNESS.md) → python / frontend / build / config / ops under this directory.
7. Operator flows: [ops/runbook.md](./ops/runbook.md) · [ops/flows.md](./ops/flows.md) — update when backup/`--user`/deploy/gate behavior changes.

Source of truth for merge: GitHub Actions **harness-gate**, not the agent’s self-report. Gate details: [build/gate.md](./build/gate.md).
