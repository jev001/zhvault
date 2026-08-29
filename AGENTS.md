# AGENTS.md — Zhihu Backup

## Goal

Backup Zhihu collections / pins / asked questions / followed questions / votes into local text + assets, with pluggable state engines and incremental resume.

## Layout

```
data/
  contents/{collections|pins|asked_questions|followed_questions|votes}/{owner_id}/{type}_{parent?}_{zhihu_id}.md
  assets/{sha16}{ext}
  meta/{sqlite|json|rocksdb}/...
```

- Filenames: `{type}_{parent_id}_{zhihu_id}.md` when parent exists (e.g. `answer_{qid}_{aid}`), else `{type}_{zhihu_id}.md` (no Chinese)
- Meta key: `{type}:{parent_id}:{zhihu_id}` or `{type}:{zhihu_id}`
- State engines: `--engine sqlite|json|rocksdb` (rocksdb is a file-backed stub in MVP)

## Commands

```bash
python -m zhihu_backup auth set-cookie Cookies.json
python -m zhihu_backup status --json
python -m zhihu_backup backup --source collection --json
python -m zhihu_backup resume --json
```

Useful flags: `--data-dir`, `--engine`, `--source`, `--full`, `--collection-id`, `--x-zse-96`, `--json`.

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
- `--engine json` behaves like sqlite for the same contents tree
- `status --json` / `backup --json` parse with `jq`
- New content filenames contain no Chinese
