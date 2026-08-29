# Anti-bypass (AI / vibe coding)

The green gate is `make gate` locally and **harness-gate** CI remotely (see [build/gate.md](./build/gate.md)). Agents with repo write access can always edit code; bypass must stay **loud and reviewable**. The following **magic** moves are forbidden:

## Forbidden

1. **`git commit --no-verify`** (or equivalent) to skip pre-commit / hooks.
2. **`--no-gpg-sign` / hook skips** used specifically to avoid the harness.
3. **Fake green tests** — empty tests, `assert True` placeholders, deleting failing tests, or marking real failures `skip` without product cause, solely to force green.
4. **Gutting the linter** — setting `lint.select` empty, ignore-all, or removing `ruff.toml` to silence `make gate`.
5. **Removing the gate** — deleting `src/tests/test_harness_invariants.py`, `.github/workflows/harness-gate.yml`, or rewriting CI to a no-op without human approval in the same change.
6. **Claiming green without evidence** — stating “tests passed” without actually running `make gate` in this repository.
7. **Self-monkeypatching the gate** in the same PR/commit set (e.g. patching pytest/ruff out) without explicit human approval.

## Not a seal

Bypass is always possible by editing the repo. Countermeasures: invariant tests fail on gutting; CI still runs on the remote; humans enable branch protection requiring **harness-gate**.

## Allowed

- Fixing real failures until `make gate` passes.
- Extending invariants with human-reviewed, real checks.
- Documented temporary skips for missing optional extras (`chroma` / `kuzu`) only when the suite already defines those markers — CI installs extras so those are not skipped away.
