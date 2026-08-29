# Operations runbook (confirmed)

Commands use placeholders only (`<url_token>`).

## One-time setup

```bash
make sync
pre-commit install
```

## Daily green

```bash
make gate          # required: ruff + full pytest
# optional helpers:
make lint
make test
```

Do **not** use `git commit --no-verify` ([anti-bypass](../anti-bypass.md)).

## Backup — self

```bash
zhvault status --json
zhvault auth set-cookie Cookies.json --json   # if cookie_present false
# collections: url.json and/or --collection-id
zhvault backup --source collection --json
zhvault backup --source all --json            # excludes social
zhvault backup --source social --json         # following + followers
zhvault resume --json                         # after interrupt
```

## Backup — other member

```bash
zhvault backup --source people --user <url_token> --json
zhvault backup --source people --user /<url_token> --json
zhvault backup --source answer --user https://www.zhihu.com/people/<url_token> --json
```

Behavior locked in code:

1. Parse token from REF (token, `/token`, `people/token`, full URL).
2. `GET /api/v4/members/{token}` — fail closed if missing.
3. Ignore `url.json` collections unless `--collection-id` is passed.
4. Member list HTTP 404 (e.g. private votes) → soft skip; does not inflate `source_errors`.

## Deploy / cron

```bash
./deploy/run.sh              # list jobs
./deploy/run.sh backup
./deploy/run.sh people       # requires user= in deploy/zhvault.ini
ZHVAULT_INI=/path/other.ini ./deploy/run.sh status
```

Locks: `data/run/{job}.pid` (removed on exit).

## Cleanup

```bash
make clean         # build artifacts
make clean-cache   # + tool caches
make clean-all     # + .venv (then make sync)
```

## Derived offline (manual)

```bash
zhvault graph rebuild --json
zhvault graph sync --backend kuzu --json
zhvault search index --json
```

Not run automatically after `backup` / `resume`.

## Agent completion checklist

1. Behavior matches this runbook + [flows.md](./flows.md).
2. `make gate` exit 0 ([verify](../verify.md)).
3. No secrets (`Cookies.json`, `data/meta/**`) committed.
4. If ops flows changed, update `docs/harness/ops/` in the same PR.
