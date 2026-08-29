# AGENTS.md — Zhihu Backup

## Goal

Backup Zhihu collections / pins / asked questions / followed questions / votes / social graph (following & followers) into local text + assets, with pluggable state engines and incremental resume.

## Layout

```
data/
  contents/{collections|pins|asked_questions|followed_questions|votes}/{owner_id}/{type}_{parent?}_{zhihu_id}.md
  contents/people/{url_token}.md
  assets/{sha16}{ext}
  meta/{sqlite|json|rocksdb}/...
  meta/{sqlite|json|rocksdb}/graph.json   # derived export (graph rebuild only)
```

- Filenames: `{type}_{parent_id}_{zhihu_id}.md` when parent exists (e.g. `answer_{qid}_{aid}`), else `{type}_{zhihu_id}.md` (no Chinese)
- Meta key: `{type}:{parent_id}:{zhihu_id}` or `{type}:{zhihu_id}`
- Frontmatter + `items.extra`: typed business IDs (`answer_id`/`question_id`, `article_id`/`column_id`, …) via `business_extra`
- Assets: global `assets(url→path)` for dedupe; `item_assets(item_key, asset_url)` links content to resources
- State engines: `--engine sqlite|json|rocksdb` (rocksdb is a file-backed stub in MVP)

## Commands

```bash
python -m zhihu_backup auth set-cookie Cookies.json
python -m zhihu_backup status --json
python -m zhihu_backup backup --source collection --json
python -m zhihu_backup backup --source social --json
python -m zhihu_backup resume --json
python -m zhihu_backup graph rebuild --json
python -m zhihu_backup graph edge add --from user:a --to user:b
python -m zhihu_backup graph edge remove --from user:a --to user:b
```

Useful flags: `--data-dir`, `--engine`, `--source`, `--full`, `--collection-id`, `--x-zse-96`, `--asset-workers`, `--json`.

Social / graph notes:

- `--source all` does **not** include `following` / `followers`; run `--source social` explicitly.
- `graph rebuild` is **manual only** (not run after `backup` / `resume`); offline from stored items + membership + persisted `graph_edges`.
- `--max-depth` defaults to `1`; values other than `1` are rejected (multi-hop crawl reserved for later).

`--json`: events/summary on stdout; logs on stderr. Agent flow: `status --json` → auth if needed → `backup --json` → read `event=summary`.

## Rules for AI agents

1. Persist state only via `StorageEngine` (do not invent parallel index files).
2. Prefer incremental; use `--full` only when explicitly required.
3. Never commit `Cookies.json` / `data/meta/**` secrets.
4. Do not implement Zhihu-side delete/uncollect in MVP.
5. Keep `Main.py` as reference until migration is complete; new work goes in `zhihu_backup/`.
6. Design/plan docs: `docs/superpowers/specs/`, `docs/superpowers/plans/`.

## Verify

- Same collection twice → second run mostly `skipped`
- Interrupt then `resume` continues from checkpoint offset
- One source HTTP 403 → `source_error` + continue other sources (`stats.source_errors`); try `--x-zse-96` if browser works
- `--engine json` behaves like sqlite for the same contents tree
- `status --json` / `backup --json` parse with `jq`
- New content filenames contain no Chinese
- `backup --source social` writes `contents/people/{url_token}.md` and upserts `follows` edges (`origin=api`)
- `graph rebuild --json` → `meta/.../graph.json` with derived content edges + wikilinks in people MD
- `graph edge add|remove` persists `origin=manual` edges (survive social sync)
- `--max-depth 2` → exit 2 + clear error (MVP depth = 1 only)
