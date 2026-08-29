# Social + Content Graph Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Backup ego following/followers as canonical people MD + persisted `follows` edges; manual offline `graph rebuild` that graphifies existing items/membership into `graph.json` (plus people wikilinks); manual edge add/remove that survives API sync.

**Architecture:** New social Sources upsert `user` items via `process_person` and `graph_edges` (`origin=api`). `graph rebuild` derives content edges from meta, merges persisted edges, writes `graph.json` — never auto-run from backup. `--max-depth` wired but rejects `!= 1`.

**Tech Stack:** Python 3.10+, existing `zhihu_backup` (requests, PyYAML, sqlite3/json engines).

**Spec:** [docs/superpowers/specs/2026-08-29-social-graph-design.md](../specs/2026-08-29-social-graph-design.md)

## Global Constraints

- Persist state only via `StorageEngine`; derived `graph.json` under meta dir is the only sidecar export.
- People path: `contents/people/{url_token}.md` (flat — **not** `people/{me}/…`).
- Meta key: `user:{url_token}`; filenames no Chinese.
- `--source all` excludes social.
- Manual-only `graph rebuild`; backup/resume never rebuild.
- MVP `--max-depth` must be `1` or exit non-zero.
- No author nodes; no avatar assets; no Zhihu unfollow.

## File map

| Path | Responsibility |
|------|----------------|
| `zhihu_backup/models.py` | `GraphEdge`, `business_extra` for `user` |
| `zhihu_backup/storage/base.py` | Abstract edge + list APIs |
| `zhihu_backup/storage/sqlite_engine.py` | `graph_edges` table + list_items/membership |
| `zhihu_backup/storage/json_engine.py` | Same (rocks inherits) |
| `zhihu_backup/sources/following.py` | Followees source |
| `zhihu_backup/sources/followers.py` | Followers source |
| `zhihu_backup/sources/__init__.py` | Register social; keep `all` exclusive |
| `zhihu_backup/writers/person.py` | Flat people MD writer |
| `zhihu_backup/graph.py` | Derive + rebuild + export |
| `zhihu_backup/pipeline.py` | `process_person` for `item_type==user` |
| `zhihu_backup/cli.py` | `--max-depth`, `graph` subcommands |
| `AGENTS.md` | Document social + graph commands |
| `tests/test_graph_edges_storage.py` | Edge CRUD |
| `tests/test_graph_rebuild.py` | Derived edges + merge |
| `tests/test_social_sources_build.py` | `all` excludes social; social resolves |

---

### Task 1: GraphEdge model + StorageEngine APIs

**Files:**
- Modify: `zhihu_backup/models.py`
- Modify: `zhihu_backup/storage/base.py`
- Modify: `zhihu_backup/storage/sqlite_engine.py`
- Modify: `zhihu_backup/storage/json_engine.py`
- Test: `tests/test_graph_edges_storage.py`

**Interfaces:**
- Produces: `GraphEdge(from_id, to_id, kind, origin, seen_at)`; `upsert_graph_edge`, `remove_graph_edge`, `list_graph_edges`, `list_items`, `list_membership`

- [ ] **Step 1: Write failing storage tests**

```python
# tests/test_graph_edges_storage.py
from pathlib import Path
from zhihu_backup.models import GraphEdge, ItemRecord
from zhihu_backup.storage.sqlite_engine import SqliteEngine
from zhihu_backup.storage.json_engine import JsonEngine


def _edge(**kw):
    base = dict(
        from_id="user:a",
        to_id="user:b",
        kind="follows",
        origin="api",
        seen_at="2026-01-01T00:00:00Z",
    )
    base.update(kw)
    return GraphEdge(**base)


def test_sqlite_upsert_list_remove(tmp_path: Path):
    eng = SqliteEngine(tmp_path / "t.db")
    eng.upsert_graph_edge(_edge())
    eng.upsert_graph_edge(_edge(origin="manual", seen_at="2026-01-02T00:00:00Z"))
    edges = eng.list_graph_edges()
    assert len(edges) == 1
    assert edges[0].origin == "manual"
    eng.remove_graph_edge("user:a", "user:b", "follows")
    assert eng.list_graph_edges() == []
    eng.close()


def test_sqlite_list_items_membership(tmp_path: Path):
    eng = SqliteEngine(tmp_path / "t.db")
    eng.upsert_item(
        ItemRecord(key="question:1", item_type="question", zhihu_id="1", title="Q")
    )
    eng.link_membership("question:1", "asked_questions", "me")
    assert eng.list_items()[0].key == "question:1"
    assert eng.list_membership() == [
        {"key": "question:1", "owner_kind": "asked_questions", "owner_id": "me"}
    ]
    eng.close()


def test_json_graph_edges_parity(tmp_path: Path):
    eng = JsonEngine(tmp_path / "state.json")
    eng.upsert_graph_edge(_edge())
    assert len(eng.list_graph_edges()) == 1
    eng.close()
```

