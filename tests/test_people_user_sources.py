from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from auth import parse_people_ref
from models import item_key
from parse import normalize_content
from sources import build_sources
from sources.member_page import MemberPagedSource, unwrap_activity_row


def test_parse_people_ref_token_and_url():
    assert parse_people_ref("example_token") == "example_token"
    assert parse_people_ref("/example_token") == "example_token"
    assert parse_people_ref("people/example_token") == "example_token"
    assert parse_people_ref("/people/example_token") == "example_token"
    assert parse_people_ref("https://www.zhihu.com/people/example_token") == "example_token"
    assert parse_people_ref("https://www.zhihu.com/people/example_token/answers") == "example_token"
    assert parse_people_ref("https://www.zhihu.com/people/example_token?x=1") == "example_token"


def test_parse_people_ref_rejects_empty():
    with pytest.raises(ValueError):
        parse_people_ref("")
    with pytest.raises(ValueError):
        parse_people_ref("https://www.zhihu.com/")


def test_build_sources_people_uses_user_no_me():
    client = MagicMock()
    client.get_json.return_value = {"data": [], "paging": {"is_end": True}}
    sources = build_sources(client, source="people", user_id="example_token", collection_ids=[])
    names = [s.name for s in sources]
    assert "following" in names
    assert "followers" in names
    assert "answer" in names
    assert "activity" in names
    assert "pin" in names
    assert all(s.source_id == "example_token" for s in sources if s.name != "collection")
    # discovery may call collections URL; must not call /me
    called_urls = [c.args[0] for c in client.get_json.call_args_list if c.args]
    assert not any(u == "/api/v4/me" or str(u).endswith("/me") for u in called_urls)


def test_build_sources_all_with_user_excludes_social():
    client = MagicMock()
    client.get_json.return_value = {"data": [], "paging": {"is_end": True}}
    names = {s.name for s in build_sources(client, source="all", user_id="example_token")}
    assert "following" not in names
    assert "followers" not in names
    assert "answer" in names
    assert "article" in names


def test_build_sources_people_without_user_empty():
    client = MagicMock()
    assert build_sources(client, source="people", collection_ids=[]) == []
    client.get_json.assert_not_called()


def test_activity_unwrap_matches_answer_item_key():
    answer = {
        "type": "answer",
        "id": "99",
        "question": {"id": "1", "title": "Q"},
        "content": "<p>hi</p>",
        "author": {"name": "A"},
    }
    row = {"type": "CREATE_ANSWER", "target": answer}
    unwrapped = unwrap_activity_row(row)
    assert unwrapped is not None
    item = normalize_content(
        unwrapped,
        owner_kind="activities",
        owner_id="example_token",
        source_tag="activity:example_token",
    )
    direct = normalize_content(
        answer,
        owner_kind="answers",
        owner_id="example_token",
        source_tag="answer:example_token",
    )
    assert item is not None and direct is not None
    assert item.key == direct.key == item_key("answer", "99", "1")


def test_member_answer_source_paging():
    client = MagicMock()
    client.get_json.side_effect = [
        {
            "data": [
                {
                    "type": "answer",
                    "id": "10",
                    "question": {"id": "2", "title": "T"},
                    "content": "<p>x</p>",
                    "author": {"name": "A"},
                }
            ],
            "paging": {"is_end": True, "totals": 1},
        }
    ]
    src = MemberPagedSource(
        client,
        "example_token",
        name="answer",
        resource="answers",
        owner_kind="answers",
        source_tag_prefix="answer",
    )
    batches = list(src.iter_items(offset=0, limit=20))
    assert len(batches) == 1
    assert len(batches[0][1]) == 1
    assert batches[0][1][0].zhihu_id == "10"


def test_member_paged_source_soft_404():
    client = MagicMock()
    client.get_json.side_effect = FileNotFoundError("HTTP 404")
    src = MemberPagedSource(
        client,
        "example_token",
        name="vote",
        resource="votes",
        owner_kind="votes",
        source_tag_prefix="vote",
    )
    assert src.total() == 0
    assert list(src.iter_items()) == []


def test_pipeline_404_does_not_count_source_error(tmp_path):
    from pipeline import Pipeline
    from sources.base import Source
    from storage import open_engine

    class Boom(Source):
        name = "vote"
        source_id = "example_token"

        def total(self):
            return None

        def iter_items(self, offset=0, limit=20):
            raise FileNotFoundError("HTTP 404 for GET .../votes")

    engine = open_engine("sqlite", tmp_path / "meta")
    pipe = Pipeline(engine, tmp_path / "contents", tmp_path / "assets")
    stats = pipe.run([Boom()], resume=False)
    assert stats.source_errors == 0
    engine.close()
