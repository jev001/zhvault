# Ops (confirmed system flows)

Harness **operations** surface: flowcharts + runbooks for flows already locked in product/docs.

| Doc | Purpose |
|-----|---------|
| [architecture.md](./architecture.md) | **Generated** full architecture + flowcharts (`make docs-arch`) |
| [flows.md](./flows.md) | Mermaid flowcharts (gate, backup me / `--user`, deploy runner) |
| [runbook.md](./runbook.md) | Step-by-step operator / agent commands |

Regenerate architecture map after structural `src/` changes:

```bash
make docs-arch
```

Related protocol:

- Green gate → [../build/gate.md](../build/gate.md) · [../verify.md](../verify.md)
- Anti-bypass → [../anti-bypass.md](../anti-bypass.md)
- Invariants → [../python/invariants.md](../python/invariants.md)

**Cursor hook:** project `.cursor/hooks.json` injects this map at `sessionStart` and blocks `git commit --no-verify` via `beforeShellExecution`.

Agents: when changing backup/`--user`/deploy/gate behavior, update these ops docs in the same change.
