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

Source of truth for merge: GitHub Actions **harness-gate**, not the agent’s self-report.
