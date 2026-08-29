import json
import sys

import pytest

from cli import build_parser, main
from models import GraphEdge
from storage import open_engine


def test_parser_graph_sync():
    p = build_parser()
    args = p.parse_args(["graph", "sync", "--backend", "kuzu", "--json"])
    assert args.func.__name__ == "cmd_graph_sync"
    assert args.backend == "kuzu"


def test_parser_graph_query_backend():
    p = build_parser()
    args = p.parse_args(
        ["graph", "query", "--from", "user:me", "--depth", "2", "--backend", "memory"]
    )
    assert args.func.__name__ == "cmd_graph_query"
    assert args.backend == "memory"


def test_graph_sync_missing_kuzu_package(monkeypatch, tmp_path, capsys):
    monkeypatch.setitem(sys.modules, "kuzu", None)
    meta = tmp_path / "meta"
    meta.mkdir()
    rc = main(
        [
            "graph",
            "sync",
            "--backend",
            "kuzu",
            "--json",
            "--data-dir",
            str(tmp_path),
        ]
    )
    assert rc == 2
    err = capsys.readouterr()
    out = json.loads(err.out.strip())
    assert out["event"] == "error"
    assert "zhvault[kuzu]" in out["error"]


def test_graph_query_backend_memory(tmp_path, capsys):
    meta = tmp_path / "meta"
    meta.mkdir()
    eng = open_engine("sqlite", meta)
    try:
        eng.upsert_graph_edge(
            GraphEdge(
                from_id="user:me",
                to_id="user:friend",
                kind="follows",
                origin="manual",
                seen_at="2026-01-01T00:00:00Z",
            )
        )
    finally:
        eng.close()

    rc = main(
        [
            "graph",
            "query",
            "--from",
            "user:me",
            "--depth",
            "1",
            "--backend",
            "memory",
            "--json",
            "--data-dir",
            str(tmp_path),
        ]
    )
    assert rc == 0
    out = json.loads(capsys.readouterr().out.strip())
    assert out["start"] == "user:me"
    ids = {n["id"] for n in out["nodes"]}
    assert ids == {"user:me", "user:friend"}


def test_graph_query_backend_kuzu_without_sync(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr("cli.common.kuzu_importable", lambda: True)
    meta = tmp_path / "meta"
    meta.mkdir()
    rc = main(
        [
            "graph",
            "query",
            "--from",
            "user:me",
            "--depth",
            "1",
            "--backend",
            "kuzu",
            "--json",
            "--data-dir",
            str(tmp_path),
        ]
    )
    assert rc == 2
    err = capsys.readouterr()
    out = json.loads(err.out.strip())
    assert out["event"] == "error"
    assert "graph sync" in out["error"].lower()
