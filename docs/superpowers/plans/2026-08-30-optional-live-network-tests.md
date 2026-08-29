# Optional Live Network Tests Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Opt-in pytest suite that hits real Zhihu APIs for list routes, profile resolve, and minimal people backup without breaking `make gate`.

**Architecture:** Shared `tests/live_support.py` classifies transient vs contract errors; `tests/test_live_zhihu.py` is `@pytest.mark.live` and skips unless `ZHVAULT_LIVE` + cookie + `ZHVAULT_LIVE_USER`. Default `addopts = -m 'not live'`; `make test-live` clears addopts.

**Tech Stack:** pytest, requests/`ZhihuClient`, Typer CliRunner, existing `zhihu_lists` / `auth` / CLI backup.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-08-30-optional-live-network-tests-design.md`
- Never commit cookies / real handles; env only for live user
- Transient (timeout/conn/429/403) → skip; contract/assert → fail
- `make gate` must stay green without network

---

### Task 1: live_support + unit tests + pytest/Makefile wiring

**Files:**
- Create: `tests/live_support.py`
- Create: `tests/test_live_support.py`
- Create: `tests/test_live_zhihu.py`
- Modify: `pyproject.toml`, `Makefile`, `README.md`, `AGENTS.md`

- [ ] Implement helpers + live tests per design
- [ ] `make gate` green (live excluded / skipped)
- [ ] Commit
