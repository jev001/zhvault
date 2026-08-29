# Graph Query + Vector Search — Design

**Date:** 2026-08-29  
**Status:** Approved  
**Parent:** [2026-08-29-social-graph-design.md](./2026-08-29-social-graph-design.md)

## Goal

Phased local indexes on top of the existing backup + social/content graph:

1. **Phase 1 — structure graph query:** multi-hop / kind-filtered queries over relationship edges without a server graph DB.
2. **Phase 2 — semantic search:** chunk + embed markdown bodies; pluggable vector backends with **Chroma optional**.

Both phases treat `StorageEngine` + `contents/**/*.md` as source of truth. Graph DB / vector DB are **derived indexes** (delete + rebuild safe).

## Non-goals

- Neo4j / hosted graph or vector services as defaults
- Auto-index after every `backup` / `resume` (manual sync, same posture as `graph rebuild`)
- Inferring social edges from embeddings
- Replacing `graph.json` / Obsidian wikilinks
- Bundling heavy ML stacks in the default install

## Shared conventions

- **Node / doc id:** existing meta keys (`user:{token}`, `answer:{qid}:{aid}`, `question:{id}`, …)
- **Derived layout:**

```
data/meta/{engine}/
  graph.json                 # existing rebuild export
  graph_query/               # Phase 1 optional materialization (if any)
  vectors/{backend}/         # Phase 2 backend-specific store
```

- CLI stays agent-friendly (`--json`); indexes never become a second write path for cookies/items/edges.

```text
Truth: items + membership + graph_edges + contents/*.md
  ├─ graph rebuild  → graph.json / wikilinks     (exists)
  ├─ graph query    → read edges (+ optional sync)  Phase 1
  └─ search index   → VectorStore backend           Phase 2
```

---

## Phase 1 — Structure graph query

### 1a (default, no new deps)

- Implement BFS / recursive query over:
  - persisted `graph_edges`, and
  - derived edges computed the same way as `rebuild_graph` (or load last `graph.json` if present and fresher — prefer **compute from engine** so stale JSON cannot lie).
- CLI:

```bash
python -m zhihu_backup graph query \
  --from user:me_token \
  --depth 2 \
  --kind follows \
  --json
```

- Output: nodes reached + edge trail (from/to/kind/origin). Exit 0 with empty set if none.
- Supports multiple `--kind` or `all` (default: all kinds).

### 1b (optional embedded graph engine)

- Only if 1a is insufficient (scale / Cypher desire).
- Candidate: **Kuzu** as optional extra; `graph sync --backend kuzu` loads nodes/edges into `data/meta/{engine}/graph_query/kuzu/`.
- Default install must not require Kuzu. Query path: prefer engine backend if synced, else 1a.

### Phase 1 acceptance

- Offline query works with content-only meta (derived edges) and with social `follows`.
- `--depth 2` returns transitive neighbors for `follows`.
- Does not mutate `graph_edges` or call Zhihu APIs.

### Phase 1 deferred

- Full Cypher surface, visualization UI, auto-sync after backup.

---

## Phase 2 — Semantic search (pluggable VectorStore)

### Problem split

| Concern | Owner |
|---------|--------|
| Chunking markdown | `zhihu_backup/search/chunk.py` |
| Embedding text → vectors | `EmbeddingProvider` protocol |
| Persist / query vectors | `VectorStore` protocol |
| CLI orchestration | `search index` / `search semantic` |

### VectorStore protocol (required)

```python
class VectorStore(Protocol):
    name: str  # backend id, e.g. "chroma", "memory"

    def upsert(self, records: Sequence[VectorRecord]) -> None:
        """Idempotent upsert by record.id (chunk id)."""

    def delete(self, ids: Sequence[str]) -> None: ...

    def query(
        self,
        vector: Sequence[float],
        *,
        top_k: int = 10,
        where: Mapping[str, Any] | None = None,
    ) -> list[VectorHit]:
        """Nearest neighbors; where filters metadata (e.g. item_type)."""

    def clear(self) -> None: ...
```

`VectorRecord`:

- `id`: stable chunk id, e.g. `{item_key}#{chunk_index}`
- `vector`: list[float]
- `document`: chunk text (optional store)
- `metadata`: `{item_key, item_type, path, title, chunk_index, ...}`

