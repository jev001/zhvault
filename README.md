# zhvault

Backup Zhihu **collections / pins / asked questions / followed questions / votes** to local markdown + assets, with checkpoint resume and default incremental sync.

Based on [zanghuaren/ZhiHu-Collection-To-Markdown](https://github.com/zanghuaren/ZhiHu-Collection-To-Markdown) (upstream single-file script quarantined under `legacy/`).

## Install

Prefer [uv](https://docs.astral.sh/uv/):

```bash
uv sync --extra dev
source .venv/bin/activate   # optional; or use: uv run zhvault ...
```

Or classic venv + pip:

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

## Deploy runner (ini + pid lock)

Cron/systemd-friendly wrapper. Config: `deploy/zhvault.ini`. Locks: `data/run/{job}.pid` (removed on exit; blocks duplicate runs).

```bash
./deploy/run.sh              # list jobs
./deploy/run.sh backup       # zhvault backup per [run.backup]
./deploy/run.sh resume
ZHVAULT_INI=/path/other.ini ./deploy/run.sh status
```

## Usage

```bash
zhvault auth set-cookie Cookies.json
zhvault status --json
zhvault backup --source collection
zhvault backup --source all --engine sqlite
zhvault resume
```

(`zhihu-backup` remains as a deprecated script alias.)

Engines: `sqlite` (default), `json`, `rocksdb` (`rocks` alias; needs `pip install 'zhvault[rocksdb]'`).

## Development

Layout (Django-style): `src/` = installable code; `tests/` = suite at repo root.

Agent / vibe constraints: [HARNESS.md](HARNESS.md) (taxonomy: python / frontend / build / config under `docs/harness/`).

```bash
make sync       # uv sync --extra dev (falls back to pip)
make sync-all   # all optional extras (chroma/kuzu/rocksdb/…)
pre-commit install
make gate       # required green: ruff + full pytest
make build
make clean      # dist/build/egg-info; clean-cache += caches; clean-all += .venv
uv run zhvault status --json
```

## Data layout

```
data/contents/.../{type}_{parent?}_{zhihu_id}.md
data/assets/{sha16}{ext}
data/meta/{engine}/...
```

Filenames: `{type}_{parent_id}_{zhihu_id}.md` when parent exists (e.g. `answer_{qid}_{aid}`), else `{type}_{zhihu_id}.md`. Meta key: `{type}:{parent_id}:{zhihu_id}` or `{type}:{zhihu_id}`.

## Agents

See `HARNESS.md`, `AGENTS.md`, `.cursor/rules/zhvault.mdc`, and `docs/agent-runbook.md`.

## Legacy

The upstream `Main.py` lives in `legacy/` for historical reference only; it is unsupported. Use `zhvault` and `src/` for all runs and development.

## Disclaimer

Technical research only. Respect Zhihu ToS; no commercial misuse.
