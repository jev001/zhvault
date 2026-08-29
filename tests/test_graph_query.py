from pathlib import Path
from zhihu_backup.models import GraphEdge, ItemRecord
from zhihu_backup.storage.sqlite_engine import SqliteEngine
from zhihu_backup.graph import query_graph


def _seed(eng: SqliteEngine) -> None:
    eng.upsert_item(ItemRecord(key="question:1", item_type="question", zhihu_id="1", title="Q"))
    eng.upsert_item(
        ItemRecord(
            key="answer:1:2",
            item_type="answer",
            zhihu_id="2",
            title="A",
            extra={"parent_id": "1", "question_id": "1"},
        )
    )
    eng.upsert_graph_edge(
        GraphEdge(
            from_id="user:me",
            to_id="user:friend",
            kind="follows",
            origin="api",
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


def test_query_depth_1_follows(tmp_path: Path):
    eng = SqliteEngine(tmp_path / "t.db")
    _seed(eng)
    out = query_graph(eng, start="user:me", depth=1, kinds={"follows"})
    ids = {n["id"] for n in out["nodes"]}
    assert ids == {"user:me", "user:friend"}
    eng.close()


def test_query_depth_2_follows(tmp_path: Path):
    eng = SqliteEngine(tmp_path / "t.db")
    _seed(eng)
    out = query_graph(eng, start="user:me", depth=2, kinds={"follows"})
    ids = {n["id"] for n in out["nodes"]}
    assert "user:other" in ids
    eng.close()


def test_query_answers_kind(tmp_path: Path):
    eng = SqliteEngine(tmp_path / "t.db")
    _seed(eng)
    out = query_graph(eng, start="answer:1:2", depth=1, kinds={"answers"})
    assert any(e["to"] == "question:1" for e in out["edges"])
    eng.close()
