# Optional Live Network Tests — Design

**Date:** 2026-08-30  
**Status:** Implemented (awaiting optional commit)

## Goal

Add **opt-in** tests that hit the real Zhihu API to validate list routes, profile resolve, and a minimal `--source people` backup — without letting flaky/external failures break `make gate` or turn every outage into a red `make test-live`.

## Decisions (locked)

| Topic | Choice |
|-------|--------|
| Enable | **D**: env `ZHVAULT_LIVE=1` + `make test-live` (not part of `make gate`) |
| Failure | **D+C**: soft-skip on transient external errors; hard-fail on contract/route bugs and assertion failures once a live session is established |
| Scope | **All**: `zhihu_lists` one-page fetches + profile resolve + minimal people backup |
| Shape | Single module `tests/test_live_zhihu.py` + small helpers (prefer one file over three) |

## Non-goals

- Recording/VCR cassettes or CI-enforced live runs
- Live POST/DELETE / `account apply`
- Committing cookies, tokens, or real handles into the repo
- Changing production list-route logic beyond what tests exercise

## Enablement

1. Register pytest marker `live` in `pyproject.toml`.
2. Live tests require **all** of:
   - `ZHVAULT_LIVE` in `{1, true, yes}` (case-insensitive)
   - A usable cookie (see below)
   - `ZHVAULT_LIVE_USER` set to a url_token (or people URL); docs/comments use placeholders only
3. Missing any of the above → `pytest.skip` (entire live module or per-fixture).
4. `make gate` / default `make test` / plain `pytest` must **not** select live tests as required greens. Prefer `addopts = "-m 'not live'"` so accidental `pytest -m live` without env still skips inside tests, and default collection excludes live from the gate path.
5. `make test-live`:
   ```make
   test-live:
   	ZHVAULT_LIVE=1 $(UV) run pytest -m live $(ARGS)
   ```
   (pip fallback same pattern.) Caller still must provide cookie + `ZHVAULT_LIVE_USER`.

### Cookie resolution (test helper)

Order:

1. `ZHVAULT_COOKIE_FILE` if set and exists  
2. Else `Cookies.json` in cwd if present  
3. Else skip with message to set cookie file / run `zhvault auth set-cookie`

Do **not** open the user’s real `data/` vault for live e2e; use `tmp_path` as `--data-dir`. Cookie is loaded into that temp engine (or passed into `ZhihuClient` the same way CLI does).

## Failure policy (D+C)

Classify errors at the live helper boundary:

| Class | Examples | Result |
|-------|----------|--------|
| Not opted in | no `ZHVAULT_LIVE`, no user, no cookie | `pytest.skip` |
| Transient / external | `Timeout`, connection errors, HTTP **429**, HTTP **403** / `PermissionError` (auth decay) | `pytest.skip` with short reason |
| Contract / route | HTTP **404** on **all** candidates with no usable payload; JSON missing `data` where list expected; profile resolve returns empty/error object when HTTP succeeded | **fail** |
| Assertion | wrong types, backup wrote nothing expected, unexpected `source_errors` for non-soft paths | **fail** |

Notes:

- Empty `data: []` with valid `paging` is **success** (user may have no columns/pins).
- Soft-skip must not swallow assertion failures after a successful JSON parse.
- Prefer one shared helper `live_get_json` / `call_or_skip_transient` so classification stays consistent.

## Test cases

### 1) Lists (`zhihu_lists`)

For each registered resource key in `LIST_ROUTES` (or the same set already covered by unit tests):

- `fetch_person_list(client, token, resource, offset=0, limit=20)`
- Assert response is a `dict` with `data` as `list` and `paging` present (dict or absent-only if API omits — prefer require `paging` when `data` exists; if Zhihu omits on empty, allow missing `paging` only when `data == []`).

Do not assert non-empty lists.

### 2) Profile resolve

- `parse_people_ref` on token / `people/{token}` / full URL forms (can stay pure unit-like inside live file or rely on existing unit tests; live file must call **`resolve_member_profile(client, token)`** against the network).
- Assert returned `url_token` non-empty and equals parsed token (or canonical token from API).

### 3) Minimal people backup

- Temp `--data-dir`, engine `json` or `sqlite`, cookie loaded.
- Run backup for `--source people --user $ZHVAULT_LIVE_USER` with the smallest practical surface (full people source set is OK if already how CLI works; do not add `--full` unless required).
- Success criteria (minimal):
  - command exit 0 (or CLI entry returns ok summary)
  - `contents/people/{url_token}.md` exists under temp data dir **or** at least one content/membership write attributable to the run
  - no hard failure from “all list routes wrong”; soft 404 skips on individual empty tabs are allowed (match product behavior)

Prefer invoking the same code path as CLI (`cmd_backup` / typer runner) over reimplementing the pipeline in the test.

## Files to touch

| Path | Change |
|------|--------|
| `pyproject.toml` | marker `live`; optional `addopts = "-m 'not live'"` |
| `Makefile` | `test-live` target; help text |
| `tests/test_live_zhihu.py` | live tests |
| `tests/live_support.py` (optional) | env/cookie/transient helpers if file grows |
| `AGENTS.md` / `README` (short) | how to run `make test-live` + required env vars |
| `docs/harness/...` | only if ops runbook already documents test targets |

## Verify

- `make gate` — green; live tests not required / not failing when env unset  
- Without `ZHVAULT_LIVE`: `pytest -m live` → all skipped  
- With live env + cookie + user: lists/profile/backup assertions as above; kill network or force 429 path → skip not fail  
- Docs never embed a real url_token

## Risks

- Zhihu WAF / zse96 may 403 often → many skips; still useful when cookie is fresh.  
- People backup can be slow; keep one e2e test, not per-tab e2e.  
- `addopts = "-m 'not live'"` means contributors must use `make test-live` or `pytest -m live`; document clearly.
