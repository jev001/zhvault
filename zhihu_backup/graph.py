from __future__ import annotations

import json
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
    nodes, derived = derive_content_edges(items, membership)
    persisted = engine.list_graph_edges()
    for e in persisted:
        nodes.setdefault(e.from_id, _stub(e.from_id, e.from_id.split(":", 1)[0]))
        nodes.setdefault(e.to_id, _stub(e.to_id, e.to_id.split(":", 1)[0]))
    edge_rows = derived + [
        {"from": e.from_id, "to": e.to_id, "kind": e.kind, "origin": e.origin}
        for e in persisted
    ]
    # Dedup by (from,to,kind): prefer manual > api > derived
    rank = {"manual": 3, "api": 2, "derived": 1}
    best: dict[tuple[str, str, str], dict[str, str]] = {}
    for row in edge_rows:
        k = (row["from"], row["to"], row["kind"])
        if k not in best or rank.get(row["origin"], 0) >= rank.get(best[k]["origin"], 0):
            best[k] = row
    out = {
        "version": 1,
        "ego": ego,
        "max_depth_requested": max_depth_requested,
        "max_depth_applied": 1,
        "generated_at": _now(),
        "nodes": sorted(nodes.values(), key=lambda n: n["id"]),
        "edges": list(best.values()),
    }
    meta_dir = Path(meta_dir)
    meta_dir.mkdir(parents=True, exist_ok=True)
    (meta_dir / "graph.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    _refresh_people_wikilinks(contents_root, out["edges"], ego)
    return out
