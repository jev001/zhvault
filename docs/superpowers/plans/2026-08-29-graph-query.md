# Graph Query (Phase 1a) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add offline `graph query` — BFS over derived + persisted edges with `--from`, `--depth`, `--kind` — no new dependencies.

**Architecture:** Reuse `derive_content_edges` + `list_graph_edges` (same merge/dedup as `rebuild_graph`). Query builds an adjacency list in memory and BFS from `--from`. CLI nests under existing `graph` subcommand.

**Tech Stack:** Python 3.10+, existing `zhihu_backup.graph` / `StorageEngine` / argparse CLI.

**Spec:** [docs/superpowers/specs/2026-08-29-graph-vector-indexes-design.md](../specs/2026-08-29-graph-vector-indexes-design.md) Phase 1a only. **Out of this plan:** Kuzu (1b), vector search (Phase 2 — separate plan).

## Global Constraints

- Persist state only via StorageEngine; indexes are derived.
- Node ids = meta keys (`user:…`, `answer:…`, …).
- Query must not mutate `graph_edges` or call Zhihu APIs.
- Prefer computing edges from engine (not trusting stale `graph.json` alone).
- No new package dependencies for Phase 1a.
- Agent CLI: `--json` on stdout; logs on stderr.

## File map

| Path | Responsibility |
|------|----------------|
| `zhihu_backup/graph.py` | `load_unified_edges`, `query_graph` (BFS) |
| `zhihu_backup/cli.py` | `graph query` subcommand |
| `tests/test_graph_query.py` | BFS + kind filter + depth |
| `AGENTS.md` | Document `graph query` |

---

### Task 1: `query_graph` core (TDD)

**Files:**
- Modify: `zhihu_backup/graph.py`
- Test: `tests/test_graph_query.py`

**Interfaces:**
- Consumes: `derive_content_edges`, `list_items`, `list_membership`, `list_graph_edges`, dedup rank from `rebuild_graph`
- Produces:

```python
def load_unified_edge_rows(engine: StorageEngine) -> list[dict[str, str]]:
    """Same derived+persisted merge as rebuild (manual > api > derived)."""

def query_graph(
    engine: StorageEngine,
    *,
    start: str,
    depth: int = 1,
    kinds: Optional[set[str]] = None,
) -> dict[str, Any]:
    """
    BFS along directed edges where edge['kind'] in kinds (or all if kinds is None).
    Returns {"start", "depth", "kinds", "nodes": [...], "edges": [...]} for the subgraph reached.
    """
```

- [ ] **Step 1: Write failing tests**

```python
# tests/test_graph_query.py
from pathlib import Path
from zhihu_backup.models import GraphEdge, ItemRecord
from zhihu_backup.storage.sqlite_engine import SqliteEngine
from zhihu_backup.graph import query_graph


def _seed(eng: SqliteEngine) -> None:
    eng.upsert_item(ItemRecord(key="question:1", item_type="question", zhihu_id="1", title="Q"))
    eng.upsert_item(
        ItemRecord(
            key="answer:1:2",
            item_type="answer",
            zhihu_id="2",
            title="A",
            extra={"parent_id": "1", "question_id": "1"},
        )
    )
    eng.upsert_graph_edge(
        GraphEdge(
            from_id="user:me",
            to_id="user:friend",
            kind="follows",
            origin="api",
            seen_at="2026-01-01T00:00:00Z",
        )
    )
    eng.upsert_graph_edge(
        GraphEdge(
            from_id="user:friend",
            to_id="user:other",
            kind="follows",
            origin="manual",
            seen_at="2026-01-01T00:00:00Z",
        )
    )


def test_query_depth_1_follows(tmp_path: Path):
    eng = SqliteEngine(tmp_path / "t.db")
    _seed(eng)
    out = query_graph(eng, start="user:me", depth=1, kinds={"follows"})
    ids = {n["id"] for n in out["nodes"]}
    assert ids == {"user:me", "user:friend"}
    eng.close()


def test_query_depth_2_follows(tmp_path: Path):
    eng = SqliteEngine(tmp_path / "t.db")
    _seed(eng)
    out = query_graph(eng, start="user:me", depth=2, kinds={"follows"})
    ids = {n["id"] for n in out["nodes"]}
    assert "user:other" in ids
    eng.close()


def test_query_answers_kind(tmp_path: Path):
    eng = SqliteEngine(tmp_path / "t.db")
    _seed(eng)
    out = query_graph(eng, start="answer:1:2", depth=1, kinds={"answers"})
    assert any(e["to"] == "question:1" for e in out["edges"])
    eng.close()
```

