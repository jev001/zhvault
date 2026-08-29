import json
import sys

import pytest

from cli import main
from models import GraphEdge
from storage import open_engine


def test_graph_sync_parses_backend(monkeypatch):
    captured = {}

    def fake_sync(args):
        captured["backend"] = args.backend
        return 0

    import cli.app  # noqa: F401

    monkeypatch.setattr(sys.modules["cli.app"], "cmd_graph_sync", fake_sync)
    assert main(["graph", "sync", "--backend", "kuzu", "--json"]) == 0
    assert captured["backend"] == "kuzu"


def test_graph_query_parses_backend(monkeypatch):
    captured = {}

    def fake_query(args):
        captured["backend"] = args.backend
        return 0

    import cli.app  # noqa: F401

    monkeypatch.setattr(sys.modules["cli.app"], "cmd_graph_query", fake_query)
    assert main(
        ["graph", "query", "--from", "user:me", "--depth", "2", "--backend", "memory"]
    ) == 0
    assert captured["backend"] == "memory"


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
