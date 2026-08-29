# Real Embeddings (local + http) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Pluggable `open_embedder(local|http|hash)`; wire CLI `--embed-provider` / model / API flags; optional `[search-ml]` extra. Never silent-hash when provider omitted.

**Architecture:** Extend `zhihu_backup/search/embed.py` with factory + two providers; CLI resolves embedder like vector backend. Manifest `model_id`/`dimensions` already force reindex.

**Tech Stack:** existing `requests`; optional `sentence-transformers>=3.0`.

**Spec:** [docs/superpowers/specs/2026-08-29-kuzu-embeddings-design.md](../specs/2026-08-29-kuzu-embeddings-design.md) Embeddings C only.

## Global Constraints

- Extras independent: `search-ml` ≠ `chroma` ≠ `kuzu`.
- Omitted `--embed-provider`: local if importable else fail with install hint (never silent hash).
- Explicit `hash` allowed for CI.
- `http` uses OpenAI-compatible embeddings API; key from flag or `ZHIHU_EMBED_API_KEY`.
- Default install unchanged (no sentence-transformers).

## File map

| Path | Role |
|------|------|
| `zhihu_backup/search/embed.py` | Protocol, Hash, Local, Http, `open_embedder`, `EmbedderError` |
| `zhihu_backup/cli.py` | resolve + flags on search index/semantic |
| `pyproject.toml` | `search-ml` extra |
| `tests/test_embed_providers.py` | hash/local-missing/http-mock |
| `tests/test_cli_search.py` | provider resolution |
| `AGENTS.md` | document flags + extras |

---

### Task 1: open_embedder + Local + Http providers

**Files:** `embed.py`; `tests/test_embed_providers.py`; `pyproject.toml`

**Interfaces:**

```python
class EmbedderError(RuntimeError): ...

def open_embedder(
    name: str,
    *,
    model: str | None = None,
    api_base: str | None = None,
    api_key: str | None = None,
) -> EmbeddingProvider: ...
```

- `hash` → `HashEmbeddingProvider`
- `local` → import sentence_transformers; default model `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`; `model_id` = model string; `dimensions` from first encode or model config
- `http` → POST `{api_base.rstrip('/')}/embeddings` with `{"model", "input": texts}`; Bearer key; parse `data[].embedding`
- ImportError on local → `EmbedderError` with `zhihu-backup[search-ml]`

- [ ] **Step 1:** Failing tests — open hash; open local with monkeypatched ImportError; open http with mocked requests returning 2-dim vectors; unknown name raises
- [ ] **Step 2:** Implement + `[project.optional-dependencies] search-ml = ["sentence-transformers>=3.0"]`
- [ ] **Step 3:** Commit `feat: add local and http embedding providers`

---

### Task 2: CLI wiring + AGENTS

**Files:** `cli.py`, `AGENTS.md`, extend `tests/test_cli_search.py`

**Resolve `--embed-provider` when None:**

```python
def resolve_embed_provider(explicit: str | None) -> str:
    if explicit:
        return explicit
    try:
        import sentence_transformers  # noqa: F401
        return "local"
    except ImportError:
        raise SystemExit / return error "install zhihu-backup[search-ml] or pass --embed-provider hash|http"
```

Flags on `search index` and `search semantic`:
- `--embed-provider` choices hash|local|http
- `--embed-model`
- `--embed-api-base`
- `--embed-api-key` (default from env)

Replace hardcoded `HashEmbeddingProvider()` with `open_embedder(...)`.

- [ ] **Step 1:** CLI tests — omit provider without ST → exit non-zero; `--embed-provider hash` works with memory; http mock path optional
- [ ] **Step 2:** AGENTS commands + extras note
- [ ] **Step 3:** Commit `feat: wire --embed-provider for search CLI`

---

## Spec coverage

| Requirement | Task |
|-------------|------|
| open_embedder local/http/hash | 1 |
| search-ml extra | 1 |
| no silent hash default | 2 |
| CLI flags + AGENTS | 2 |
