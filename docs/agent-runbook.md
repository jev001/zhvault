# Agent runbook

Prerequisite: `make sync` (editable install; provides `zhvault` on PATH). Once per clone: `pre-commit install`.

1. `zhvault status --json`
2. If `cookie_present` is false: `zhvault auth set-cookie Cookies.json --json`
3. Ensure `url.json` has collection URLs (or pass `--collection-id`).
4. `zhvault backup --source all --json`
5. On interrupt: `zhvault resume --json`
6. Read final `{"event":"summary",...}` for counts.

**Green gate (required before claiming done):** `make gate`  
See [HARNESS.md](../HARNESS.md) (protocol taxonomy), [harness/verify.md](./harness/verify.md), and [harness/build/gate.md](./harness/build/gate.md). Do not bypass hooks or invent fake tests.
