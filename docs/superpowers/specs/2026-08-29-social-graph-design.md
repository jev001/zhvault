# Social + Content Graph — Design

**Date:** 2026-08-29  
**Status:** Approved  
**Parent:** [2026-08-29-zhihu-backup-design.md](./2026-08-29-zhihu-backup-design.md)

## Goal

1. Backup the logged-in user's **following** and **followers** into canonical person markdown plus durable directed `follows` edges.
2. Provide a **manual, offline** `graph rebuild` that materializes a unified relationship graph from already-backed-up `items` + `membership`, merged with persisted API/manual edges.
3. Allow **manual edge maintenance** that survives API social sync and derived recompute.
4. Reserve `--max-depth` for a later multi-hop crawl (MVP depth = 1 only).

## Non-goals (this iteration)

- Auto `graph rebuild` after `backup` / `resume`
- Multi-hop crawl (`--max-depth > 1` must fail clearly)
- Author→content edges (author `url_token` not stored yet)
- Avatar / people asset download
- Zhihu-side unfollow / remove follower
- Graph UI / Neo4j / visualization beyond JSON + Obsidian wikilinks
- Including social sources in `--source all`

## Layout

```
data/
  contents/
    people/
      {url_token}.md              # one file per person
      _index_{me_url_token}.md    # ego index (derived on rebuild)
    {collections|pins|...}/...    # unchanged content tree
  meta/{sqlite|json|rocksdb}/
    ...                           # items, membership, checkpoints, ...
    graph_edges                   # persisted: origin=api|manual only
    graph.json                    # derived export (rebuild only)
```

- Person meta key: `user:{url_token}`
- Person filename: `{url_token}.md` (no Chinese)
- `owner_kind` for people items: `people`

### Person frontmatter (minimum)

- `id` / `url_token`, `type: user`, `url`, `title` (display name), `headline`, optional follower/following counts
- `sources[]` e.g. `following:{me}`, `followers:{me}`
- Body sections `## Following` / `## Followers` with `[[url_token]]` — **written only by `graph rebuild`**, from persisted `follows` edges

## Graph model

### Nodes

Node `id` = existing meta item key when available:

- `user:{url_token}`
- `question:{id}`, `answer:{qid}:{aid}`, `article:…`, `pin:…`, …
- Synthetic `collection:{id}` when membership `owner_kind=collections`

Rebuild also ensures stub user nodes for people-scoped membership `owner_id` values even if no people MD exists yet.

### Persisted edges (`graph_edges`)

Identity: `(from_id, to_id, kind)`.

| field | meaning |
|-------|---------|
| `from_id`, `to_id` | node ids |
| `kind` | e.g. `follows` |
| `origin` | `api` \| `manual` |
| `seen_at` | ISO timestamp on upsert |

Rules:

- Social backup upserts `follows` with `origin=api` (following: `me→user`; followers: `user→me`).
- `graph edge add` writes `origin=manual` (default kind `follows`).
- API sync **must not delete** `origin=manual` rows.
- Derived content relations are **not** stored in `graph_edges`.

### Derived edges (JSON only, `origin=derived`)

Computed exclusively inside `graph rebuild`:

| kind | from → to | source |
|------|-----------|--------|
| `answers` | answer → question | item `parent_id` |
| `in_column` | article → column | item `parent_id` / extra |
| `asked` | `user:{owner_id}` → question | membership `asked_questions` |
| `follows_question` | `user:{owner_id}` → question | membership `followed_questions` |
| `voted` | `user:{owner_id}` → item | membership `votes` |
| `pinned` | `user:{owner_id}` → pin | membership `pins` |
| `collected` | `collection:{id}` → item | membership `collections` |

### Export `graph.json`

```json
{
  "version": 1,
  "ego": "<me_url_token or null>",
  "max_depth_requested": 1,
  "max_depth_applied": 1,
  "generated_at": "...",
  "nodes": [
    {"id": "...", "type": "...", "title": "...", "url": "...", "path": "..."}
  ],
  "edges": [
    {"from": "...", "to": "...", "kind": "...", "origin": "api|manual|derived"}
  ]
}
```

Rebuild steps:

1. Load all items → nodes.
2. Add stub nodes for membership-derived users/collections as needed.
3. Emit derived edges from parent links + membership.
4. Load persisted `graph_edges` (api + manual).
5. Union → write `graph.json`.
6. Refresh people Following/Followers wikilinks + `_index_{me}.md` from **follows** edges only.

## CLI

| command / flag | behavior |
|----------------|----------|
| `--source following\|followers\|social` | people backup; `social` = both for ego from `/api/v4/me` |
| `--source all` | existing content sources only — **excludes** social |
| `--max-depth N` | default `1`; MVP **errors** if `N != 1` |
| `graph rebuild` | offline; only way to refresh `graph.json` / people wikilinks |
| `graph edge add --from KEY --to KEY [--kind KIND]` | upsert edge with `origin=manual` (overwrites prior `origin` on same `(from,to,kind)`) |
| `graph edge remove --from KEY --to KEY [--kind KIND]` | delete that `(from,to,kind)` row entirely (api or manual) |

`backup` / `resume` never call rebuild. API social sync upserts `origin=api` only when inserting/updating from the feed; it must not delete other `(from,to,kind)` rows, including manual ones that are not in the current page.

## Pipeline (people)

- APIs: `GET /api/v4/members/{id}/followees`, `.../followers` (offset paging, same pattern as pins).
- `FollowingSource` / `FollowersSource`; checkpoint `(source, center_token)`.
- `process_person`: incremental skip via `content_updated_at` / `--full`; write `contents/people/{token}.md`; `upsert_item`; `upsert_graph_edge(..., origin=api)`.
- No asset localization for people in MVP.
- One side HTTP 403 → `source_error` + continue other sources.

## Multi-hop (later)

- Depth 0 = ego; depth k expands followees∪followers of depth k−1 nodes (deduped).
- Same person/edge/rebuild machinery; this iteration only wires `--max-depth` and rejects `>1`.

## StorageEngine additions

- `upsert_graph_edge(from_id, to_id, kind, origin, seen_at)`
- `remove_graph_edge(from_id, to_id, kind, *, origin=None)` — see CLI note
- `list_graph_edges()` → all persisted edges
- `list_items()` / `list_membership()` (or equivalent) for offline rebuild — required for content graphify

Implement for `sqlite` and `json`; `rocksdb` stub mirrors interface.

## Acceptance

- Content-only meta: `graph rebuild --json` produces nodes/edges for answers→questions and membership relations (jq-able); no network.
- `backup --source social` then `graph rebuild`: people files + `follows` in JSON; second social run mostly `skipped`.
- Manual edge remains after social re-backup and after another rebuild.
- `backup --source all` does not fetch social and does not touch `graph.json`.
- `--max-depth 2` exits non-zero with a clear message.
- Interrupt + `resume` continues following/followers checkpoints.

## Out of scope follow-ups

- Persist author `url_token` → `authored` edges
- Implement BFS `--max-depth N`
- Optional auto-rebuild flag (explicit opt-in only)
