import importlib.util
import sys
from pathlib import Path

import pytest

from graph import query_graph
from graph_kuzu import query_kuzu, sync_to_kuzu
from models import GraphEdge, ItemRecord
from storage.sqlite_engine import SqliteEngine


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


def test_sync_to_kuzu_missing_package_install_hint(monkeypatch, tmp_path: Path):
    monkeypatch.setitem(sys.modules, "kuzu", None)
    eng = SqliteEngine(tmp_path / "t.db")
    with pytest.raises(Exception, match=r"zhihu-backup\[kuzu\]") as excinfo:
        sync_to_kuzu(eng, tmp_path / "kuzu")
    assert "zhihu-backup[kuzu]" in str(excinfo.value)
    eng.close()


@pytest.mark.kuzu
@pytest.mark.skipif(
    importlib.util.find_spec("kuzu") is None,
    reason="kuzu not installed",
)
def test_query_kuzu_follows_depth_2_matches_query_graph(tmp_path: Path):
    eng = SqliteEngine(tmp_path / "t.db")
    _seed(eng)
    db_path = tmp_path / "kuzu"
    stats = sync_to_kuzu(eng, db_path)
    assert stats["nodes"] >= 1
    assert stats["edges"] >= 2
    mem = query_graph(eng, start="user:me", depth=2, kinds={"follows"})
    kuz = query_kuzu(db_path, start="user:me", depth=2, kinds={"follows"})
    assert kuz["start"] == mem["start"]
    assert kuz["depth"] == mem["depth"]
    assert kuz["kinds"] == mem["kinds"]
    assert {n["id"] for n in kuz["nodes"]} == {n["id"] for n in mem["nodes"]}
    eng.close()
