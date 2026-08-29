from pathlib import Path

from models import GraphEdge, ItemRecord
from storage.json_engine import JsonEngine
from storage.sqlite_engine import SqliteEngine


def _edge(**kw):
    base = {
        "from_id": "user:a",
        "to_id": "user:b",
        "kind": "follows",
        "origin": "api",
        "seen_at": "2026-01-01T00:00:00Z",
    }
    base.update(kw)
    return GraphEdge(**base)


def test_sqlite_upsert_list_remove(tmp_path: Path):
    eng = SqliteEngine(tmp_path / "t.db")
    eng.upsert_graph_edge(_edge())
    eng.upsert_graph_edge(_edge(origin="manual", seen_at="2026-01-02T00:00:00Z"))
    edges = eng.list_graph_edges()
    assert len(edges) == 1
    assert edges[0].origin == "manual"
    eng.remove_graph_edge("user:a", "user:b", "follows")
    assert eng.list_graph_edges() == []
    eng.close()


def test_sqlite_list_items_membership(tmp_path: Path):
    eng = SqliteEngine(tmp_path / "t.db")
    eng.upsert_item(
        ItemRecord(key="question:1", item_type="question", zhihu_id="1", title="Q")
    )
    eng.link_membership("question:1", "asked_questions", "me")
    assert eng.list_items()[0].key == "question:1"
    assert eng.list_membership() == [
        {"key": "question:1", "owner_kind": "asked_questions", "owner_id": "me"}
    ]
    eng.close()


def test_json_graph_edges_parity(tmp_path: Path):
    eng = JsonEngine(tmp_path / "state.json")
    eng.upsert_graph_edge(_edge())
    assert len(eng.list_graph_edges()) == 1
    eng.close()


def test_sqlite_api_upsert_preserves_manual(tmp_path: Path):
    eng = SqliteEngine(tmp_path / "t.db")
    eng.upsert_graph_edge(_edge(origin="manual", seen_at="2026-01-02T00:00:00Z"))
    eng.upsert_graph_edge(_edge(origin="api", seen_at="2026-01-03T00:00:00Z"))
    edges = eng.list_graph_edges()
    assert len(edges) == 1
    assert edges[0].origin == "manual"
    assert edges[0].seen_at == "2026-01-02T00:00:00Z"
    eng.close()


def test_json_api_upsert_preserves_manual(tmp_path: Path):
    eng = JsonEngine(tmp_path / "state.json")
    eng.upsert_graph_edge(_edge(origin="manual", seen_at="2026-01-02T00:00:00Z"))
    eng.upsert_graph_edge(_edge(origin="api", seen_at="2026-01-03T00:00:00Z"))
    edges = eng.list_graph_edges()
    assert len(edges) == 1
    assert edges[0].origin == "manual"
    assert edges[0].seen_at == "2026-01-02T00:00:00Z"
    eng.close()
