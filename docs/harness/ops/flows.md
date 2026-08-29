# Confirmed flowcharts

Placeholders only (`<url_token>`); never document real Zhihu handles.

## 1. Green gate (required before claiming done)

```mermaid
flowchart TD
  start[Task code complete] --> gate["make gate"]
  gate -->|exit 0| ok[Claim done / open PR]
  gate -->|fail| fix[Fix root cause]
  fix --> gate
  bypass["git commit --no-verify"] -.->|forbidden| anti[anti-bypass.md]
  gate -.->|CI| ci[harness-gate workflow]
```

## 2. Backup — logged-in self (default)

```mermaid
flowchart TD
  sync["make sync + pre-commit install"] --> status["zhvault status --json"]
  status -->|no cookie| auth["zhvault auth set-cookie Cookies.json"]
  auth --> status
  status -->|ok| cfg["url.json and/or --collection-id"]
  cfg --> backup["zhvault backup --source all|collection|... --json"]
  backup -->|interrupt| resume["zhvault resume --json"]
  resume --> summary["event=summary"]
  backup --> summary
```

Notes:

- `--source all` does **not** include following/followers; use `--source social` explicitly.
- Collections come from `url.json` / `--collection-id` when **no** `--user`.

## 3. Backup — other profile (`--user`)

```mermaid
flowchart TD
  cmd["zhvault backup --source people --user REF --json"] --> parse["parse_people_ref\n token | /token | people/token | URL"]
  parse -->|invalid| err2[exit 2]
  parse --> verify["GET /api/v4/members/token"]
  verify -->|404/error| err2
  verify --> ignore["Ignore url.json collections\n unless --collection-id"]
  ignore --> discover["Discover member collections if needed"]
  discover --> sources["Sources: activity answer zvideo asked\n article column pin following followers\n + collections"]
  sources --> run[Pipeline]
  run -->|list HTTP 404| soft["source_unavailable\n soft skip no source_errors"]
  run --> summary["event=summary user=token"]
```

Recommended command:

```bash
zhvault backup --source people --user <url_token> --json
# also OK: --user /<url_token>  or  --user https://www.zhihu.com/people/<url_token>
```

## 4. Deploy runner (ini + pid lock)

```mermaid
flowchart TD
  invoke["./deploy/run.sh JOB"] --> ini["Read deploy/zhvault.ini\n ZHVAULT_INI override"]
  ini --> lock{"data/run/JOB.pid\n live process?"}
  lock -->|yes| fail[exit 1 already running]
  lock -->|stale/missing| write[Write pid + trap cleanup]
  write --> zh["uv run zhvault ...\n --user from ini if set"]
  zh --> done[Remove pid on EXIT]
```

## 5. Layered make clean

```mermaid
flowchart LR
  clean["make clean\n dist build egg-info"] --> cache["make clean-cache\n + pytest/ruff/pycache"]
  cache --> all["make clean-all\n + .venv"]
```

Never deletes `data/` or `Cookies.json`.
