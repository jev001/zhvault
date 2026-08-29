"""Build account mutate plans from local StorageEngine inventory (no writes)."""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

from http_client import ZhihuClient
from models import ItemRecord
from mutate import endpoints
from storage.base import StorageEngine

log = logging.getLogger("mutate.plan")

SOURCE_ALIASES = {
    "following": "following",
    "followees": "following",
    "collection": "collection",
    "collections": "collection",
    "followed": "followed",
    "followed_questions": "followed",
    "followed-questions": "followed",
}

CONTENT_TYPES = {"answer", "article", "pin", "zvideo", "question"}


def parse_sources(raw: str) -> list[str]:
    parts = [p.strip() for p in (raw or "").split(",") if p.strip()]
    if not parts:
        raise ValueError("--source required (comma list: following,collection,followed)")
    out: list[str] = []
    for p in parts:
        key = SOURCE_ALIASES.get(p.lower())
        if not key:
            raise ValueError(f"unsupported mutate source {p!r}; use following|collection|followed")
        if key not in out:
            out.append(key)
    return out


def parse_map_collection(entries: list[str] | None) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for entry in entries or []:
        if "=" not in entry:
            raise ValueError(f"--map-collection expects A_id=B_id, got {entry!r}")
        a, b = entry.split("=", 1)
        a, b = a.strip(), b.strip()
        if not a or not b:
            raise ValueError(f"--map-collection expects A_id=B_id, got {entry!r}")
        mapping[a] = b
    return mapping


def fingerprint_inventory(
    *,
    mode: str,
    sources: list[str],
    limit: int | None,
    map_collection: dict[str, str],
    following: list[str],
    followed: list[str],
    collection_items: list[tuple[str, str, str]],
) -> str:
    payload = {
        "mode": mode,
        "sources": sources,
        "limit": limit,
        "map_collection": map_collection,
        "following": following,
        "followed": followed,
        "collection_items": [[a, b, c] for a, b, c in collection_items],
    }
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def fingerprint_actions(actions: list[dict[str, Any]], *, mode: str, sources: list[str], limit: int | None) -> str:
    """Legacy helper for tests; prefer fingerprint_inventory for plans."""
    payload = {
        "mode": mode,
        "sources": sources,
        "limit": limit,
        "actions": actions,
    }
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _ego_from_engine(engine: StorageEngine) -> str | None:
    edges = engine.list_graph_edges()
    from_counts: dict[str, int] = {}
    for e in edges:
        if e.kind != "follows":
            continue
        if e.from_id.startswith("user:"):
            from_counts[e.from_id] = from_counts.get(e.from_id, 0) + 1
    if from_counts:
        return max(from_counts.items(), key=lambda kv: kv[1])[0][5:]
    return None


def _following_tokens(engine: StorageEngine, ego: str) -> list[str]:
    ego_key = f"user:{ego}"
    tokens: list[str] = []
    seen: set[str] = set()
    for e in engine.list_graph_edges():
        if e.kind != "follows" or e.from_id != ego_key:
            continue
        if not e.to_id.startswith("user:"):
            continue
        tok = e.to_id[5:]
        if tok and tok not in seen:
            seen.add(tok)
            tokens.append(tok)
    return tokens


def _followed_question_ids(engine: StorageEngine) -> list[str]:
    by_key = {i.key: i for i in engine.list_items()}
    ids: list[str] = []
    seen: set[str] = set()
    for m in engine.list_membership():
        if m["owner_kind"] != "followed_questions":
            continue
        rec = by_key.get(m["key"])
        qid = None
        if rec:
            qid = (rec.extra or {}).get("question_id") or rec.zhihu_id
            if rec.item_type != "question" and (rec.extra or {}).get("question_id"):
                qid = (rec.extra or {}).get("question_id")
            elif rec.item_type == "question":
                qid = rec.zhihu_id
        if not qid and m["key"].startswith("question:"):
            qid = m["key"].split(":", 1)[1]
        if qid and str(qid) not in seen:
            seen.add(str(qid))
            ids.append(str(qid))
    return ids


def _content_type_and_id(rec: ItemRecord) -> tuple[str, str] | None:
    t = rec.item_type
    if t not in CONTENT_TYPES:
        return None
    return t, str(rec.zhihu_id)