- [ ] **Step 2: Run tests — expect fail**

Run: `pytest tests/test_graph_edges_storage.py -v`  
Expected: FAIL (GraphEdge / methods missing)

- [ ] **Step 3: Add `GraphEdge` + `business_extra` for user**

In `zhihu_backup/models.py`, add:

```python
@dataclass
class GraphEdge:
    from_id: str
    to_id: str
    kind: str
    origin: str  # api | manual
    seen_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GraphEdge":
        return cls(
            from_id=str(data["from_id"]),
            to_id=str(data["to_id"]),
            kind=str(data["kind"]),
            origin=str(data["origin"]),
            seen_at=str(data.get("seen_at") or ""),
        )
```

In `business_extra`, before the generic fallback:

```python
if t == "user":
    return {"user_id": zid, "url_token": zid}
```

- [ ] **Step 4: Extend `StorageEngine` ABC**

```python
# zhihu_backup/storage/base.py — add imports GraphEdge; add methods:
@abstractmethod
def upsert_graph_edge(self, edge: GraphEdge) -> None: ...

@abstractmethod
def remove_graph_edge(self, from_id: str, to_id: str, kind: str) -> None: ...

@abstractmethod
def list_graph_edges(self) -> list[GraphEdge]: ...

@abstractmethod
def list_items(self) -> list[ItemRecord]: ...

@abstractmethod
def list_membership(self) -> list[dict[str, str]]: ...
```

- [ ] **Step 5: Implement sqlite**

Schema addition in `_init_schema`:

```sql
CREATE TABLE IF NOT EXISTS graph_edges (
    from_id TEXT NOT NULL,
    to_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    origin TEXT NOT NULL,
    seen_at TEXT,
    PRIMARY KEY (from_id, to_id, kind)
);
```

Implement upsert (INSERT OR REPLACE), remove, list_*; `list_membership` returns `[{"key","owner_kind","owner_id"}, ...]`.

- [ ] **Step 6: Implement json**

In `_default()` add `"graph_edges": {}`. Key edges as `f"{from_id}\t{to_id}\t{kind}"`. Implement list helpers from `items` / `membership`.

- [ ] **Step 7: Run tests — expect pass**

Run: `pytest tests/test_graph_edges_storage.py -v`  
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add zhihu_backup/models.py zhihu_backup/storage/ tests/test_graph_edges_storage.py
git commit -m "$(cat <<'EOF'
feat: add graph_edges storage and list helpers for rebuild

EOF
)"
```

---

### Task 2: Offline `graph rebuild` (derived content edges)

**Files:**
- Create: `zhihu_backup/graph.py`
- Create: `zhihu_backup/writers/person.py` (wikilink refresh helpers used by rebuild)
- Test: `tests/test_graph_rebuild.py`

**Interfaces:**
- Consumes: `list_items`, `list_membership`, `list_graph_edges`
- Produces: `rebuild_graph(engine, contents_root, meta_dir, *, ego=None) -> dict` writing `meta_dir/graph.json`

- [ ] **Step 1: Write failing rebuild tests**

```python
# tests/test_graph_rebuild.py
from pathlib import Path
from zhihu_backup.models import GraphEdge, ItemRecord
from zhihu_backup.storage.sqlite_engine import SqliteEngine
from zhihu_backup.graph import rebuild_graph


