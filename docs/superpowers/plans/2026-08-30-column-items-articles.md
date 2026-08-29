# Column Items + Article Detail Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Expand `--source column` to fetch `/columns/{key}/items`, always GET article detail, write articles + column stub with `## Articles` wikilinks.

**Architecture:** `ColumnExpandSource` replaces plain `MemberPagedSource` for columns; helpers in `zhihu_lists.py` for items + article detail URLs.

**Tech Stack:** existing `ZhihuClient`, `normalize_content`, pipeline unchanged.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-08-30-column-items-articles-design.md`
- Articles: `owner_kind=articles`, `owner_id=member`, `source_tag=column-items:{column_key}`, `parent_id=column_key`
- Always detail fetch; soft-skip per article on failure
- `make gate` green

---

### Task 1: API helpers + ColumnExpandSource + wire + tests

**Files:**
- Modify: `src/zhihu_lists.py`
- Create: `src/sources/column_expand.py`
- Modify: `src/sources/__init__.py`
- Create: `tests/test_column_expand.py`
- Modify: `AGENTS.md` (one line)

- [ ] Implement + tests + `make gate`
- [ ] Commit (include pending profile members-first if still dirty)
