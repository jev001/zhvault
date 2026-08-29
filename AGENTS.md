# AGENTS.md — zhvault

## Goal

Backup Zhihu collections / pins / asked questions / followed questions / votes / social graph (following & followers) into local text + assets, with pluggable state engines and incremental resume.

## Project layout

- **CLI / project name:** `zhvault` (console script). Deprecated alias: `zhihu-backup` only — no `python -m zhihu_backup`.
- **Code:** lives under `src/` as the setuptools import root. Imports are top-level (`cli`, `storage`, `mutate`, …) — not `import zhvault` or `import zhihu_backup`.
- **Dev:** `make sync` (editable install), `make test`, `make lint`, `make build`.

## Data layout

```
data/
  contents/{collections|pins|asked_questions|followed_questions|votes}/{owner_id}/{type}_{parent?}_{zhihu_id}.md
  contents/people/{url_token}.md
  assets/{sha16}{ext}
  meta/{sqlite|json|rocksdb}/...
  meta/{sqlite|json|rocksdb}/graph.json   # derived export (graph rebuild only)
  meta/{sqlite|json|rocksdb}/vectors/     # search index (manifest + chroma|memory)
```

- Filenames: `{type}_{parent_id}_{zhihu_id}.md` when parent exists (e.g. `answer_{qid}_{aid}`), else `{type}_{zhihu_id}.md` (no Chinese)
- Meta key: `{type}:{parent_id}:{zhihu_id}` or `{type}:{zhihu_id}`
- Frontmatter + `items.extra`: typed business IDs (`answer_id`/`question_id`, `article_id`/`column_id`, …) via `business_extra`
- Assets: prefer original zhimg URLs (strip `_720w` etc.); meta stores `source_url`/`origin_url`; default MD uses HTML comments + Obsidian `![[assets/{file}]]` plus frontmatter `assets: [{file,path,source,origin}]`. Override with `--asset-link rel|wikilink|assets-root`. Vault/site root = `data/` for Obsidian / Hexo / Next (`public/assets`).
- State engines: `--engine sqlite|json|rocksdb` (rocksdb is a file-backed stub in MVP)

## Commands

```bash
make sync   # once: editable install + dev deps

zhvault auth set-cookie Cookies.json
zhvault status --json
zhvault backup --source collection --json
zhvault backup --source social --json
zhvault resume --json
zhvault graph rebuild --json
zhvault graph sync --backend kuzu --json
zhvault graph query --from user:me --depth 2 --kind follows --json
zhvault graph query --from user:me --depth 2 --backend auto --json
zhvault graph query --from user:me --depth 2 --backend memory --json
zhvault graph query --from user:me --depth 2 --backend kuzu --json
zhvault graph edge add --from user:a --to user:b
zhvault graph edge remove --from user:a --to user:b
zhvault search index --json
zhvault search index --embed-provider hash --vector-backend memory --json
zhvault search semantic "query" --top-k 10 --json
zhvault search semantic "query" --embed-provider local --json
zhvault search semantic "query" --expand-graph 1 --kind follows --json
zhvault account plan --mode prune --source following,collection,followed --json
zhvault account plan --mode migrate --from-data-dir ../a/data --source following,collection --json
# DANGER — live Zhihu writes; requires stacked confirmations:
zhvault account apply --plan plan.json --i-understand-danger --confirm APPLY --json
```

Useful flags: `--data-dir`, `--engine`, `--source`, `--full`, `--collection-id`, `--x-zse-96`, `--asset-workers`, `--asset-link`, `--json`, `--vector-backend`, `--embed-provider`, `--embed-model`, `--embed-api-base`, `--embed-api-key`, `--from-data-dir`, `--map-collection`, `--i-understand-danger`, `--confirm`.