def test_rebuild_derives_answers_and_asked(tmp_path: Path):
    eng = SqliteEngine(tmp_path / "t.db")
    eng.upsert_item(
        ItemRecord(
            key="answer:10:20",
            item_type="answer",
            zhihu_id="20",
            title="A",
            url="https://www.zhihu.com/question/10/answer/20",
            path="contents/votes/me/answer_10_20.md",
            extra={"question_id": "10", "parent_id": "10"},
        )
    )
    eng.upsert_item(
        ItemRecord(key="question:10", item_type="question", zhihu_id="10", title="Q")
    )
    eng.link_membership("question:10", "asked_questions", "me_token")
    eng.upsert_graph_edge(
        GraphEdge(
            from_id="user:me_token",
            to_id="user:friend",
            kind="follows",
            origin="manual",
            seen_at="2026-01-01T00:00:00Z",
        )
    )
    meta = tmp_path / "meta"
    meta.mkdir()
    people = tmp_path / "contents" / "people"
    people.mkdir(parents=True)
    (people / "me_token.md").write_text("---\ntitle: Me\n---\n\nbody\n", encoding="utf-8")
    out = rebuild_graph(eng, tmp_path / "contents", meta, ego="me_token")
    assert (meta / "graph.json").exists()
    kinds = {(e["from"], e["to"], e["kind"], e["origin"]) for e in out["edges"]}
    assert ("answer:10:20", "question:10", "answers", "derived") in kinds
    assert ("user:me_token", "question:10", "asked", "derived") in kinds
    assert ("user:me_token", "user:friend", "follows", "manual") in kinds
    eng.close()
```

- [ ] **Step 2: Run — expect fail**

Run: `pytest tests/test_graph_rebuild.py -v`  
Expected: FAIL import/rebuild missing

- [ ] **Step 3: Implement `zhihu_backup/graph.py`**

Core logic (complete module):

```python
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
```

Implement `_refresh_people_wikilinks` as shown above (complete helpers `_split_frontmatter` / `_strip_link_sections` / `_section`).

- [ ] **Step 4: Run tests — expect pass**

Run: `pytest tests/test_graph_rebuild.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add zhihu_backup/graph.py zhihu_backup/writers/person.py tests/test_graph_rebuild.py
git commit -m "$(cat <<'EOF'
feat: offline graph rebuild from items, membership, and edges

EOF
)"
```

---

### Task 3: Following/Followers sources + person pipeline

**Files:**
- Create: `zhihu_backup/sources/following.py`, `zhihu_backup/sources/followers.py`
- Modify: `zhihu_backup/sources/__init__.py`, `zhihu_backup/pipeline.py`, `zhihu_backup/writers/person.py`
- Test: `tests/test_social_sources_build.py`, extend rebuild/person as needed

**Interfaces:**
- Produces: `FollowingSource.name == "following"`, `FollowersSource.name == "followers"`
- `normalize_member(row, *, center_id, source_tag, edge_direction) -> NormalizedItem`
- Pipeline: if `item.item_type == "user"`: `process_person` (no assets)

- [ ] **Step 1: Failing build_sources test**

```python
# tests/test_social_sources_build.py
from unittest.mock import MagicMock
from zhihu_backup.sources import build_sources


def test_all_excludes_social():
    client = MagicMock()
    client.get_json.return_value = {"url_token": "me", "id": "me"}
    names = {s.name for s in build_sources(client, source="all", collection_ids=[])}
    assert "following" not in names
    assert "followers" not in names


def test_social_includes_both():
    client = MagicMock()
    client.get_json.return_value = {"url_token": "me", "id": "me"}
    names = [s.name for s in build_sources(client, source="social", collection_ids=[])]
    assert names == ["following", "followers"]
```

- [ ] **Step 2: Run — expect fail**

Run: `pytest tests/test_social_sources_build.py -v`

- [ ] **Step 3: Implement sources**

`following.py` pattern (mirror `pin.py`):

```python
class FollowingSource(Source):
    name = "following"

    def __init__(self, client: ZhihuClient, user_id: str):
        self.client = client
        self.source_id = str(user_id)
        self._api = f"https://www.zhihu.com/api/v4/members/{self.source_id}/followees"

    def total(self) -> Optional[int]:
        data = self.client.get_json(self._api, params={"offset": 0, "limit": 1})
        return int((data.get("paging") or {}).get("totals") or 0)

    def iter_items(self, offset: int = 0, limit: int = 20) -> Iterator[tuple[int, list[NormalizedItem]]]:
        from zhihu_backup.parse import normalize_member

        current = offset
        while True:
            data = self.client.get_json(self._api, params={"offset": current, "limit": limit})
            rows = data.get("data") or []
            items: list[NormalizedItem] = []
            for row in rows:
                member = row.get("author") if isinstance(row.get("author"), dict) else row
                if not isinstance(member, dict):
                    continue
                item = normalize_member(
                    member, center_id=self.source_id, source_name=self.name
                )
                if item:
                    items.append(item)
            next_offset = current + len(rows)
            yield next_offset, items
            paging = data.get("paging") or {}
            if not rows or paging.get("is_end"):
                break
            current = next_offset
