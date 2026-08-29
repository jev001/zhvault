from __future__ import annotations

from unittest.mock import MagicMock

from zhihu_lists import LIST_ROUTES, fetch_person_list, list_url, routes_for


def test_collections_prefers_people_route():
    routes = routes_for("collections")
    assert routes[0].root == "people"
    assert routes[0].path == "collections"
    assert "include" in routes[0].extra_params


def test_columns_uses_column_contributions():
    routes = routes_for("columns")
    assert routes[0].path == "column-contributions"
    assert routes[0].root == "members"


def test_articles_include_and_sort():
    r = routes_for("articles")[0]
    assert r.path == "articles"
    assert r.extra_params.get("sort_by") == "created"
    assert "include" in r.extra_params


def test_fetch_person_list_falls_back_after_404():
    client = MagicMock()

    def side_effect(url, params=None):
        if "/people/" in url:
            raise FileNotFoundError("HTTP 404")
        return {"data": [{"id": "1", "title": "c"}], "paging": {"is_end": True}}

    client.get_json.side_effect = side_effect
    data = fetch_person_list(client, "example_token", "collections", offset=0, limit=20)
    assert data["data"][0]["id"] == "1"
    urls = [c.args[0] for c in client.get_json.call_args_list]
    assert any("/people/example_token/collections" in u for u in urls)
    assert any("/members/example_token/collections" in u for u in urls)


def test_fetch_person_list_binds_winning_route():
    client = MagicMock()
    client.get_json.return_value = {"data": [], "paging": {"is_end": True}}
    bound: dict = {}
    fetch_person_list(client, "example_token", "articles", _bound=bound)
    assert "articles" in bound
    first_url = client.get_json.call_args_list[0].args[0]
    assert "/members/example_token/articles" in first_url
    # second page uses bound route only
    client.get_json.reset_mock()
    fetch_person_list(client, "example_token", "articles", offset=20, _bound=bound)
    assert client.get_json.call_count == 1
    assert "/members/example_token/articles" in client.get_json.call_args.args[0]


def test_list_url_shape():
    from zhihu_lists import ListRoute

    u = list_url("example_token", ListRoute("people", "collections"))
    assert u == "https://www.zhihu.com/api/v4/people/example_token/collections"


def test_all_registered_resources_have_routes():
    for key in (
        "collections",
        "articles",
        "columns",
        "answers",
        "pins",
        "questions",
        "zvideos",
        "activities",
        "votes",
        "followees",
        "followers",
        "following-questions",
    ):
        assert key in LIST_ROUTES
        assert len(LIST_ROUTES[key]) >= 1


def test_fetch_profile_prefers_members():
    from zhihu_lists import fetch_profile

    client = MagicMock()
    client.get_json.return_value = {"url_token": "example_token", "name": "N"}
    out = fetch_profile(client, "example_token")
    assert out["url_token"] == "example_token"
    assert client.get_json.call_count == 1
    assert "/members/example_token" in client.get_json.call_args.args[0]
    assert "/people/" not in client.get_json.call_args.args[0]
