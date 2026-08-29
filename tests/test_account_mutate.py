"""Tests for gated account mutate (FCQ)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from zhihu_backup.cli import build_parser, main
from zhihu_backup.models import GraphEdge, ItemRecord
from zhihu_backup.mutate.apply import ApplyGateError, apply_plan, check_apply_gates
from zhihu_backup.mutate.endpoints import follow_user_url
from zhihu_backup.mutate.plan import build_plan, parse_sources
from zhihu_backup.storage import open_engine


def _seed_following(meta: Path, *, ego: str = "me", friends: list[str] | None = None) -> None:
    eng = open_engine("sqlite", meta)
    try:
        for tok in friends or ["alice", "bob"]:
            eng.upsert_item(
                ItemRecord(key=f"user:{tok}", item_type="user", zhihu_id=tok, title=tok)
            )
            eng.upsert_graph_edge(
                GraphEdge(
                    from_id=f"user:{ego}",
                    to_id=f"user:{tok}",
                    kind="follows",
                    origin="api",
                    seen_at="2026-01-01T00:00:00Z",
                )
            )
    finally:
        eng.close()


def _seed_collection(meta: Path) -> None:
    eng = open_engine("sqlite", meta)
    try:
        eng.upsert_item(
            ItemRecord(
                key="answer:1:10",
                item_type="answer",
                zhihu_id="10",
                title="a",
                extra={"answer_id": "10", "question_id": "1"},
            )
        )
        eng.link_membership("answer:1:10", "collections", "99")
        eng.upsert_item(
            ItemRecord(
                key="question:42",
                item_type="question",
                zhihu_id="42",
                title="q",
                extra={"question_id": "42"},
            )
        )
        eng.link_membership("question:42", "followed_questions", "me")
    finally:
        eng.close()


def test_parse_sources_required():
    with pytest.raises(ValueError):
        parse_sources("")
    assert parse_sources("following,collection") == ["following", "collection"]
    assert parse_sources("followed_questions") == ["followed"]


def test_plan_prune_following_only(tmp_path: Path):
    meta = tmp_path / "meta"
    meta.mkdir()
    _seed_following(meta)
    eng = open_engine("sqlite", meta)
    try:
        plan = build_plan(
            mode="prune",
            sources=["following"],
            inventory_engine=eng,
            actor_token="me",
            inventory_meta={"data_dir": str(tmp_path), "engine": "sqlite", "map_collection": {}},
        )
    finally:
        eng.close()
    ops = {a["op"] for a in plan["actions"]}
    assert ops == {"unfollow_user"}
    assert len(plan["actions"]) == 2
    assert plan["danger"] is True
    assert plan["fingerprint"]


def test_plan_migrate_following(tmp_path: Path):
    meta = tmp_path / "meta"
    meta.mkdir()
    _seed_following(meta)
    eng = open_engine("sqlite", meta)
    try:
        plan = build_plan(
            mode="migrate",
            sources=["following"],
            inventory_engine=eng,
            actor_token="me",
        )
    finally:
        eng.close()
    assert all(a["op"] == "follow_user" for a in plan["actions"])


def test_plan_collection_and_followed(tmp_path: Path):
    meta = tmp_path / "meta"
    meta.mkdir()
    _seed_collection(meta)
    eng = open_engine("sqlite", meta)
    try:
        prune = build_plan(mode="prune", sources=["collection", "followed"], inventory_engine=eng)
        mig = build_plan(
            mode="migrate",
            sources=["collection"],
            inventory_engine=eng,
            map_collection={"99": "200"},
        )
    finally:
        eng.close()
    assert any(a["op"] == "collect_remove" for a in prune["actions"])
    assert any(a["op"] == "unfollow_question" for a in prune["actions"])
    add = [a for a in mig["actions"] if a["op"] == "collect_add"]
    assert len(add) == 1
    assert add[0]["collection_id"] == "200"


def test_apply_gates_refuse():
    with pytest.raises(ApplyGateError):
        check_apply_gates(i_understand_danger=False, confirm="APPLY")
    with pytest.raises(ApplyGateError):
        check_apply_gates(i_understand_danger=True, confirm="yes")
    check_apply_gates(i_understand_danger=True, confirm="APPLY")


def test_apply_mocked_success_and_partial_fail(tmp_path: Path):
    meta = tmp_path / "meta"
    meta.mkdir()
    _seed_following(meta, friends=["alice", "bob"])
    eng = open_engine("sqlite", meta)
    try:
        plan = build_plan(
            mode="prune",
            sources=["following"],
            inventory_engine=eng,
            actor_token="me",
            inventory_meta={
                "data_dir": str(tmp_path.resolve()),
                "engine": "sqlite",
                "map_collection": {},
            },
        )
    finally:
        eng.close()

    client = MagicMock()
    calls: list[tuple[str, str]] = []

    def request_json(method, url, **kwargs):
        calls.append((method, url))
        if "bob" in url:
            raise RuntimeError("boom")
        return {}

    client.request_json.side_effect = request_json
    client.get_json.return_value = {"url_token": "me"}

    result = apply_plan(
        plan,
        client,
        i_understand_danger=True,
        confirm="APPLY",
        open_engine_fn=open_engine,
        skip_rebuild=False,
    )
    assert result["writes_executed"] is True
    assert result["ok"] == 1
    assert result["failed_count"] == 1
    assert any(m == "DELETE" and follow_user_url("alice") == u for m, u in calls)


def test_apply_stale_fingerprint(tmp_path: Path):
    meta = tmp_path / "meta"
    meta.mkdir()
    _seed_following(meta, friends=["alice"])
    eng = open_engine("sqlite", meta)
    try:
        plan = build_plan(
            mode="prune",
            sources=["following"],
            inventory_engine=eng,
            actor_token="me",
            inventory_meta={
                "data_dir": str(tmp_path.resolve()),
                "engine": "sqlite",
                "map_collection": {},
            },
        )
        # mutate inventory after plan
        eng.upsert_graph_edge(
            GraphEdge(
                from_id="user:me",
                to_id="user:carol",
                kind="follows",
                origin="api",
                seen_at="2026-01-01T00:00:00Z",
            )
        )
    finally:
        eng.close()

    client = MagicMock()
    client.get_json.return_value = {"url_token": "me"}
    with pytest.raises(ApplyGateError, match="fingerprint"):
        apply_plan(
            plan,
            client,
            i_understand_danger=True,
            confirm="APPLY",
            open_engine_fn=open_engine,
        )
    client.request_json.assert_not_called()


def test_cli_plan_json(tmp_path: Path, capsys):
    meta = tmp_path / "meta"
    meta.mkdir()
    _seed_following(meta)
    rc = main(
        [
            "account",
            "plan",
            "--mode",
            "prune",
            "--source",
            "following",
            "--data-dir",
            str(tmp_path),
            "--json",
        ]
    )
    assert rc == 0
    plan = json.loads(capsys.readouterr().out.strip())
    assert plan["mode"] == "prune"
    assert "fingerprint" in plan
    assert plan.get("danger") is True
    assert all(a["op"] == "unfollow_user" for a in plan["actions"])


def test_cli_apply_refuses_without_flags(tmp_path: Path):
    meta = tmp_path / "meta"
    meta.mkdir()
    _seed_following(meta)
    eng = open_engine("sqlite", meta)
    try:
        plan = build_plan(
            mode="prune",
            sources=["following"],
            inventory_engine=eng,
            actor_token="me",
            inventory_meta={
                "data_dir": str(tmp_path.resolve()),
                "engine": "sqlite",
                "map_collection": {},
            },
        )
    finally:
        eng.close()
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    eng2 = open_engine("sqlite", meta)
    try:
        eng2.set_cookie({"z_c0": "x"})
    finally:
        eng2.close()

    rc = main(
        [
            "account",
            "apply",
            "--plan",
            str(plan_path),
            "--data-dir",
            str(tmp_path),
            "--json",
        ]
    )
    assert rc == 2


def test_parser_account():
    p = build_parser()
    args = p.parse_args(
        [
            "account",
            "apply",
            "--plan",
            "p.json",
            "--i-understand-danger",
            "--confirm",
            "APPLY",
        ]
    )
    assert args.func.__name__ == "cmd_account_apply"
    assert args.i_understand_danger is True
    assert args.confirm == "APPLY"
