# Kuzu Graph Sync + Real Embeddings — Design

**Date:** 2026-08-29  
**Status:** Approved  
**Parent:** [2026-08-29-graph-vector-indexes-design.md](./2026-08-29-graph-vector-indexes-design.md)

## Goal

1. **Phase 1b:** Optional **Kuzu** derived graph index + query path that prefers Kuzu when synced, else falls back to in-process BFS (1a).
2. **Embeddings C:** Pluggable real embedders — **local sentence-transformers** and **HTTP OpenAI-compatible API** — alongside existing `hash` (tests). Separate extras from Chroma.

## Non-goals

- Making Kuzu or ML stacks required for default install
- Replacing `graph.json` / StorageEngine as source of truth
- Auto-sync/index after every backup
- Hosted Neo4j / cloud-only vector DB as defaults
- Changing VectorStore protocol (Chroma/memory stay)

## Shared rules

- Derived indexes under `data/meta/{engine}/`
- Optional deps via `pyproject.toml` extras; missing import → non-zero + install hint
- CLI `--json`; no silent fallbacks to weaker backends when user asked for a stronger one

```
data/meta/{engine}/
  graph.json
  graph_query/kuzu/          # Phase 1b
  vectors/{backend}/         # existing
  vectors/manifest.json      # extend with embedder model_id (already)
```

---

## Phase 1b — Kuzu

### Sync

```bash
python -m zhihu_backup graph sync --backend kuzu [--json]
```

- Load unified edges via `load_unified_edge_rows` + nodes from `list_items` / stubs (same as rebuild/query).
- Write/overwrite `meta/{engine}/graph_query/kuzu/`.
- Extra: `pip install 'zhihu-backup[kuzu]'` → `kuzu` package.
- Missing kuzu + `--backend kuzu` → error with install hint.

### Query

```bash
python -m zhihu_backup graph query --from KEY --depth N --kind ... [--backend auto|memory|kuzu]
```

| `--backend` | Behavior |
|-------------|----------|
| `auto` (default) | Use Kuzu if DB dir exists **and** kuzu importable; else 1a BFS |
| `memory` | Force 1a BFS |
| `kuzu` | Require Kuzu DB + package; else error (do not silent-fallback) |

Kuzu query: directed multi-hop along filtered relationship types (map `kind` to a property on REL). Exact Cypher is an implementation detail; must match 1a BFS semantics for the same depth/kinds on a synced snapshot (acceptance: same node id set for a fixture).

### Accept

- Sync without network; query `--backend kuzu` returns depth-2 follows.
- Default install unchanged (no kuzu).
- `graph rebuild` unchanged (still writes graph.json + wikilinks).

---

## Embeddings C — providers

### Factory

```python
def open_embedder(name: str, **kwargs) -> EmbeddingProvider: ...
```

| name | Extra | Notes |
|------|-------|--------|
| `hash` | none | Tests / CI; default when no ML extra and user passes `--embed-provider hash` |
| `local` | `search-ml` | sentence-transformers; default model e.g. `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` (Chinese-friendly); override `--embed-model` |
| `http` | none beyond `requests` (already dep) | OpenAI-compatible `POST {base}/embeddings`; needs `--embed-api-base`, `--embed-api-key` (env `ZHIHU_EMBED_API_KEY` ok), `--embed-model` |

### CLI

```bash
python -m zhihu_backup search index \
  --vector-backend chroma \
  --embed-provider local|http|hash \
  [--embed-model ...] \
  [--embed-api-base ...] \
  [--embed-api-key ...] \
  --json

python -m zhihu_backup search semantic "..." --embed-provider local ...
```

Resolution for `--embed-provider` when **omitted**:

1. If `search-ml` importable → `local`
2. Else → **fail** with hint to install `[search-ml]` or pass `--embed-provider hash` / `http`  
   (Do **not** silently use hash in production CLI — same posture as vector backend.)

Manifest already stores `model_id` + `dimensions`; switching provider/model forces clear+reindex (existing behavior).

### Packaging

```toml
[project.optional-dependencies]
chroma = ["chromadb>=0.5"]
kuzu = ["kuzu>=0.4"]
search-ml = ["sentence-transformers>=3.0"]
```

Keep extras independent: chroma ≠ search-ml ≠ kuzu.

### Accept

- `hash` still works for CI without extras.
- `local` with extra: index + semantic on fixture (may be slow; mark optional/heavy test).
- `http`: unit-test with mocked `requests`; live test optional/manual.
- Missing `local` without flag → non-zero install hint.

---

## Implementation order

1. Embeddings C (`open_embedder`, local + http + CLI flags) — unblocks real semantic search  
2. Phase 1b Kuzu sync + query backend flag  

(Or reverse if graph Cypher is higher priority; default: embeddings first.)

## Out of scope

- Auto graph sync / search index after backup  
- Social `--max-depth` BFS crawl  
- Author edges  
- BM25 hybrid  