- [ ] **Step 2: Run — expect fail**

`pytest tests/test_graph_query.py -v` → FAIL (`query_graph` missing)

- [ ] **Step 3: Implement in `graph.py`**

Extract merge logic from `rebuild_graph` into `load_unified_edge_rows(engine)` used by both rebuild and query (DRY — do not copy-paste rank dict).

BFS:

```python
from collections import deque

def query_graph(engine, *, start: str, depth: int = 1, kinds: Optional[set[str]] = None) -> dict[str, Any]:
    rows = load_unified_edge_rows(engine)
    if kinds is not None:
        rows = [e for e in rows if e["kind"] in kinds]
    adj: dict[str, list[dict[str, str]]] = {}
    for e in rows:
        adj.setdefault(e["from"], []).append(e)
    seen_nodes = {start}
    seen_edges: list[dict[str, str]] = []
    q: deque[tuple[str, int]] = deque([(start, 0)])
    while q:
        node, d = q.popleft()
        if d >= depth:
            continue
        for e in adj.get(node, []):
            seen_edges.append(e)
            nxt = e["to"]
            if nxt not in seen_nodes:
                seen_nodes.add(nxt)
                q.append((nxt, d + 1))
    # Build minimal node stubs from ids (+ titles from list_items when present)
    items = {i.key: i for i in engine.list_items()}
    nodes = []
    for nid in sorted(seen_nodes):
        if nid in items:
            nodes.append(_node_from_item(items[nid]))
        else:
            typ = nid.split(":", 1)[0] if ":" in nid else "unknown"
            nodes.append(_stub(nid, typ))
    return {
        "start": start,
        "depth": depth,
        "kinds": sorted(kinds) if kinds is not None else None,
        "nodes": nodes,
        "edges": seen_edges,
    }
```

Refactor `rebuild_graph` to call `load_unified_edge_rows` so behavior stays identical; re-run `tests/test_graph_rebuild.py`.

- [ ] **Step 4: Tests pass**

`pytest tests/test_graph_query.py tests/test_graph_rebuild.py -v`

- [ ] **Step 5: Commit**

```bash
git add zhihu_backup/graph.py tests/test_graph_query.py
git commit -m "$(cat <<'EOF'
feat: add in-process graph query BFS over unified edges

EOF
)"
```

---

### Task 2: CLI `graph query` + AGENTS

**Files:**
- Modify: `zhihu_backup/cli.py`, `AGENTS.md`
- Test: extend `tests/test_cli_graph_max_depth.py` or add `tests/test_cli_graph_query.py`

**Interfaces:**
- `python -m zhihu_backup graph query --from KEY [--depth N] [--kind K]... --json`

- [ ] **Step 1: Failing CLI test**

```python
def test_graph_query_cli_json(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    # seed engine under data/meta/sqlite like other CLI tests
    ...
    rc = main(["graph", "query", "--from", "user:me", "--depth", "1", "--kind", "follows", "--json", "--data-dir", str(tmp_path / "data")])
    assert rc == 0
    # parse stdout last JSON object / single object with event summary or raw graph
```

Match existing CLI JSON style: either print the query result dict directly or `{"event":"summary", ...}`. Prefer printing the query result as one JSON object (jq-friendly).

- [ ] **Step 2: Wire argparse**

Under `graph` subparsers, add `query` with:
- `--from` required
- `--depth` type=int default 1
- `--kind` action=append default None → pass as set or None for all

`cmd_graph_query`: open engine, call `query_graph`, print JSON if `--json` else human summary (node count + edge count).

- [ ] **Step 3: Update AGENTS.md** Commands + Verify bullet for `graph query --depth 2`

- [ ] **Step 4: Commit**

```bash
git commit -m "$(cat <<'EOF'
feat: expose graph query CLI and document it

EOF
)"
```

---

## Spec coverage (Phase 1a)

| Requirement | Task |
|-------------|------|
| Offline BFS query | 1 |
| kind + depth filters | 1 |
| Compute from engine not stale JSON alone | 1 (`load_unified_edge_rows`) |
| CLI + docs | 2 |
| No new deps / no API / no edge mutation | both |

## Next plan

After this ships: [2026-08-29-vector-search.md](./2026-08-29-vector-search.md) (Phase 2 VectorStore + optional Chroma).