Optional extras:
- `pip install 'zhvault[chroma]'` — durable Chroma vector index. Default `--vector-backend` is chroma when importable; otherwise the CLI fails with an install hint (pass `--vector-backend memory` only for tests).
- `pip install 'zhvault[search-ml]'` — local embeddings via sentence-transformers. Omitted `--embed-provider` defaults to `local` when importable; otherwise the CLI fails with an install hint (pass `--embed-provider hash` for CI/tests, or `http` with `--embed-api-base` / `--embed-model`; API key from `--embed-api-key` or `ZHIHU_EMBED_API_KEY`).
- `pip install 'zhvault[kuzu]'` — optional Kuzu derived graph index at `meta/{engine}/graph_query/kuzu/`. `graph sync --backend kuzu` builds it; `graph query --backend kuzu` requires sync (no silent fallback). `--backend auto` uses Kuzu when synced and importable, else in-memory BFS; `--backend memory` always BFS.

Social / graph notes:

- `--source all` does **not** include `following` / `followers`; run `--source social` explicitly.
- `graph rebuild` is **manual only** (not run after `backup` / `resume`); offline from stored items + membership + persisted `graph_edges`.
- `graph query` is offline BFS over unified edges (derived + persisted); `--json` prints the query result dict (nodes + edges). `--backend auto|memory|kuzu` selects in-memory BFS vs synced Kuzu index.
- `graph sync --backend kuzu` writes derived index to `meta/{engine}/graph_query/kuzu/` (offline; does not mutate `graph_edges`).
- `--max-depth` defaults to `1`; values other than `1` are rejected (multi-hop crawl reserved for later).

`--json`: events/summary on stdout; logs on stderr. Agent flow: `status --json` → auth if needed → `backup --json` → read `event=summary`.

## Rules for AI agents

1. Persist state only via `StorageEngine` (do not invent parallel index files).
2. Prefer incremental; use `--full` only when explicitly required.
3. Never commit `Cookies.json` / `data/meta/**` secrets.
4. Zhihu-side follow/unfollow / collect/uncollect / question follow only via `account plan` (safe) + `account apply` with `--i-understand-danger` and `--confirm APPLY`. Never auto-write after backup.
5. Keep `Main.py` as reference until migration is complete; new work goes in `src/` (top-level modules under the import root).
6. Design/plan docs: `docs/superpowers/specs/`, `docs/superpowers/plans/`.

## Verify

- `make test` and `make lint` pass after changes
- Same collection twice → second run mostly `skipped`
- Interrupt then `resume` continues from checkpoint offset
- One source HTTP 403 → `source_error` + continue other sources (`stats.source_errors`); try `--x-zse-96` if browser works
- `--engine json` behaves like sqlite for the same contents tree
- `status --json` / `backup --json` parse with `jq`
- New content filenames contain no Chinese
- `backup --source social` writes `contents/people/{url_token}.md` and upserts `follows` edges (`origin=api`)
- `graph rebuild --json` → `meta/.../graph.json` with derived content edges + wikilinks in people MD
- `graph query --from user:me --depth 2 --kind follows --json` → jq-friendly subgraph (no network)
- `graph edge add|remove` persists `origin=manual` edges (survive social sync)
- `--max-depth 2` → exit 2 + clear error (MVP depth = 1 only)
- `search index --json` writes `meta/{engine}/vectors/` (manifest + backend store); second run upserts same chunk ids
- `search semantic QUERY --json` returns hits with `item_key` / score / path (offline; requires matching embed provider used at index time)
- `search semantic ... --expand-graph N` attaches `neighbors` from `query_graph` per hit (best-effort)
- Missing chromadb and no `--vector-backend memory` → non-zero + `pip install 'zhvault[chroma]'`
- Missing `--embed-provider` and no sentence-transformers → non-zero + `pip install 'zhvault[search-ml]'` or pass `--embed-provider hash|http`
- `graph sync --backend kuzu` without kuzu package → non-zero + `pip install 'zhvault[kuzu]'`
- `graph query --backend kuzu` without prior sync → non-zero (no silent fallback to memory)
- `graph query --backend memory` matches BFS on unified edges (same as pre-kuzu behavior)
- `account plan` emits plan JSON with fingerprint; never POST/DELETE
- `account apply` without both danger flags → non-zero, no writes; stale fingerprint → abort
