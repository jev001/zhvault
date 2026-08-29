# Kuzu Graph Sync (Phase 1b) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or executing-plans.

**Goal:** Optional Kuzu derived index via `graph sync --backend kuzu`; `graph query --backend auto|memory|kuzu` with 1a fallback only for `auto`.

**Architecture:** Sync writes `meta/{engine}/graph_query/kuzu/` from `load_unified_edge_rows` + items. Query uses Kuzu when requested/available; semantic parity with BFS on fixtures.

**Tech Stack:** optional `kuzu>=0.4`; existing graph.py.

**Spec:** [docs/superpowers/specs/2026-08-29-kuzu-embeddings-design.md](../specs/2026-08-29-kuzu-embeddings-design.md) Phase 1b.

**Prerequisite:** Phase 1a `query_graph` / `load_unified_edge_rows` (already on master). Prefer landing embeddings plan first if both queued; this plan is independent.

## Global Constraints

- Kuzu optional extra only; never default dependency.
- `--backend kuzu` must not silent-fallback to memory.
- `--backend auto`: Kuzu if dir exists and importable else BFS.
- Sync/query offline; no Zhihu; no mutation of `graph_edges`.
- Acceptance: same node id set as BFS for depth/kinds on synced fixture.

## File map

| Path | Role |
|------|------|
| `zhihu_backup/graph_kuzu.py` | sync_to_kuzu, query_kuzu |
| `zhihu_backup/graph.py` | keep BFS; optional thin dispatch helpers |
| `zhihu_backup/cli.py` | `graph sync`, query `--backend` |
| `pyproject.toml` | `kuzu` extra |
| `tests/test_graph_kuzu.py` | skipif no kuzu; ImportError path; parity |
| `AGENTS.md` | sync + backend flags |

---

### Task 1: sync_to_kuzu + query_kuzu

**Files:** `graph_kuzu.py`; `tests/test_graph_kuzu.py`; `pyproject.toml`

Schema (minimal): Node table `Node(id STRING, PRIMARY KEY)`; Rel `FOLLOWS` or generic `LINK(kind STRING)` between nodes — prefer single `LINK` with `kind` property for all edge kinds.

```python
def sync_to_kuzu(engine: StorageEngine, db_path: Path) -> dict: ...
def query_kuzu(db_path: Path, *, start: str, depth: int, kinds: set[str] | None) -> dict: ...
```

- [ ] **Step 1:** Tests — monkeypatch missing kuzu → error hint `zhihu-backup[kuzu]`; with kuzu: sync fixture + query depth 2 follows matches `query_graph` node ids
- [ ] **Step 2:** Implement + `kuzu = ["kuzu>=0.4"]` extra
- [ ] **Step 3:** Commit `feat: add optional Kuzu graph sync and query`

---

### Task 2: CLI graph sync + query --backend

**Files:** `cli.py`, `AGENTS.md`, CLI tests

```bash
python -m zhihu_backup graph sync --backend kuzu --json
python -m zhihu_backup graph query --from KEY --depth 2 --backend auto|memory|kuzu --json
```

`db_path = meta/{engine}/graph_query/kuzu`

- [ ] **Step 1:** CLI tests for sync missing package; query --backend memory still works; --backend kuzu without sync errors
- [ ] **Step 2:** AGENTS
- [ ] **Step 3:** Commit `feat: expose graph sync and query --backend CLI`

---

## Spec coverage

| Requirement | Task |
|-------------|------|
| sync kuzu derived index | 1 |
| query backend auto/memory/kuzu | 2 |
| optional extra + install hint | 1–2 |
| BFS parity | 1 |
