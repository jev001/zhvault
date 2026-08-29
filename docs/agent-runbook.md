# Agent runbook

Prerequisite: `make sync` (editable install; provides `zhvault` on PATH).

1. `zhvault status --json`
2. If `cookie_present` is false: `zhvault auth set-cookie Cookies.json --json`
3. Ensure `url.json` has collection URLs (or pass `--collection-id`).
4. `zhvault backup --source all --json`
5. On interrupt: `zhvault resume --json`
6. Read final `{"event":"summary",...}` for counts.

Dev checks: `make test`, `make lint`.
