# Zhihu Backup (`zhihu-backup`)

Backup Zhihu **collections / pins / asked questions / followed questions / votes** to local markdown + assets, with checkpoint resume and default incremental sync.

Based on [zanghuaren/ZhiHu-Collection-To-Markdown](https://github.com/zanghuaren/ZhiHu-Collection-To-Markdown) (legacy `Main.py` kept for reference).

## Install

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

## Configure

1. Put cookies in `Cookies.json` (same format as before; convert browser curl → JSON).
2. Put collection URLs in `url.json`:

```json
{
  "collections": [
    {"url": "https://www.zhihu.com/collection/123456", "path": "ignored-by-new-cli"}
  ]
}
```

Optional: pass `--x-zse-96` if Zhihu requires it.

## Usage

```bash
python -m zhihu_backup auth set-cookie Cookies.json
python -m zhihu_backup status --json
python -m zhihu_backup backup --source collection
python -m zhihu_backup backup --source all --engine sqlite
python -m zhihu_backup resume
```

Engines: `sqlite` (default), `json`, `rocksdb` (MVP file-backed stub).

## Data layout

```
data/contents/.../{type}_{parent?}_{zhihu_id}.md
data/assets/{sha16}{ext}
data/meta/{engine}/...
```

Filenames: `{type}_{parent_id}_{zhihu_id}.md` when parent exists (e.g. `answer_{qid}_{aid}`), else `{type}_{zhihu_id}.md`. Meta key: `{type}:{parent_id}:{zhihu_id}` or `{type}:{zhihu_id}`.

## Agents

See `AGENTS.md`, `.cursor/rules/zhihu-backup.mdc`, and `docs/agent-runbook.md`.

## Legacy

`Main.py` still exports a single collection list to title-based markdown. Prefer `zhihu_backup` for new runs.

## Disclaimer

Technical research only. Respect Zhihu ToS; no commercial misuse.
