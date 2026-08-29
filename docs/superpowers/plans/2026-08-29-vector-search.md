# Vector Search (Phase 2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Pluggable semantic search over backed-up markdown: chunk → embed → `VectorStore`; durable **optional Chroma** backend; always-available `memory` for tests.

**Architecture:** Protocols `VectorStore` + `EmbeddingProvider`; factory `open_vector_store`. CLI `search index` / `search semantic` with optional `--expand-graph` calling Phase 1a `query_graph`. Default install has no `chromadb`.

**Tech Stack:** Python 3.10+; optional extra `chroma` → `chromadb>=0.5`; stub/hash embedder for CI.

**Spec:** [docs/superpowers/specs/2026-08-29-graph-vector-indexes-design.md](../specs/2026-08-29-graph-vector-indexes-design.md) Phase 2. **Depends on:** Phase 1a `query_graph` for `--expand-graph` only (index/semantic work without it if expand omitted).

**Prerequisite:** Prefer merging [2026-08-29-graph-query.md](./2026-08-29-graph-query.md) first. If executing this plan alone, `--expand-graph` can be stubbed to error “graph query not available” until 1a lands — do not block VectorStore on Kuzu.

## Global Constraints

- Vector / graph indexes are derived; truth remains StorageEngine + contents.
- Node/doc ids = meta item keys; chunk id = `{item_key}#{chunk_index}`.
- `chromadb` only via optional extra; missing + `--vector-backend chroma` → non-zero + install hint.
- Never silently no-op indexing.
- Embedding provider separate from vector backend (test with hash embedder + memory/chroma).
- No Zhihu API in search commands; no writes to `graph_edges` from search index.
- Persist Chroma under `data/meta/{engine}/vectors/chroma/`; manifest at `vectors/manifest.json`.

## File map

| Path | Responsibility |
|------|----------------|
| `zhihu_backup/search/__init__.py` | exports |
| `zhihu_backup/search/types.py` | `VectorRecord`, `VectorHit` |
| `zhihu_backup/search/store.py` | `VectorStore` protocol + `open_vector_store` |
| `zhihu_backup/search/memory_store.py` | in-memory store |
| `zhihu_backup/search/chroma_store.py` | optional Chroma adapter |
| `zhihu_backup/search/embed.py` | `EmbeddingProvider` + `HashEmbeddingProvider` |
| `zhihu_backup/search/chunk.py` | markdown chunking |
| `zhihu_backup/search/index.py` | index orchestration + manifest |
| `zhihu_backup/cli.py` | `search` subcommands |
| `pyproject.toml` | `[project.optional-dependencies] chroma` |
| `tests/test_vector_store_*.py`, `test_search_*.py` | TDD |
| `AGENTS.md` | search commands + chroma extra |

---

### Task 1: Types + MemoryVectorStore + HashEmbeddingProvider

**Files:** create `zhihu_backup/search/{types,store,memory_store,embed}.py`; test `tests/test_vector_store_memory.py`

**Interfaces:**

```python
@dataclass
class VectorRecord:
    id: str
    vector: list[float]
    document: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

@dataclass
class VectorHit:
    id: str
    score: float
    document: str
    metadata: dict[str, Any]

class VectorStore(Protocol):
    name: str
    def upsert(self, records: Sequence[VectorRecord]) -> None: ...
    def delete(self, ids: Sequence[str]) -> None: ...
    def query(self, vector: Sequence[float], *, top_k: int = 10, where: Mapping[str, Any] | None = None) -> list[VectorHit]: ...
    def clear(self) -> None: ...

def open_vector_store(backend: str, root: Path) -> VectorStore: ...
```

`HashEmbeddingProvider`: map text → fixed-dim float vector via hashlib (deterministic); `model_id="hash-v1"`, `dimensions=32` (or 64).

`MemoryVectorStore`: brute-force cosine similarity; `where` equality on metadata keys.

- [ ] **Step 1: Failing tests** — upsert two records, query nearest, delete, clear; `open_vector_store("memory", path)` works; unknown backend raises.
- [ ] **Step 2: RED → implement → GREEN**
- [ ] **Step 3: Commit** `feat: add VectorStore protocol and memory backend`

---

### Task 2: Optional Chroma backend

**Files:** `zhihu_backup/search/chroma_store.py`; `pyproject.toml` extra; `tests/test_vector_store_chroma.py`

**Interfaces:**
- `ChromaVectorStore` implements `VectorStore`; persist_directory = `root / "chroma"`
- `open_vector_store("chroma", root)` imports chromadb; on `ImportError` raise `VectorBackendError` with message containing `pip install` / `zhihu-backup[chroma]`

- [ ] **Step 1: Test without chromadb** — calling open chroma raises with install hint (skip if chromadb installed in env — use monkeypatch to force ImportError).
- [ ] **Step 2: Test with chromadb** — mark `@pytest.mark.chroma` or skipif not importable; upsert/query round-trip.
- [ ] **Step 3: Add pyproject optional-dependencies**

```toml
[project.optional-dependencies]
chroma = ["chromadb>=0.5"]
```

- [ ] **Step 4: Commit** `feat: optional Chroma VectorStore backend`

---

### Task 3: Chunking + index orchestration + manifest

**Files:** `chunk.py`, `index.py`; `tests/test_search_chunk_index.py`

**Interfaces:**

```python
def chunk_markdown(text: str, *, max_chars: int = 1200, overlap: int = 100) -> list[str]: ...

def build_index(
    engine: StorageEngine,
    contents_root: Path,
    vectors_root: Path,
    *,
    store: VectorStore,
    embedder: EmbeddingProvider,
) -> dict[str, Any]:
    """Read items with path, chunk files, embed, upsert; write manifest.json; return stats."""
```

Manifest:

```json
{"model_id": "...", "dimensions": N, "backend": "memory|chroma", "updated_at": "...", "chunks": N}
```

If manifest `model_id`/`dimensions` mismatch current embedder → `clear()` then full reindex.

- [ ] **Step 1: Tests** — chunk splits long text; index fixture md files via memory+hash; manifest written; second index idempotent chunk count.
- [ ] **Step 2: Implement**
- [ ] **Step 3: Commit** `feat: chunk and index markdown into VectorStore`

---

### Task 4: CLI `search index|semantic` + expand-graph + AGENTS

**Files:** `cli.py`, `AGENTS.md`; `tests/test_cli_search.py`

**CLI:**

```bash
python -m zhihu_backup search index [--vector-backend chroma|memory] [--json]
python -m zhihu_backup search semantic QUERY [--top-k 10] [--vector-backend ...] [--expand-graph N] [--kind ...] [--json]
```

Resolve backend:
1. Explicit `--vector-backend`
2. Else if chroma importable → chroma
3. Else fail with install hint (do not default to memory in production CLI — memory only when explicitly requested)

`--expand-graph N`: for each hit `item_key` in metadata, `query_graph(..., depth=N)`; attach `neighbors` list on hit (best-effort).

- [ ] **Step 1: CLI tests** with memory backend + tmp data-dir
- [ ] **Step 2: Implement cmds + AGENTS** (note optional `[chroma]` extra)
- [ ] **Step 3: Commit** `feat: add search index and semantic CLI`

---

## Spec coverage (Phase 2)

| Requirement | Task |
|-------------|------|
| VectorStore protocol | 1 |
| memory always | 1 |
| chroma optional + install hint | 2 |
| EmbeddingProvider separate | 1, 3 |
| chunk + index + manifest | 3 |
| search CLI + expand-graph | 4 |
| no chromadb in default deps | 2 |

## Placeholder scan

No TBD; Kuzu / real sentence-transformers deferred per spec.