Factory: `open_vector_store(backend: str, root: Path, **kwargs) -> VectorStore`.

Unknown backend → clear error listing installed backends.

### Backends

| Backend | Packaging | Role |
|---------|-----------|------|
| `memory` | always | Tests / tiny smoke; not durable |
| `chroma` | **optional** extra (`pip install zhihu-backup[chroma]` or `chromadb`) | Default durable local store when extra installed |
| (later) `sqlite_vec` / LanceDB | optional extras | Same protocol; not required for MVP |

**Chroma specifics:**

- Persist under `data/meta/{engine}/vectors/chroma/`
- Collection name fixed, e.g. `zhihu_chunks`
- Soft-fail: if user passes `--vector-backend chroma` but package missing → exit non-zero with install hint
- Default `--vector-backend`: if unset, prefer `chroma` when importable; otherwise require an explicit `--vector-backend memory` (tests) or fail with install hint — **never silently skip indexing**

### EmbeddingProvider protocol

```python
class EmbeddingProvider(Protocol):
    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...
    @property
    def dimensions(self) -> int: ...
    @property
    def model_id(self) -> str: ...
```

MVP providers:

- `hash` / deterministic stub — tests only (not semantic)
- optional real provider behind extra (e.g. local sentence-transformers or HTTP API) — **separate from Chroma extra** so Chroma can be tested with stub embeddings

Store `model_id` + `dimensions` in an index manifest (`vectors/manifest.json`) so reindex is forced on model change.

### Chunking

- Input: item records with `path` under `contents/`
- Split on markdown headings / blank lines; max chars soft limit (e.g. 1200) with overlap ~100
- Skip `people/` wikilink-only shells if body shorter than N (configurable); still allow indexing people headlines if desired later
- No network during `search index` except whatever the embedding provider needs

### CLI

```bash
python -m zhihu_backup search index --vector-backend chroma --json
python -m zhihu_backup search semantic "关键词或句子" --top-k 10 --json
python -m zhihu_backup search semantic "..." --expand-graph 1 --kind follows --json
```

- `search index`: chunk → embed → `VectorStore.upsert`; writes/updates manifest
- `search semantic`: embed query → `VectorStore.query` → hits with `item_key`, score, snippet path
- `--expand-graph N`: optional; run Phase 1 query from each hit’s `item_key` / author user node if present — best-effort, skipped if no graph neighbors

### Packaging

```toml
# pyproject.toml extras (illustrative)
[project.optional-dependencies]
chroma = ["chromadb>=0.5"]
# search-ml = ["sentence-transformers..."]  # later, separate from chroma
```

Default `pip install` / requirements.txt: **no chromadb**.

### Phase 2 acceptance

- With chroma extra: index a fixture vault → semantic query returns expected `item_key` (stub or real embedder in CI — CI uses `memory` + hash embedder).
- Missing chroma + `--vector-backend chroma` → non-zero + install message.
- Protocol allows a second backend without changing CLI verbs.
- `search index` does not write `graph_edges`; does not call Zhihu.

### Phase 2 deferred

- Hybrid BM25+vector ranking
- Auto-reindex on backup
- Multimodal (images)
- Hosted Chroma / cloud embeddings as first-class (may appear later as another EmbeddingProvider)

---

## Implementation order

1. Phase **1a** `graph query` (SQLite/in-process BFS) + tests + AGENTS — **done**
2. Phase **2** `VectorStore` + `memory` + optional `chroma` + stub embedder + `search index|semantic` — **done**
3. Phase **1b** Kuzu + real EmbeddingProviders — see [2026-08-29-kuzu-embeddings-design.md](./2026-08-29-kuzu-embeddings-design.md)
4. ~~Real EmbeddingProvider extra when product-ready~~ → covered in kuzu-embeddings design (local + http)

## Risks / notes

- Preferring `url_token` for `/me` may leave dual user nodes (`user:numeric` vs `user:token`) in old data — document in query help.
- Chroma native deps can be painful on some platforms — keep it optional and document the extra.
- Do not put vectors inside the JSON meta blob; keep backend directories separate for size and clear/rebuild.

## Out of scope follow-ups (parent graph spec still open)

- Author `url_token` → `authored` edges  
- BFS crawl `--max-depth N` for social backup  
- Auto graph rebuild / auto search index  
