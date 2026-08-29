import json

from cli import build_parser, main
from models import GraphEdge
from storage import open_engine


def test_parser_graph_query():
    p = build_parser()
    args = p.parse_args(
        ["graph", "query", "--from", "user:me", "--depth", "2", "--kind", "follows"]
    )
    assert args.func.__name__ == "cmd_graph_query"
    assert args.from_id == "user:me"
    assert args.depth == 2
    assert args.kind == ["follows"]


def test_graph_query_cli_json(tmp_path, capsys):
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
        eng.upsert_graph_edge(
            GraphEdge(
                from_id="user:friend",
                to_id="user:other",
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
            "--kind",
            "follows",
            "--json",
            "--data-dir",
            str(tmp_path),
        ]
    )
    assert rc == 0
    out = json.loads(capsys.readouterr().out.strip())
    assert out["start"] == "user:me"
    assert out["depth"] == 1
    assert out["kinds"] == ["follows"]
    ids = {n["id"] for n in out["nodes"]}
    assert ids == {"user:me", "user:friend"}
    assert len(out["edges"]) == 1


def test_graph_query_cli_kind_all(tmp_path, capsys):
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
        eng.upsert_graph_edge(
            GraphEdge(
                from_id="user:me",
                to_id="answer:1:2",
                kind="collected",
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
            "--kind",
            "all",
            "--json",
            "--data-dir",
            str(tmp_path),
        ]
    )
    assert rc == 0
    out = json.loads(capsys.readouterr().out.strip())
    assert out["kinds"] is None
    assert len(out["edges"]) == 2


def test_graph_query_cli_human(tmp_path, capsys):
    meta = tmp_path / "meta"
    meta.mkdir()
    eng = open_engine("sqlite", meta)
    try:
        eng.upsert_graph_edge(
            GraphEdge(
                from_id="user:a",
                to_id="user:b",
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
            "user:a",
            "--data-dir",
            str(tmp_path),
        ]
    )
    assert rc == 0
    text = capsys.readouterr().out
    assert "2 nodes" in text or "nodes: 2" in text.lower() or "2 node" in text
    assert "1 edge" in text or "edges: 1" in text.lower() or "1 edge" in text
