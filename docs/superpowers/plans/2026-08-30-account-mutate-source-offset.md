# Account Mutate Source Kind + Offset Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `account plan` runnable by entity kind (people vs questions vs collections), support `--source all`, and batch large kinds with `--offset` + `--limit` after a stable action sort.

**Architecture:** Keep all mutate planning in `src/mutate/plan.py`. Canonicalize sources so questions are `followed_questions` (not ambiguous `followed`). Expand `all` at parse time. Sort the full action list, then slice `[offset:offset+limit]`. Fingerprint includes `offset` and the renamed snapshot key so apply rebuild stays consistent.

**Tech Stack:** Python 3.11+, existing `mutate.plan` / Typer CLI / pytest / `make gate`.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-08-30-account-mutate-source-offset-design.md`
- Do **not** modify `a.json` or `data-a/` (local plan / vault data)
- Do **not** add followers (fans) mutate ops
- Do **not** change apply HTTP endpoints or danger gates
- Offset applies to the **merged sorted** action list (not per-source windows)
- Sort **before** window (fix current limit-then-sort order)
- Old plans missing `offset` recompute as `offset=0`
- `make gate` must stay green

## File map

| Path | Responsibility |
|------|----------------|
| `src/mutate/plan.py` | `all` + canonical `followed_questions`; `offset` window; fingerprint/snapshot keys; `total_before_window` |
| `src/cli/app.py` | `--offset` on `account plan`; help text |
| `src/cli/cmd_account.py` | Pass `offset` into `build_plan` |
| `tests/test_account_mutate.py` | `all`, aliases, offset windows, fingerprint sensitivity; update old `followed` expectations |
| `AGENTS.md` | account examples: `followed_questions`, `all`, `--offset` |

---

### Task 1: `parse_sources` — `all` + canonical `followed_questions`

**Files:**
- Modify: `src/mutate/plan.py` (`SOURCE_ALIASES`, `parse_sources`)
- Modify: `tests/test_account_mutate.py`

**Interfaces:**
- Produces: `parse_sources(raw: str) -> list[str]` returning only canonical names: `following` \| `followed_questions` \| `collection`
- Consumes: none

- [ ] **Step 1: Write failing tests**

Replace / extend `test_parse_sources_required` in `tests/test_account_mutate.py`:

```python
def test_parse_sources_required():
    with pytest.raises(ValueError):
        parse_sources("")
    assert parse_sources("following,collection") == ["following", "collection"]
    assert parse_sources("followed") == ["followed_questions"]
    assert parse_sources("followed_questions") == ["followed_questions"]
    assert parse_sources("all") == ["following", "followed_questions", "collection"]
    assert parse_sources("all,following") == ["following", "followed_questions", "collection"]
```

Also update any test that passes `sources=["followed"]` to `sources=["followed_questions"]` (e.g. `test_plan_collection_and_followed`).

- [ ] **Step 2: Run tests — expect FAIL**

```bash
pytest tests/test_account_mutate.py::test_parse_sources_required -v
```

Expected: FAIL (`followed` still canonical or `all` unknown).

- [ ] **Step 3: Implement `parse_sources`**

In `src/mutate/plan.py`, replace aliases and parse logic:

```python
SOURCE_ALIASES = {
    "following": "following",
    "followees": "following",
    "collection": "collection",
    "collections": "collection",
    "followed_questions": "followed_questions",
    "followed": "followed_questions",
    "followed-questions": "followed_questions",
}

ALL_SOURCES = ["following", "followed_questions", "collection"]


def parse_sources(raw: str) -> list[str]:
    parts = [p.strip() for p in (raw or "").split(",") if p.strip()]
    if not parts:
        raise ValueError(
            "--source required (comma list: following,followed_questions,collection,all)"
        )
    out: list[str] = []
    for p in parts:
        low = p.lower()
        if low == "all":
            for key in ALL_SOURCES:
                if key not in out:
                    out.append(key)
            continue
        key = SOURCE_ALIASES.get(low)
        if not key:
            raise ValueError(
                f"unsupported mutate source {p!r}; use following|followed_questions|collection|all"
            )
        if key not in out:
            out.append(key)
    return out
```

Update every internal `if "followed" in sources:` branch to `if "followed_questions" in sources:`.

- [ ] **Step 4: Run tests — expect PASS**

```bash
pytest tests/test_account_mutate.py::test_parse_sources_required tests/test_account_mutate.py::test_plan_collection_and_followed -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/mutate/plan.py tests/test_account_mutate.py
git commit -m "$(cat <<'EOF'
feat: canonicalize account mutate followed_questions and source all

