# Hard invariants (zhvault) — Python

These are non-negotiable for agents and humans. Enforced by review + `make gate` + `tests/test_harness_invariants.py` where noted.

1. **StorageEngine only** — Persist backup/meta state via `StorageEngine` (`sqlite` / `json` / `rocksdb`). Do not invent parallel index files (derived exports `graph.json` / vectors / kuzu are explicit exceptions under `meta/`).
2. **No secrets in git** — Never commit `Cookies.json`, `data/meta/**` cookies/state secrets, or credentials.
3. **Incremental default** — Prefer resume/checkpoints; use `--full` only when explicitly required.
4. **Account mutate danger gate** — Zhihu write ops only via `account plan` (safe) then `account apply` with **both** `--i-understand-danger` and `--confirm APPLY`. Never auto-apply after backup.
5. **Write HTTP confinement** — Non-GET `ZhihuClient.request_json` call sites belong under `src/mutate/` only (AST-checked).
6. **`src/` import root** — Code under `src/`; imports are top-level (`cli`, `storage`, …). No `src/zhvault` / `src/zhihu_backup` package dirs. Do not extend `legacy/Main.py`.
7. **Content filenames** — `{type}_{parent?}_{zhihu_id}.md` using ASCII business IDs only (no Chinese in paths). Titles may be Chinese; IDs must not be.
8. **`--source all`** — Does not include social (`following` / `followers`); run `--source social` explicitly.
9. **Graph rebuild / search index / kuzu sync** — Manual derived steps; not implicit after every backup.
10. **Harness gate files** — Keep `ruff.toml` (non-empty lint select), `.github/workflows/harness-gate.yml`, and `tests/test_harness_invariants.py`.