```

`FollowersSource` is identical except `name = "followers"` and API suffix `/followers`.

```python
def normalize_member(
    row: dict,
    *,
    center_id: str,
    source_name: str,  # following | followers
) -> Optional[NormalizedItem]:
    token = str(row.get("url_token") or row.get("id") or "")
    if not token:
        return None
    name = str(row.get("name") or token)
    headline = str(row.get("headline") or "")
    return NormalizedItem(
        item_type="user",
        zhihu_id=token,
        url=f"https://www.zhihu.com/people/{token}",
        title=name,
        author=name,
        author_badge=headline,
        markdown_body=headline or name,
        owner_kind="people",
        owner_id=center_id,
        sources=[f"{source_name}:{center_id}"],
        modified=None,  # always rewrite person shell unless --full skip via hash later
    )
```

For incremental skip: set `modified` from nothing → first run creates; subsequent runs without `--full` skip if item exists (extend `should_skip`: for `user`, skip when existing and not `full`). Document in `process_person`.

`FollowersSource`: same API path `/followers`; edge direction `user→me`.

- [ ] **Step 4: `PersonWriter` flat path**

```python
# zhihu_backup/writers/person.py
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from zhihu_backup.models import NormalizedItem, business_extra


class PersonWriter:
    def __init__(self, contents_root: Path):
        self.root = Path(contents_root) / "people"

    def path_for(self, token: str) -> Path:
        return self.root / f"{token}.md"

    def write(self, item: NormalizedItem, body: str) -> Path:
        path = self.path_for(item.zhihu_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        data: dict[str, Any] = {
            "id": item.zhihu_id,
            "type": "user",
            "url": item.url,
            "title": item.title,
            "url_token": item.zhihu_id,
            "sources": item.sources,
        }
        data.update(business_extra(item))
        if item.author_badge:
            data["headline"] = item.author_badge
        data = {k: v for k, v in data.items() if v is not None}
        fm = yaml.dump(data, allow_unicode=True, sort_keys=False, default_flow_style=False)
        path.write_text(f"---\n{fm}---\n\n{body.lstrip()}", encoding="utf-8")
        return path
```

- [ ] **Step 5: Pipeline `process_person`**

In `process_item`, branch:

```python
if item.item_type == "user":
    return self.process_person(item, source=source)
```

`process_person`:
1. If not full and `get_item(item.key)` exists → update `last_seen_at`, still `upsert_graph_edge`, return `"skipped"` (edge refresh every time).
2. Else write via `PersonWriter`, upsert item, upsert edge.
3. Edge: if `source.name == "following"`: `from=user:{source.source_id}`, `to=user:{item.zhihu_id}`; if `followers`: reverse. `kind=follows`, `origin=api`.

- [ ] **Step 6: Register in `build_sources`**

```python
need_me = name in (
    "all", "pin", "pins", "asked", "asked_questions", "followed", "followed_questions",
    "vote", "votes", "following", "followers", "social",
)
# NOTE: "all" must NOT include following/followers
if name in ("following", "social") and user_id:
    sources.append(FollowingSource(client, user_id))
if name in ("followers", "social") and user_id:
    sources.append(FollowersSource(client, user_id))
```

Prefer `url_token` over numeric `id` for `user_id` when both exist (`url_token` first).

- [ ] **Step 7: Tests pass + commit**

```bash
pytest tests/test_social_sources_build.py tests/test_graph_rebuild.py -v
git add zhihu_backup/sources/ zhihu_backup/pipeline.py zhihu_backup/writers/person.py zhihu_backup/parse.py tests/
git commit -m "$(cat <<'EOF'
feat: backup following/followers into people and api follows edges

EOF
)"
```

---

### Task 4: CLI — `graph` commands + `--max-depth`

**Files:**
- Modify: `zhihu_backup/cli.py`
- Modify: `zhihu_backup/storage/__init__.py` if needed for meta path helper
- Test: `tests/test_cli_graph_max_depth.py` (argparse / cmd unit)

**Interfaces:**
- Produces: `python -m zhihu_backup graph rebuild|edge …`; `--max-depth` on backup/resume

- [ ] **Step 1: Failing max-depth test**

```python
# tests/test_cli_graph_max_depth.py
from zhihu_backup.cli import build_parser, main