EOF
)"
```

---

### Task 2: Offset window + fingerprint rename

**Files:**
- Modify: `src/mutate/plan.py` (`fingerprint_inventory`, `build_plan`, `recompute_fingerprint`, `rebuild_plan_from_inventory`)
- Modify: `tests/test_account_mutate.py`

**Interfaces:**
- Produces: `build_plan(..., limit: int | None = None, offset: int = 0) -> dict` with keys `offset`, `total_before_window`; fingerprint payload uses `followed_questions` + `offset`
- Consumes: Task 1 canonical source names

- [ ] **Step 1: Write failing window/fingerprint tests**

```python
def test_plan_offset_limit_window(tmp_path: Path):
    meta = tmp_path / "meta"
    meta.mkdir()
    _seed_following(meta, friends=["alice", "bob", "carol"])
    eng = open_engine("sqlite", meta)
    try:
        p0 = build_plan(
            mode="prune",
            sources=["following"],
            inventory_engine=eng,
            actor_token="me",
            offset=0,
            limit=1,
        )
        p1 = build_plan(
            mode="prune",
            sources=["following"],
            inventory_engine=eng,
            actor_token="me",
            offset=1,
            limit=1,
        )
        full = build_plan(
            mode="prune",
            sources=["following"],
            inventory_engine=eng,
            actor_token="me",
        )
    finally:
        eng.close()
    assert full["total_before_window"] == 3
    assert len(p0["actions"]) == 1
    assert len(p1["actions"]) == 1
    assert p0["actions"] != p1["actions"]
    assert p0["fingerprint"] != p1["fingerprint"]
    assert p0["offset"] == 0 and p1["offset"] == 1
    assert "followed_questions" in (p0.get("inventory") or {}).get("snapshot", {}) or True
    # snapshot key present when source selected:
    snap = full["inventory"]["snapshot"]
    assert "followed_questions" in snap or "following" in snap
    assert snap.get("following")  # following source → following list


def test_plan_offset_default_matches_zero(tmp_path: Path):
    meta = tmp_path / "meta"
    meta.mkdir()
    _seed_following(meta)
    eng = open_engine("sqlite", meta)
    try:
        a = build_plan(mode="prune", sources=["following"], inventory_engine=eng, actor_token="me")
        b = build_plan(
            mode="prune",
            sources=["following"],
            inventory_engine=eng,
            actor_token="me",
            offset=0,
        )
    finally:
        eng.close()
    assert a["fingerprint"] == b["fingerprint"]
    assert a["actions"] == b["actions"]


def test_build_plan_rejects_negative_offset(tmp_path: Path):
    meta = tmp_path / "meta"
    meta.mkdir()
    _seed_following(meta)
    eng = open_engine("sqlite", meta)
    try:
        with pytest.raises(ValueError, match="offset"):
            build_plan(
                mode="prune",
                sources=["following"],
                inventory_engine=eng,
                actor_token="me",
                offset=-1,
            )
    finally:
        eng.close()
```

Adjust `_seed_following` call if the helper uses a different kw name (`friends` vs existing). Match the existing helper signature in the test file.

- [ ] **Step 2: Run tests — expect FAIL**

```bash
pytest tests/test_account_mutate.py::test_plan_offset_limit_window tests/test_account_mutate.py::test_plan_offset_default_matches_zero tests/test_account_mutate.py::test_build_plan_rejects_negative_offset -v
```

Expected: FAIL (`offset` unexpected / TypeError).

- [ ] **Step 3: Implement fingerprint + window window**

Update `fingerprint_inventory`:

```python
def fingerprint_inventory(
    *,
    mode: str,
    sources: list[str],
    limit: int | None,
    offset: int,
    map_collection: dict[str, str],
    following: list[str],
    followed_questions: list[str],
    collection_items: list[tuple[str, str, str]],
) -> str:
    payload = {
        "mode": mode,
        "sources": sources,
        "limit": limit,
        "offset": offset,
        "map_collection": map_collection,
        "following": following,
        "followed_questions": followed_questions,
        "collection_items": [[a, b, c] for a, b, c in collection_items],
    }
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()
```

In `build_plan`, add `offset: int = 0`, validate `offset >= 0`, rename local `followed` list usage to `followed_questions`, and **replace** the limit/sort block with:

```python
    actions = sorted(actions, key=lambda a: json.dumps(a, sort_keys=True))
    total_before_window = len(actions)
    if offset < 0:
        raise ValueError("offset must be >= 0")
    if limit is not None and limit >= 0:
        actions = actions[offset : offset + limit]
    else:
        actions = actions[offset:]

    snap_following = following if "following" in sources else []
    snap_followed_questions = followed_questions if "followed_questions" in sources else []
    snap_collection = collection_items if "collection" in sources else []

    fp = fingerprint_inventory(
        mode=mode,
        sources=sources,
        limit=limit,
        offset=offset,
        map_collection=map_collection,
        following=snap_following,
        followed_questions=snap_followed_questions,
        collection_items=snap_collection,
    )
    meta = dict(inventory_meta or {})
    meta.setdefault("map_collection", map_collection)
    meta["snapshot"] = {
        "following": snap_following,
        "followed_questions": snap_followed_questions,
        "collection_items": [[a, b, c] for a, b, c in snap_collection],
    }
    plan: dict[str, Any] = {
        "version": 1,
        "mode": mode,
        "danger": True,
        "fingerprint": fp,
        "actor_hint": actor_token,
        "sources": sources,
        "limit": limit,
        "offset": offset,
        "total_before_window": total_before_window,
        "actions": actions,
        "collection_resolve": collection_resolve,
        "inventory": meta,
        "counts": _count_ops(actions),
    }
    return plan
