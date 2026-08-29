from __future__ import annotations

from unittest.mock import MagicMock

from parse import enrich_question_detail, normalize_content, question_payload_from_row


def test_question_payload_from_row_nested():
    row = {"question": {"id": "1", "title": "t"}}
    q = question_payload_from_row(row)
    assert q["type"] == "question"
    assert q["id"] == "1"


def test_enrich_question_detail_fetches_when_empty():
    client = MagicMock()
    client.get_json.return_value = {"id": "42", "detail": "<p>body</p>", "title": "T"}
    content = {"id": "42", "type": "question", "title": "T"}
    out = enrich_question_detail(client, content)
    client.get_json.assert_called_once()
    assert out["detail"] == "<p>body</p>"
    item = normalize_content(out, owner_kind="followed_questions", owner_id="u", source_tag="followed:u")
    assert item is not None
    assert "body" in item.markdown_body
    assert item.url == "https://www.zhihu.com/question/42"


def test_enrich_skips_fetch_when_detail_present():
    client = MagicMock()
    content = {"id": "1", "type": "question", "detail": "<p>x</p>"}
    enrich_question_detail(client, content)
    client.get_json.assert_not_called()