def test_max_depth_rejected(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    # minimal: call internal guard
    from zhihu_backup.cli import _require_max_depth_one
    import pytest
    with pytest.raises(SystemExit):
        _require_max_depth_one(2)
```

Or test `main(["backup", "--max-depth", "2", "--json"])` returns non-zero after engine open — prefer pure helper:

```python
def test_require_max_depth_one():
    from zhihu_backup.cli import require_max_depth_mvp
    assert require_max_depth_mvp(1) is None
    err = require_max_depth_mvp(2)
    assert err and "not implemented" in err.lower()
```

- [ ] **Step 2: Implement CLI**

```python
def require_max_depth_mvp(n: int) -> Optional[str]:
    if int(n) != 1:
        return f"--max-depth={n} not implemented yet (only 1 supported)"
    return None
```

In `_run_backup`, before sources:

```python
msg = require_max_depth_mvp(getattr(args, "max_depth", 1))
if msg:
    if args.json:
        print(json.dumps({"event": "error", "error": msg}), flush=True)
    else:
        log.error(msg)
    return 2
```

Add `--max-depth` default 1 to backup flags.

`graph` subparser:

```python
g = sub.add_parser("graph", help="relationship graph helpers", parents=[common])
g_sub = g.add_subparsers(dest="graph_command", required=True)
rb = g_sub.add_parser("rebuild", help="offline rebuild graph.json from meta", parents=[common])
rb.set_defaults(func=cmd_graph_rebuild)
ea = g_sub.add_parser("edge", help="manual edge mutations", parents=[common])
# edge add/remove as nested or flat: graph edge add | graph edge remove
```

Prefer flat:

```python
# graph rebuild | graph edge-add | graph edge-remove
# OR nest: graph edge {add,remove} — implement nested to match `auth set-cookie`
```

Implement nested `graph edge add|remove` like `auth set-cookie`.

`cmd_graph_rebuild`:
- open engine
- resolve ego via `/me` **only if cookies present**; else `ego=None` (offline content-only OK)
- `meta_dir = data/meta/{engine}/` (same as open_engine path parent)
- `out = rebuild_graph(...);` print `{"event":"summary","nodes":N,"edges":M}` if `--json`

`cmd_graph_edge_add/remove`: upsert/remove `GraphEdge` with `origin=manual`.

- [ ] **Step 3: Tests + commit**

```bash
pytest tests/test_cli_graph_max_depth.py -v
git add zhihu_backup/cli.py tests/test_cli_graph_max_depth.py
git commit -m "$(cat <<'EOF'
feat: add graph rebuild/edge CLI and max-depth MVP guard

EOF
)"
```

---

### Task 5: Docs + acceptance smoke

**Files:**
- Modify: `AGENTS.md`
- Optionally: `README.md` (one paragraph + commands only if README already lists sources)

- [ ] **Step 1: Update AGENTS.md**

Add under Layout: `contents/people/{url_token}.md`, `meta/.../graph.json`.  
Commands:

```bash
python -m zhihu_backup backup --source social --json
python -m zhihu_backup graph rebuild --json
python -m zhihu_backup graph edge add --from user:a --to user:b
python -m zhihu_backup graph edge remove --from user:a --to user:b
```

Note: `all` excludes social; rebuild is manual; `--max-depth` reserved.

- [ ] **Step 2: Run full relevant tests**

```bash
pytest tests/test_graph_edges_storage.py tests/test_graph_rebuild.py tests/test_social_sources_build.py tests/test_cli_graph_max_depth.py tests/test_business_extra.py -v
```

Expected: all PASS

- [ ] **Step 3: Manual acceptance checklist (no network for rebuild)**

1. Seed sqlite with answer+question+membership (or use existing `data/`) → `graph rebuild --json` → jq `.edges[] | select(.kind=="answers")`
2. Confirm backup `--source all` source list has no following/followers (unit already covers)
3. `--max-depth 2` returns 2

- [ ] **Step 4: Commit**

```bash
git add AGENTS.md
git commit -m "$(cat <<'EOF'
docs: document social backup and manual graph rebuild

EOF
)"
```

---

## Spec coverage self-check

| Spec requirement | Task |
|------------------|------|
| People MD + following/followers APIs | 3 |
| Persisted edges api/manual | 1, 3, 4 |
| Manual-only rebuild + derived content edges | 2, 4 |
| `graph.json` + wikilinks | 2 |
| `all` excludes social | 3 |
| `--max-depth` reject ≠1 | 4 |
| Manual edge add/remove | 4 |
| AGENTS / verify | 5 |

## Placeholder scan

No TBD steps; wikilink helper fully specified in Task 2; person flat path explicit.