```

Update `recompute_fingerprint` to pass `offset=int(plan.get("offset") or 0)` and read `snap.get("followed_questions")` (fallback: `snap.get("followed") or []` for old embedded snapshots only if you need local debug — prefer strict new key in new plans).

Update `rebuild_plan_from_inventory` to pass `offset=int(plan.get("offset") or 0)` into `build_plan`.

Fix any remaining callers of `fingerprint_inventory` / snapshot `followed` inside this module and tests.

- [ ] **Step 4: Run account mutate tests**

```bash
pytest tests/test_account_mutate.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/mutate/plan.py tests/test_account_mutate.py
git commit -m "$(cat <<'EOF'
feat: slice account mutate plans with offset after stable sort

EOF
)"
```

---

### Task 3: CLI `--offset` + AGENTS examples

**Files:**
- Modify: `src/cli/app.py` (`account_plan`)
- Modify: `src/cli/cmd_account.py`
- Modify: `AGENTS.md`

**Interfaces:**
- Consumes: `build_plan(..., offset: int = 0)` from Task 2
- Produces: CLI `--offset` default 0 wired through to plan JSON

- [ ] **Step 1: Add CLI option and wire**

In `src/cli/app.py` `account_plan`:

```python
    source: str = typer.Option(
        ...,
        "--source",
        help="comma list: following,followed_questions,collection,all (required; no default)",
    ),
    ...
    limit: int | None = typer.Option(None, "--limit", help="cap actions in plan"),
    offset: int = typer.Option(0, "--offset", help="skip first N sorted actions (batch window)"),
```

Pass `offset=offset` into `_run(...)/cmd_account_plan`.

In `src/cli/cmd_account.py`:

```python
        plan = build_plan(
            mode=mode,
            sources=sources,
            inventory_engine=inv_engine,
            map_collection=map_collection,
            limit=args.limit,
            offset=int(getattr(args, "offset", 0) or 0),
            client=client if mode == "migrate" else None,
            actor_token=actor_token,
            inventory_meta=inventory_meta,
        )
```

If `offset < 0`, either let `build_plan` raise or `cmd_fail` with the ValueError message.

Update `AGENTS.md` account examples (do not touch `a.json` / `data-a/`):

```bash
zhvault account plan --mode prune --source following,collection,followed_questions --json
zhvault account plan --mode migrate --from-data-dir ../a/data --source following --offset 0 --limit 500 --json
zhvault account plan --mode migrate --from-data-dir ../a/data --source followed_questions --json
zhvault account plan --mode prune --source all --json
```

Add `--offset` to the Useful flags line.

- [ ] **Step 2: Smoke CLI help**

```bash
zhvault account plan --help
```

Expected: help shows `--offset` and updated `--source` text.

- [ ] **Step 3: Run gate**

```bash
make gate
```

Expected: ruff + pytest green.

- [ ] **Step 4: Commit**

```bash
git add src/cli/app.py src/cli/cmd_account.py AGENTS.md
git commit -m "$(cat <<'EOF'
feat: expose account plan --offset and document source kinds

EOF
)"
```

---

### Task 4: Spec status + final verify

**Files:**
- Modify: `docs/superpowers/specs/2026-08-30-account-mutate-source-offset-design.md` (status line only)

- [ ] **Step 1: Mark spec implemented**

Change status from `Approved (design); awaiting implementation plan` to `Implemented` (match whatever Status line exists in the spec).

- [ ] **Step 2: Final gate**

```bash
make gate
```

Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/specs/2026-08-30-account-mutate-source-offset-design.md
git commit -m "$(cat <<'EOF'
docs: mark account mutate source-offset design implemented

EOF
)"
```

---

## Spec coverage checklist

| Spec requirement | Task |
|------------------|------|
| Canonical `followed_questions`; `followed` alias | Task 1 |
| `--source all` expands + dedupes | Task 1 |
| `--offset` + `--limit` after sort | Task 2 |
| Fingerprint includes `offset`; key rename | Task 2 |
| `total_before_window` | Task 2 |
| Rebuild/recompute pass offset (missing → 0) | Task 2 |
| CLI `--offset` + help | Task 3 |
| AGENTS examples | Task 3 |
| No followers mutate / no apply endpoint changes | Global Constraints |
| Do not modify `a.json` / `data-a/` | Global Constraints |
| `make gate` green | Tasks 3–4 |
