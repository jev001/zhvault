# Account Mutate (Online FCQ, Gated) — Design

**Date:** 2026-08-29  
**Status:** Approved (plan implement)

## Goal

Mutate the **logged-in Zhihu account** for:

- **F** follow / unfollow people  
- **C** add / remove collection items  
- **Q** follow / unfollow questions  

Two modes:

1. **`prune`** — delete-only using the current cookie account’s local inventory  
2. **`migrate`** — read inventory from account A’s `--from-data-dir`, write with account B’s cookie  

Default behavior is **plan / analyze only** (local inventory + optional GET). Live POST/DELETE requires stacked danger confirmation.

## Non-goals

- Votes / pins / asked / remove followers  
- Local MD/meta/graph purge as a substitute for unfollow  
- Auto-apply after `backup`  
- Guaranteeing Zhihu ToS compliance (user owns risk)

## Safety gate

1. `account plan` — never writes; emits plan JSON + `event=plan_summary`  
2. `account apply --plan PATH` — refuses unless **all** of:
   - `--i-understand-danger`
   - `--confirm APPLY` (exact)
   - plan `fingerprint` matches recomputed inventory hash  
3. Stderr DANGER banner with `/me` `url_token` and op counts before writes  

## CLI

```bash
python -m zhihu_backup account plan --mode prune \
  --source following,collection,followed --json

python -m zhihu_backup account plan --mode migrate \
  --from-data-dir ../a/data --data-dir data_b \
  --source following,collection,followed \
  --map-collection 123=456 --json

python -m zhihu_backup account apply --plan plan.json \
  --i-understand-danger --confirm APPLY --json
```

`--source` must be an explicit non-empty comma list (`following|collection|followed` and aliases). Empty → error.

## Collection resolve (migrate)

1. `--map-collection A_id=B_id` wins  
2. Else same **title** as B’s existing favlists (GET)  
3. Else record `create` with title; apply creates then adds items  

## Inventory

| Source | Prune | Migrate |
|--------|-------|---------|
| following | unfollow tokens from `follows` edges `user:{me}→user:X` | follow those tokens |
| followed | unfollow question ids from `followed_questions` membership | follow on B |
| collection | remove items from membership `collections` | resolve target id; add |

## Layout

```
zhihu_backup/mutate/
  endpoints.py   # pinned write/list URLs
  plan.py        # inventory → plan + fingerprint
  apply.py       # gates + dispatch
```

`ZhihuClient.request_json` is the only write path; call only from `apply`.

## Verify

- Plan → zero write HTTP methods  
- Apply without flags → non-zero, no writes  
- Stale fingerprint → abort  
- Mocked apply continues after per-item failure; summary lists `failed[]`
