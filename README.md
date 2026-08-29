# zhvault

Backup Zhihu **collections / pins / asked questions / followed questions / votes** to local markdown + assets, with checkpoint resume and default incremental sync.

Based on [zanghuaren/ZhiHu-Collection-To-Markdown](https://github.com/zanghuaren/ZhiHu-Collection-To-Markdown) (legacy `Main.py` kept for reference).

## Install

```bash
python -m venv .venv
source .venv/bin/activate
make sync
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
zhvault auth set-cookie Cookies.json
zhvault status --json
zhvault backup --source collection
zhvault backup --source all --engine sqlite
zhvault resume
```

(`zhihu-backup` remains as a deprecated script alias.)

Engines: `sqlite` (default), `json`, `rocksdb` (MVP file-backed stub).

## Development

Code lives under `src/` as the setuptools import root (imports are `cli`, `storage`, … — not `import zhvault`).

```bash
make sync    # editable install + dev deps
make test
make lint
make build   # wheel with zhvault console script
```

## Data layout

```
data/contents/.../{type}_{parent?}_{zhihu_id}.md
data/assets/{sha16}{ext}
data/meta/{engine}/...
```

Filenames: `{type}_{parent_id}_{zhihu_id}.md` when parent exists (e.g. `answer_{qid}_{aid}`), else `{type}_{zhihu_id}.md`. Meta key: `{type}:{parent_id}:{zhihu_id}` or `{type}:{zhihu_id}`.

## Agents

See `AGENTS.md`, `.cursor/rules/zhvault.mdc`, and `docs/agent-runbook.md`.

## Legacy

`Main.py` still exports a single collection list to title-based markdown. Prefer `zhvault` for new runs.

## Disclaimer

Technical research only. Respect Zhihu ToS; no commercial misuse.
