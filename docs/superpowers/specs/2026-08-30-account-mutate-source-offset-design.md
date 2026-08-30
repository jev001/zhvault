# Account Mutate — Source Kind Split + Offset Window

**Date:** 2026-08-30  
**Status:** Implemented  
**Extends:** [2026-08-29-account-mutate-design.md](./2026-08-29-account-mutate-design.md)

## Goal

When merging / pruning accounts, “follow” inventory must be runnable **by entity kind** (people vs questions vs collections), and large kinds must be **batchable** with `--offset` + `--limit`. `--source all` expands to every mutate kind.

## Problem

- Account A’s following graph can be huge; one plan with all follow-people actions is impractical.
- CLI name `followed` reads like “被关注的人” (followers) but means **followed questions**. People vs questions must stay clearly separated in source names and plan snapshots.
- Existing `--limit` alone always takes the same sorted prefix; migrate does not shrink A’s inventory, so batches cannot advance without `--offset`.

## Non-goals

- Mutating **followers** (fans / 被关注的人) — out of scope
- Per-source independent windows when multiple sources are combined (offset applies to the merged sorted action list)
- Changing Zhihu follow/collect HTTP endpoints or apply gates
- Auto-apply after backup

## CLI

`--source` remains **required** (non-empty). Canonical values after parse:

| Value | Meaning | Inventory |
|-------|---------|-----------|
| `following` | People the ego follows | graph edges `kind=follows`, `user:{me}→user:X` |
| `followed_questions` | Questions the ego follows | membership `owner_kind=followed_questions` |
| `collection` | Favlist items | membership `owner_kind=collections` |
| `all` | Expands to the three above in that order, then dedupe | — |

Aliases (map to canonical; plan stores canonical only):

- `followees` → `following`
- `followed`, `followed-questions` → `followed_questions`
- `collections` → `collection`

Batching:

- `--offset N` — default `0`, require `N >= 0`
- `--limit M` — optional cap (unchanged)
- Slice **after** stable sort: `actions[offset : offset+limit]` (or `actions[offset:]` if no limit)

Recommended large-account flow: one kind per plan (`--source following`), then bump `--offset`. Prefer not to rely on `all` + offset for huge inventories.

Example:

```bash
zhvault account plan --mode migrate \
  --from-data-dir ../a/data \
  --source following --offset 0 --limit 500 --json

zhvault account plan --mode migrate \
  --from-data-dir ../a/data \
  --source followed_questions --json

zhvault account plan --mode prune --source all --json
```

## Plan build / fingerprint

Order:

1. Expand/normalize `sources`
2. Collect full action list from inventory (same ops as today)
3. `sorted(actions, key=json.dumps(..., sort_keys=True))`
4. Apply offset/limit window
5. Fingerprint and emit plan

Fingerprint inputs:

- `mode`, `sources` (canonical), `limit`, `offset`, `map_collection`
- snapshot lists: `following`, `followed_questions`, `collection_items`

Relative to 2026-08-29:

- Rename snapshot/fingerprint key `followed` → `followed_questions`
- Add `offset` (missing in old plans → treat as `0` on recompute/rebuild)

Plan JSON additions:

- `offset` (int)
- `sources` always canonical expanded list
- `total_before_window` (int) — action count before offset/limit, for batch review
- `counts` still by `op` on the **windowed** actions

Apply path unchanged except fingerprint rebuild must pass the same `offset` / `limit` / `sources`.

## Layout / files

| File | Change |
|------|--------|
| `src/mutate/plan.py` | `all`, canonical `followed_questions`, offset slice, fingerprint/snapshot keys |
| `src/cli/app.py`, `src/cli/cmd_account.py` | `--offset`; wire into `build_plan`; help text |
| `tests/test_account_mutate.py` | `all`, aliases, offset windows, fingerprint sensitivity |
| `AGENTS.md` | account examples: `followed_questions`, `all`, `--offset` |

## Verify

1. `parse_sources("all")` → `["following", "followed_questions", "collection"]`
2. `parse_sources("followed")` → `["followed_questions"]`
3. Same inventory: `--offset 0 --limit 1` vs `--offset 1 --limit 1` → different single actions and different fingerprints
4. Omitting `--offset` ≡ `offset=0` (behavior matches pre-change for same sources/limit)
5. `make gate` green
