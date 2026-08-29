# Zhihu Backup CLI Implementation Plan

> **For agentic workers:** Execute task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Build `zhihu-backup` CLI: backup collections/pins/asked/followed/votes with contents+assets, pluggable engines, checkpoint + incremental, agent `--json` scaffold.

**Architecture:** CLI → Sources → Pipeline → StorageEngine → `data/{contents,assets,meta}/`

**Tech Stack:** Python 3.10+, requests, html2text, PyYAML, sqlite3; JSON engine; RocksDB stub

## Global Constraints

- Filenames: `type_{zhihu_id}` only (no Chinese)
- Contents dir name: `contents` (not `md`/`docs`)
- Default incremental; `--full` for full validate
- Cookie in meta engine, never commit
- MVP: no Zhihu-side cleanup, no x-zse-96 auto, no GUI

---

### Task 1: Scaffold + SQLite engine

- [ ] Package layout under `zhihu_backup/`
- [ ] `StorageEngine` protocol + sqlite impl
- [ ] pyproject / requirements update

### Task 2: Writers + models

- [ ] ContentWriter: path + frontmatter
- [ ] AssetWriter: sha16 + URL map
- [ ] Shared models (ItemKey, Checkpoint, etc.)

### Task 3: Collection source + pipeline

- [ ] Port Main.py paging/HTML→MD/images
- [ ] Checkpoint + incremental decide
- [ ] Tests for skip/update logic

### Task 4: Other sources

- [ ] pins, asked_questions, followed_questions, votes

### Task 5: CLI + engines + agents

- [ ] backup/resume/status/auth + `--json`
- [ ] json engine + rocks stub
- [ ] AGENTS.md + `.cursor/rules` + README

### Verify

- Second run mostly skip
- resume from offset
- `--engine json` parity
- `status --json` jq-able
- no Chinese filenames