def _collection_items(engine: StorageEngine) -> list[tuple[str, str, str]]:
    """Return list of (collection_id, content_type, content_id)."""
    by_key = {i.key: i for i in engine.list_items()}
    out: list[tuple[str, str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for m in engine.list_membership():
        if m["owner_kind"] != "collections":
            continue
        rec = by_key.get(m["key"])
        if not rec:
            continue
        pair = _content_type_and_id(rec)
        if not pair:
            continue
        row = (str(m["owner_id"]), pair[0], pair[1])
        if row not in seen:
            seen.add(row)
            out.append(row)
    return out


def _fetch_collection_title(client: ZhihuClient | None, collection_id: str) -> str:
    if client is None:
        return ""
    try:
        data = client.get_json(endpoints.collection_meta_url(collection_id))
        title = data.get("title") or (data.get("collection") or {}).get("title") or ""
        return str(title)
    except Exception as e:
        log.warning("collection title fetch failed id=%s: %s", collection_id, e)
        return ""


def _list_member_collections(client: ZhihuClient, url_token: str) -> dict[str, str]:
    """title(lower) -> collection id for B."""
    by_title: dict[str, str] = {}
    url = endpoints.member_collections_url(url_token)
    offset = 0
    while True:
        data = client.get_json(url, params={"offset": offset, "limit": 20})
        rows = data.get("data") or []
        if not rows:
            break
        for row in rows:
            cid = str(row.get("id") or (row.get("collection") or {}).get("id") or "")
            title = str(row.get("title") or (row.get("collection") or {}).get("title") or "")
            if cid and title:
                by_title.setdefault(title.lower(), cid)
        paging = data.get("paging") or {}
        if paging.get("is_end"):
            break
        offset += len(rows)
        if offset > 5000:
            break
    return by_title


def resolve_collections(
    *,
    from_items: list[tuple[str, str, str]],
    map_collection: dict[str, str],
    client: ZhihuClient | None,
    actor_token: str | None,
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """Return (collection_resolve rows, from_id -> to_id_or_create_marker)."""
    titles: dict[str, str] = {}
    for cid, _, _ in from_items:
        if cid not in titles:
            titles[cid] = _fetch_collection_title(client, cid)

    b_by_title: dict[str, str] = {}
    if client is not None and actor_token:
        try:
            b_by_title = _list_member_collections(client, actor_token)
        except Exception as e:
            log.warning("list B collections failed: %s", e)

    resolve: list[dict[str, Any]] = []
    mapping: dict[str, str] = {}
    for cid in sorted(titles.keys()):
        title = titles[cid]
        if cid in map_collection:
            to_id = map_collection[cid]
            how = "map"
            mapping[cid] = to_id
            resolve.append({"from_id": cid, "to_id": to_id, "how": how, "title": title})
            continue
        match = b_by_title.get(title.lower()) if title else None
        if match:
            mapping[cid] = match
            resolve.append({"from_id": cid, "to_id": match, "how": "name", "title": title})
        else:
            # create at apply; marker embeds title
            marker = f"__create__:{title or cid}"
            mapping[cid] = marker
            resolve.append({"from_id": cid, "to_id": None, "how": "create", "title": title or cid})
    return resolve, mapping


def build_plan(
    *,
    mode: str,
    sources: list[str],
    inventory_engine: StorageEngine,
    map_collection: dict[str, str] | None = None,
    limit: int | None = None,
    client: ZhihuClient | None = None,
    actor_token: str | None = None,
    inventory_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if mode not in ("prune", "migrate"):
        raise ValueError("mode must be prune|migrate")
    map_collection = dict(map_collection or {})
    actions: list[dict[str, Any]] = []
    collection_resolve: list[dict[str, Any]] = []

    ego = actor_token or _ego_from_engine(inventory_engine) or ""
    following: list[str] = []
    followed: list[str] = []
    collection_items: list[tuple[str, str, str]] = []

    if "following" in sources:
        following = _following_tokens(inventory_engine, ego) if ego else []
        for tok in following:
            op = "unfollow_user" if mode == "prune" else "follow_user"
            actions.append({"op": op, "url_token": tok})

    if "followed" in sources:
        followed = _followed_question_ids(inventory_engine)
        for qid in followed:
            op = "unfollow_question" if mode == "prune" else "follow_question"
            actions.append({"op": op, "question_id": qid})

    if "collection" in sources:
        collection_items = _collection_items(inventory_engine)
        if mode == "prune":
            for cid, ctype, coid in collection_items:
                actions.append(
                    {
                        "op": "collect_remove",
                        "collection_id": cid,
                        "content_type": ctype,
                        "content_id": coid,
                    }
                )
        else:
            collection_resolve, mapping = resolve_collections(
                from_items=collection_items,
                map_collection=map_collection,
                client=client,
                actor_token=actor_token,
            )
            for cid, ctype, coid in collection_items:
                target = mapping.get(cid, cid)
                action: dict[str, Any] = {
                    "op": "collect_add",
                    "content_type": ctype,
                    "content_id": coid,
                    "from_collection_id": cid,
                }
                if target.startswith("__create__:"):
                    action["collection_id"] = None
                    action["create_title"] = target[len("__create__:") :]
                else:
                    action["collection_id"] = target
                actions.append(action)

    if limit is not None and limit >= 0:
        actions = actions[:limit]

    actions = sorted(actions, key=lambda a: json.dumps(a, sort_keys=True))

    snap_following = following if "following" in sources else []
    snap_followed = followed if "followed" in sources else []
    snap_collection = collection_items if "collection" in sources else []

    fp = fingerprint_inventory(
        mode=mode,
        sources=sources,
        limit=limit,
        map_collection=map_collection,
        following=snap_following,
        followed=snap_followed,
        collection_items=snap_collection,
    )
    meta = dict(inventory_meta or {})
    meta.setdefault("map_collection", map_collection)
    meta["snapshot"] = {
        "following": snap_following,
        "followed": snap_followed,
        "collection_items": [[a, b, c] for a, b, c in snap_collection],
    }
    plan: dict[str, Any] = {
        "version": 1,
        "mode": mode,
        "danger": True,
        "fingerprint": fp,
        "actor_hint": actor_token,
        "sources": sources,
        "limit": limit,
        "actions": actions,
        "collection_resolve": collection_resolve,
        "inventory": meta,
        "counts": _count_ops(actions),
    }
    return plan


def _count_ops(actions: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for a in actions:
        op = str(a.get("op") or "")
        counts[op] = counts.get(op, 0) + 1
    return counts


def recompute_fingerprint(plan: dict[str, Any]) -> str:
    """Recompute from embedded inventory snapshot fields if present; else actions (tests)."""
    inv = plan.get("inventory") or {}
    snap = inv.get("snapshot")
    if isinstance(snap, dict):
        items = snap.get("collection_items") or []
        return fingerprint_inventory(
            mode=str(plan.get("mode")),
            sources=list(plan.get("sources") or []),
            limit=plan.get("limit"),
            map_collection=dict(inv.get("map_collection") or {}),
            following=list(snap.get("following") or []),
            followed=list(snap.get("followed") or []),
            collection_items=[(a, b, c) for a, b, c in items],
        )
    return fingerprint_actions(
        list(plan.get("actions") or []),
        mode=str(plan.get("mode")),
        sources=list(plan.get("sources") or []),
        limit=plan.get("limit"),
    )


def load_plan(path: Path) -> dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("plan must be a JSON object")
    return data


def rebuild_plan_from_inventory(plan: dict[str, Any], *, open_engine_fn, client: ZhihuClient | None = None) -> dict[str, Any]:
    """Rebuild plan from inventory paths stored in plan for fingerprint verification."""
    inv = plan.get("inventory") or {}
    mode = str(plan.get("mode"))
    sources = list(plan.get("sources") or [])
    limit = plan.get("limit")
    map_collection = dict(inv.get("map_collection") or {})
    from_data = inv.get("from_data_dir")
    data_dir = inv.get("data_dir")
    engine_name = inv.get("engine") or "sqlite"
    if mode == "migrate":
        if not from_data:
            raise ValueError("migrate plan missing inventory.from_data_dir")
        root = Path(from_data)
    else:
        if not data_dir:
            raise ValueError("prune plan missing inventory.data_dir")
        root = Path(data_dir)
    meta = root / "meta"
    eng = open_engine_fn(engine_name, meta)
    try:
        return build_plan(
            mode=mode,
            sources=sources,
            inventory_engine=eng,
            map_collection=map_collection,
            limit=limit,
            client=client,
            actor_token=plan.get("actor_hint"),
            inventory_meta=inv,
        )
    finally:
        eng.close()
