# Build / green gate

Local and remote mechanical gate. Tool files stay at **repo root** (ecosystem defaults); this doc is the agent protocol map.

## Required local green

```bash
make gate    # ruff check src && pytest
```

Defined in root [`Makefile`](../../../Makefile) (`gate` target). Do not treat `make test` alone as sufficient for completion.

## Pre-commit

- Config: [`.pre-commit-config.yaml`](../../../.pre-commit-config.yaml) (must stay at git root)
- Once per clone: `pre-commit install` (after `make sync`)
- Agents must not use `git commit --no-verify` to skip ([anti-bypass](../anti-bypass.md))

## CI

- Workflow: [`.github/workflows/harness-gate.yml`](../../../.github/workflows/harness-gate.yml)
- Runs `pip install -e ".[dev,chroma,kuzu]"` then `make gate` on push/PR to `master`
- Human one-time: enable branch protection → require status check **harness-gate**

## Related

- Completion contract: [verify.md](../verify.md)
- Config inventory: [config/inventory.md](../config/inventory.md)
