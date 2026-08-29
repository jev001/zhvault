# Agent runbook

1. `python -m zhihu_backup status --json`
2. If `cookie_present` is false: `python -m zhihu_backup auth set-cookie Cookies.json --json`
3. Ensure `url.json` has collection URLs (or pass `--collection-id`).
4. `python -m zhihu_backup backup --source all --json`
5. On interrupt: `python -m zhihu_backup resume --json`
6. Read final `{"event":"summary",...}` for counts.
