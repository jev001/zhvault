# Column Items → Article Detail Backup — Design

**Date:** 2026-08-30  
**Status:** Draft (awaiting user review)

## Goal

When backing up columns (`--source column` / included by `people` / `all` with `--user`), after listing a member’s columns, also fetch **every article inside each column** with **full detail payloads**, write article markdown, and keep **column stub markdown** that **wikilinks** to those articles.

## Locked decisions

| Topic | Choice |
|-------|--------|
| Artifact set | **C**: column stub MD + article MDs + wikilinks from column → articles |
| Column article list | `GET /api/v4/columns/{column_key}/items` (+ `ws_qiangzhisafe`, `offset`, `limit`) |
| Article body | **B**: always fetch article detail per list row (do not rely on list `content`) |
| Shape | Dedicated column expand path (方案 1), not a new CLI source name |

Browser-confirmed list example:

`https://www.zhihu.com/api/v4/columns/c_2074890283800645989/items?ws_qiangzhisafe`

## Non-goals

- Changing HTTP 404 retry policy
- Changing profile resolve order further
- New `--source` verb (reuse `column`)
- Mutate / subscribe / unfollow columns
- Replacing `--source article` (member article tab remains independent; shared `item_key` dedupes)

## Current behavior (baseline)

- `_member_column` → `MemberPagedSource(resource="columns")` → `column-contributions`
- `unwrap_column_row` → `normalize_content` for `type=column` (intro only)
- No `/columns/.../items` and no article detail fetch

## Target flow

```text
column-contributions page
  → for each column:
      yield/write column NormalizedItem (stub)
      GET /columns/{column_key}/items (paginate)
        → for each row (article id):
            GET /api/v4/articles/{article_id}   # always (B)
            yield article NormalizedItem (owner_kind=columns or articles; see below)
      update column MD body with wikilink list of articles written this run / known membership
```

### Column key

Prefer `url_token` when present (e.g. `c_2074890283800645989`); else string `id`. Same key used in the items URL path.

### Article detail URL

Default: `GET https://www.zhihu.com/api/v4/articles/{id}`.  
If live traffic requires an `include=` query, add a single constant in `zhihu_lists` (or a tiny helper next to column items) once confirmed — no silent alternate without a fallback log.

### Owner / paths / keys

- **Column stub:** keep `owner_kind=columns`, `owner_id=<member url_token>`, `source_tag=column:<member>`.
- **Articles from column items:** normalize as `type=article` with `parent_id` / `extra.column_id` set from the column key (existing `business_extra` / graph `in_column` already expect this).
  - **Locked:** `owner_kind=articles`, `owner_id=<member url_token>`, `source_tag=column-items:<column_key>` so paths align with `--source article` and `item_key` dedupes cleanly.
- Incremental: same `item_key` → pipeline `skipped` as today.

### Wikilinks (C)

After articles for a column are processed (or on column item write + post-pass):

- Column MD gains a section (e.g. `## Articles`) listing Obsidian-style `[[relative-or-vault-path]]` links to each article file path known for that `column_id` (from this run’s writes and/or membership query if cheap).
- Do not invent a second index file; membership + MD body only.
- Match existing vault conventions (`asset-link` / wikilink style already used for assets). If article paths are under `contents/articles/...`, links are repo-relative from vault root `data/`.

### Errors

| Case | Behavior |
|------|----------|
| Column list 404 | soft-skip column source (existing) |
| Items list 404/empty | keep column stub; log; no articles |
| Article detail 403/429/timeout | soft-skip that article (log); continue |
| Article detail 404 | soft-skip that article |
| Malformed row (no id) | skip row |

Transient vs hard follows existing source_error patterns where applicable; one bad article must not abort the whole column source.

### Checkpoint / resume

- Pipeline checkpoints are per `source_name/source_id` (today: `column/<member>`).
- Expanding items makes one logical source much heavier. **MVP:** keep a single Source `column/<member>`; checkpoint remains contribution-list offset. If interrupted mid-column, resume may re-walk earlier columns’ items but articles should mostly `skipped` via item_key.  
- Optional later: nested checkpoint `column-items/<column_key>` — out of MVP unless gate tests prove too slow.

## API helpers

Add small helpers (names illustrative):

- `column_items_url(column_key) -> str`
- `fetch_column_items(client, column_key, offset, limit) -> dict`
- `fetch_article_detail(client, article_id) -> dict`

Wire from a new `ColumnExpandSource` (or specialize `_member_column` to return a Source that implements the expand loop) instead of plain `MemberPagedSource` for columns only.

## CLI / docs

- No new flags required for MVP.
- Document in `AGENTS.md` / README: `--source column` expands items + article detail.
- Live tests (optional): extend live suite later; not blocking MVP unit tests with mocks.

## Verify

- Mock: contributions → 1 column → items → 2 article ids → 2 detail GETs → yield 1 column + 2 articles; column MD link section contains both basenames.
- Same article id already stored → second run `skipped`.
- Items empty → column only.
- Detail 404 → column still written; one article skipped.
- `make gate` green.

## Risks

- Request volume (B): many columns × articles × detail; respect `ZhihuClient` throttle.
- Column key mismatch (`id` vs `url_token`) → 404 on items; log key used and try the other once if first 404 (single fallback), then give up for that column.
