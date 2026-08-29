# Zhihu Backup Tool — Design

**Date:** 2026-08-29  
**Status:** Approved

## Goal

CLI package `zhihu-backup` that backs up Zhihu collections, pins (ideas), asked questions, followed questions, and votes. Body text lives in markdown files; attachments in an assets directory. Pluggable state engines (SQLite / JSON / RocksDB). Checkpoint resume + default incremental sync. Agent-friendly scaffolding (`AGENTS.md`, `--json` CLI).

## Non-goals (MVP)

- Zhihu-side cleanup (uncollect / delete)
- Auto-refresh of `x-zse-96`
- GUI
- Full RocksDB production hardening (stub acceptable)

## Layout

```
data/
  contents/{collections|pins|asked_questions|followed_questions|votes}/{owner_id}/{type}_{zhihu_id}.md
  assets/{sha16}{ext}
  meta/{sqlite|json|rocksdb}/...
```

- Filenames: `type_{zhihu_id}` only (no Chinese titles)
- Frontmatter: `id`, `type`, `url`, `created`, `modified`, `sources[]`, title (display only)
- Sidecar index in meta engine: membership, dates, incremental fields

## Architecture

```
CLI (backup|resume|status|auth)
  → Source adapters
  → Pipeline: fetch → decide(skip|update|new) → write contents/assets → checkpoint
  → StorageEngine (sqlite|json|rocksdb)
```

### Incremental

- Stable key: `type:zhihu_id` (e.g. `answer:123`)
- Skip body/images when remote `updated_at` unchanged
- Default mode: incremental; `--full` forces re-validate
- Orphaned remote removals: keep local, mark `orphaned`

### Checkpoint

- Key: `(source, source_id)` → `{offset, updated_at}`
- Commit after each successful page
- Per-item failures go to `failed_items`; do not advance past uncommitted page on engine write failure

## StorageEngine API

- `get/set_cookie`
- `get/set_checkpoint(source, source_id)`
- `upsert_item` / `get_item`
- `link_membership`
- `list_by` / `status_summary`
- `record_failed` / asset URL map

Default engine: **sqlite**. Switch via `--engine json|rocksdb`.

## CLI

| Command | Notes |
|---------|--------|
| `backup` | `--source`, `--engine`, `--full`, `--json`, `--data-dir` |
| `resume` | Continue from checkpoints |
| `status` | Progress / cookie / counts; `--json` |
| `auth set-cookie` | Store cookie in meta (not git) |

`--json`: machine-readable events/summary on stdout; logs on stderr.

## Agents scaffold

- `AGENTS.md` — goals, layout, commands, prohibitions, verify steps
- `.cursor/rules/zhihu-backup.mdc` — StorageEngine boundary, naming, incremental-first
- Optional runbook under `docs/`

## Migration from Main.py

Reuse: collection API paging, HTML→MD, image download/MIME.  
Drop: Chinese title filenames, frontmatter-only dedupe, stateful-less full scans.  
Keep `Main.py` until migration complete.
