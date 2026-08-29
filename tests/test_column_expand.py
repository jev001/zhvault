from __future__ import annotations

from unittest.mock import MagicMock

from sources.column_expand import ColumnExpandSource, article_id_from_column_item_row
from zhihu_lists import column_items_url, column_key


def test_column_key_prefers_url_token():
    assert column_key({"id": "1", "url_token": "c_abc"}) == "c_abc"
    assert column_key({"id": "99"}) == "99"


def test_column_items_url():
    assert column_items_url("c_2074890283800645989").endswith(
        "/columns/c_2074890283800645989/items"
    )


def test_article_id_from_row_shapes():
    assert article_id_from_column_item_row({"type": "article", "id": "10"}) == "10"
    assert (
        article_id_from_column_item_row({"content": {"type": "article", "id": "11"}})
        == "11"
    )
    assert article_id_from_column_item_row({"type": "pin", "id": "1"}) is None


def test_column_expand_fetches_items_and_article_details():
    client = MagicMock()

    def get_json(url, params=None):
        u = str(url)
        if "column-contributions" in u or u.endswith("/columns"):
            return {
                "data": [
                    {
                        "column": {
                            "id": "9",
                            "url_token": "c_tok",
                            "title": "Col",
                            "type": "column",
                            "intro": "<p>hi</p>",
                        }
                    }
                ],
                "paging": {"is_end": True},
            }
        if "/columns/c_tok/items" in u:
            return {
                "data": [
                    {"type": "article", "id": "101"},
                    {"type": "article", "id": "102"},
                ],
                "paging": {"is_end": True},
            }
        if u.endswith("/articles/101"):
            return {
                "id": "101",
                "type": "article",
                "title": "A1",
                "content": "<p>one</p>",
                "updated": 1,
            }
        if u.endswith("/articles/102"):
            return {
                "id": "102",
                "type": "article",
                "title": "A2",
                "content": "<p>two</p>",
                "updated": 2,
            }
        raise AssertionError(f"unexpected url {u}")

    client.get_json.side_effect = get_json
    src = ColumnExpandSource(client, "example_token")
    pages = list(src.iter_items(offset=0, limit=20))
    assert len(pages) == 1
    _off, items = pages[0]
    types = [i.item_type for i in items]
    assert types[0] == "column"
    assert types[1:] == ["article", "article"]
    col = items[0]
    assert "## Articles" in col.markdown_body
    assert "[[contents/articles/example_token/article_c_tok_101]]" in col.markdown_body
    assert "[[contents/articles/example_token/article_c_tok_102]]" in col.markdown_body
    assert items[1].owner_kind == "articles"
    assert items[1].parent_id == "c_tok"
    assert items[1].sources == ["column-items:c_tok"]
    urls = [c.args[0] for c in client.get_json.call_args_list]
    assert any("/articles/101" in u for u in urls)
    assert any("/articles/102" in u for u in urls)


def test_column_expand_skips_failed_article_detail():
    client = MagicMock()

    def get_json(url, params=None):
        u = str(url)
        if "column-contributions" in u:
            return {
                "data": [
                    {
                        "column": {
                            "id": "1",
                            "url_token": "c_x",
                            "title": "C",
                            "type": "column",
                        }
                    }
                ],
                "paging": {"is_end": True},
            }
        if "/items" in u:
            return {"data": [{"type": "article", "id": "1"}], "paging": {"is_end": True}}
        if "/articles/1" in u:
            raise FileNotFoundError("HTTP 404")
        raise AssertionError(u)

    client.get_json.side_effect = get_json
    src = ColumnExpandSource(client, "u")
    _off, items = next(iter(src.iter_items()))
    assert len(items) == 1
    assert items[0].item_type == "column"
