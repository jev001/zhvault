from __future__ import annotations

import json
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from zhihu_backup.models import GraphEdge, ItemRecord
from zhihu_backup.storage.base import StorageEngine

PEOPLE_SCOPED = {
    "asked_questions": "asked",
    "followed_questions": "follows_question",
    "votes": "voted",
    "pins": "pinned",
}


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _node_from_item(rec: ItemRecord) -> dict[str, Any]:
    return {
        "id": rec.key,
        "type": rec.item_type,
        "title": rec.title or "",
        "url": rec.url or "",
        "path": rec.path or "",
    }


def _stub(node_id: str, type_: str, title: str = "") -> dict[str, Any]:
    return {"id": node_id, "type": type_, "title": title, "url": "", "path": ""}


def derive_content_edges(
    items: list[ItemRecord], membership: list[dict[str, str]]
) -> tuple[dict[str, dict[str, Any]], list[dict[str, str]]]:
    nodes: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, str]] = []
    by_key = {i.key: i for i in items}
    for rec in items:
        nodes[rec.key] = _node_from_item(rec)
        parent = (rec.extra or {}).get("parent_id") or (rec.extra or {}).get("question_id")
        if rec.item_type == "answer" and parent:
            qkey = f"question:{parent}"
            nodes.setdefault(qkey, _stub(qkey, "question"))
            edges.append(
                {"from": rec.key, "to": qkey, "kind": "answers", "origin": "derived"}
            )
        if rec.item_type == "article":
            col = (rec.extra or {}).get("column_id") or (rec.extra or {}).get("parent_id")
            if col:
                ckey = f"column:{col}"
                nodes.setdefault(ckey, _stub(ckey, "column"))
                edges.append(
                    {"from": rec.key, "to": ckey, "kind": "in_column", "origin": "derived"}
                )
    for m in membership:
        key, kind, oid = m["key"], m["owner_kind"], m["owner_id"]
        if kind in PEOPLE_SCOPED and key in by_key:
            ukey = f"user:{oid}"
            nodes.setdefault(ukey, _stub(ukey, "user", oid))
            edges.append(
                {
                    "from": ukey,
                    "to": key,
                    "kind": PEOPLE_SCOPED[kind],
                    "origin": "derived",
                }
            )
        elif kind == "collections" and key in by_key:
            ckey = f"collection:{oid}"
            nodes.setdefault(ckey, _stub(ckey, "collection", oid))
            edges.append(
                {"from": ckey, "to": key, "kind": "collected", "origin": "derived"}
            )
    return nodes, edges


def _split_frontmatter(text: str) -> tuple[str, str]:
    if not text.startswith("---"):
        return "", text
    end = text.find("\n---", 3)
    if end < 0:
        return "", text
    fm = text[: end + 4]
    body = text[end + 4 :].lstrip("\n")
    return fm + "\n", body


def _strip_link_sections(body: str) -> str:
    lines = body.splitlines()
    out: list[str] = []
    skipping = False
    for line in lines:
        if line.strip() in ("## Following", "## Followers"):
            skipping = True
            continue
        if skipping and line.startswith("## "):
            skipping = False
        if not skipping:
            out.append(line)
    return "\n".join(out).rstrip() + ("\n" if out else "")


def _section(title: str, tokens: list[str]) -> str:
    lines = [f"## {title}", ""]
    for t in sorted(set(tokens)):
        lines.append(f"- [[{t}]]")
    lines.append("")
    return "\n".join(lines)


def _refresh_people_wikilinks(
    contents_root: Path, edges: list[dict[str, str]], ego: Optional[str]
) -> None:
    people_dir = Path(contents_root) / "people"
    people_dir.mkdir(parents=True, exist_ok=True)
    follows = [e for e in edges if e.get("kind") == "follows"]
    following: dict[str, list[str]] = {}
    followers: dict[str, list[str]] = {}
    for e in follows:
        frm, to = e["from"], e["to"]
        if frm.startswith("user:") and to.startswith("user:"):
            following.setdefault(frm[5:], []).append(to[5:])
            followers.setdefault(to[5:], []).append(frm[5:])
    tokens = set(following) | set(followers)
    if ego:
        tokens.add(ego)
    for token in tokens:
        path = people_dir / f"{token}.md"
        if path.exists():
            raw = path.read_text(encoding="utf-8")
            fm, body = _split_frontmatter(raw)
            body = _strip_link_sections(body)
        else:
            fm = (
                "---\n"
                f"title: {token}\n"
                "type: user\n"
                f"url_token: {token}\n"
                "---\n"
            )
            body = ""
        text = (
            fm
            + ("\n" if not fm.endswith("\n") else "")
            + body
            + ("\n" if body and not body.endswith("\n") else "")
            + _section("Following", following.get(token, []))
            + _section("Followers", followers.get(token, []))
        )
        path.write_text(text, encoding="utf-8")
    if ego:
        idx = people_dir / f"_index_{ego}.md"
        idx.write_text(
            "---\n"
            f"title: Social index ({ego})\n"
            "type: social_index\n"
            f"ego: {ego}\n"
            "---\n\n"
            + _section("Following", following.get(ego, []))
            + _section("Followers", followers.get(ego, [])),
            encoding="utf-8",
        )


_ORIGIN_RANK = {"manual": 3, "api": 2, "derived": 1}


def load_unified_edge_rows(engine: StorageEngine) -> list[dict[str, str]]:
    """Same derived+persisted merge as rebuild (manual > api > derived)."""
    items = engine.list_items()
    membership = engine.list_membership()
    _, derived = derive_content_edges(items, membership)
    persisted = engine.list_graph_edges()
    edge_rows = derived + [
        {"from": e.from_id, "to": e.to_id, "kind": e.kind, "origin": e.origin}
        for e in persisted
    ]
    best: dict[tuple[str, str, str], dict[str, str]] = {}
    for row in edge_rows:
        k = (row["from"], row["to"], row["kind"])
        if k not in best or _ORIGIN_RANK.get(row["origin"], 0) >= _ORIGIN_RANK.get(
            best[k]["origin"], 0
        ):
            best[k] = row
    return list(best.values())


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


def rebuild_graph(
    engine: StorageEngine,
    contents_root: Path,
    meta_dir: Path,
    *,
    ego: Optional[str] = None,
    max_depth_requested: int = 1,
) -> dict[str, Any]:
    items = engine.list_items()
    membership = engine.list_membership()
    nodes, _ = derive_content_edges(items, membership)
    persisted = engine.list_graph_edges()
    for e in persisted:
        nodes.setdefault(e.from_id, _stub(e.from_id, e.from_id.split(":", 1)[0]))
        nodes.setdefault(e.to_id, _stub(e.to_id, e.to_id.split(":", 1)[0]))
    out = {
        "version": 1,
        "ego": ego,
        "max_depth_requested": max_depth_requested,
        "max_depth_applied": 1,
        "generated_at": _now(),
        "nodes": sorted(nodes.values(), key=lambda n: n["id"]),
        "edges": load_unified_edge_rows(engine),
    }
    meta_dir = Path(meta_dir)
    meta_dir.mkdir(parents=True, exist_ok=True)
    (meta_dir / "graph.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    _refresh_people_wikilinks(contents_root, out["edges"], ego)
    return out
