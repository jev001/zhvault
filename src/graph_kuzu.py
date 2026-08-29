from __future__ import annotations

import shutil
from collections import deque
from pathlib import Path
from typing import Any

from graph import load_unified_edge_rows
from storage.base import StorageEngine


class KuzuBackendError(RuntimeError):
    """Raised when the kuzu extra is missing or the DB cannot be used."""


def _require_kuzu():
    try:
        import kuzu
    except ImportError as exc:
        raise KuzuBackendError(
            "kuzu backend requires kuzu. "
            "Install with: pip install 'zhvault[kuzu]'"
        ) from exc
    return kuzu


def _close(obj: Any) -> None:
    close = getattr(obj, "close", None)
    if callable(close):
        close()


def _reset_db_path(db_path: Path) -> None:
    if db_path.is_dir():
        shutil.rmtree(db_path)
    elif db_path.exists():
        db_path.unlink()
    db_path.parent.mkdir(parents=True, exist_ok=True)


def _stub_node(nid: str) -> dict[str, Any]:
    typ = nid.split(":", 1)[0] if ":" in nid else "unknown"
    return {"id": nid, "type": typ, "title": "", "url": "", "path": ""}


def _exec(conn: Any, query: str, params: dict[str, Any] | None = None) -> Any:
    result = conn.execute(query, params) if params is not None else conn.execute(query)
    return result


def _consume(result: Any) -> None:
    if result is None:
        return
    get_all = getattr(result, "get_all", None)
    if callable(get_all):
        get_all()
    elif hasattr(result, "has_next"):
        while result.has_next():
            result.get_next()
    _close(result)


def _fetch_rows(result: Any) -> list[list[Any]]:
    rows: list[list[Any]] = []
    if result is None:
        return rows
    if hasattr(result, "has_next"):
        while result.has_next():
            rows.append(result.get_next())
    _close(result)
    return rows


def _node_ids(engine: StorageEngine, rows: list[dict[str, str]]) -> set[str]:
    ids = {rec.key for rec in engine.list_items()}
    for e in rows:
        ids.add(e["from"])
        ids.add(e["to"])
    return ids


def sync_to_kuzu(engine: StorageEngine, db_path: Path) -> dict[str, Any]:
    """Overwrite db_path with Node + LINK tables from unified graph edges."""
    kuzu = _require_kuzu()
    db_path = Path(db_path)
    rows = load_unified_edge_rows(engine)
    node_ids = _node_ids(engine, rows)
    _reset_db_path(db_path)
    db = kuzu.Database(str(db_path))
    conn = kuzu.Connection(db)
    try:
        _consume(_exec(conn, "CREATE NODE TABLE Node(id STRING, PRIMARY KEY (id))"))
        _consume(
            _exec(
                conn,
                "CREATE REL TABLE LINK(FROM Node TO Node, kind STRING, origin STRING)",
            )
        )
        for nid in node_ids:
            _consume(_exec(conn, "CREATE (n:Node {id: $id})", {"id": nid}))
        for e in rows:
            _consume(
                _exec(
                    conn,
                    "MATCH (a:Node {id: $frm}), (b:Node {id: $to}) "
                    "CREATE (a)-[:LINK {kind: $kind, origin: $origin}]->(b)",
                    {
                        "frm": e["from"],
                        "to": e["to"],
                        "kind": e["kind"],
                        "origin": e.get("origin", ""),
                    },
                )
            )
    finally:
        _close(conn)
        _close(db)
    return {"nodes": len(node_ids), "edges": len(rows), "path": str(db_path)}


def query_kuzu(
    db_path: Path,
    *,
    start: str,
    depth: int,
    kinds: set[str] | None = None,
) -> dict[str, Any]:
    """BFS over Kuzu LINK edges; same return shape as query_graph."""
    kuzu = _require_kuzu()
    db_path = Path(db_path)
    db = kuzu.Database(str(db_path), read_only=True)
    conn = kuzu.Connection(db)
    try:
        result = _exec(
            conn,
            "MATCH (a:Node)-[r:LINK]->(b:Node) RETURN a.id, b.id, r.kind, r.origin",
        )
        raw = _fetch_rows(result)
    finally:
        _close(conn)
        _close(db)
    rows: list[dict[str, str]] = []
    for frm, to, kind, origin in raw:
        if kinds is not None and kind not in kinds:
            continue
        rows.append(
            {
                "from": str(frm),
                "to": str(to),
                "kind": str(kind),
                "origin": "" if origin is None else str(origin),
            }
        )
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
    return {
        "start": start,
        "depth": depth,
        "kinds": sorted(kinds) if kinds is not None else None,
        "nodes": [_stub_node(nid) for nid in sorted(seen_nodes)],
        "edges": seen_edges,
    }
