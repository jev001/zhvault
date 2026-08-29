from pathlib import Path

from graph import rebuild_graph
from models import GraphEdge, ItemRecord
from storage.sqlite_engine import SqliteEngine


def test_rebuild_derives_answers_and_asked(tmp_path: Path):
    eng = SqliteEngine(tmp_path / "t.db")
    eng.upsert_item(
        ItemRecord(
            key="answer:10:20",
            item_type="answer",
            zhihu_id="20",
            title="A",
            url="https://www.zhihu.com/question/10/answer/20",
            path="contents/votes/me/answer_10_20.md",
            extra={"question_id": "10", "parent_id": "10"},
        )
    )
    eng.upsert_item(
        ItemRecord(key="question:10", item_type="question", zhihu_id="10", title="Q")
    )
    eng.link_membership("question:10", "asked_questions", "me_token")
    eng.upsert_graph_edge(
        GraphEdge(
            from_id="user:me_token",
            to_id="user:friend",
            kind="follows",
            origin="manual",
            seen_at="2026-01-01T00:00:00Z",
        )
    )
    meta = tmp_path / "meta"
    meta.mkdir()
    people = tmp_path / "contents" / "people"
    people.mkdir(parents=True)
    (people / "me_token.md").write_text("---\ntitle: Me\n---\n\nbody\n", encoding="utf-8")
    out = rebuild_graph(eng, tmp_path / "contents", meta, ego="me_token")
    assert (meta / "graph.json").exists()
    kinds = {(e["from"], e["to"], e["kind"], e["origin"]) for e in out["edges"]}
    assert ("answer:10:20", "question:10", "answers", "derived") in kinds
    assert ("user:me_token", "question:10", "asked", "derived") in kinds
    assert ("user:me_token", "user:friend", "follows", "manual") in kinds
    eng.close()
