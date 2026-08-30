from __future__ import annotations

from unittest.mock import MagicMock

from article_detail import (
    article_payload_usable,
    fetch_article_detail,
    parse_zhuanlan_html,
)


def test_article_payload_rejects_10003():
    assert not article_payload_usable({"error": {"message": "bad params", "code": 10003}})
    assert article_payload_usable(
        {"id": "1", "type": "article", "title": "t", "content": "<p>x</p>"}
    )


def test_parse_zhuanlan_js_initial_data():
    html = """
    <html><head></head><body>
    <script id="js-initialData" type="text/json">
    {"initialState":{"entities":{"articles":{"44839349":{
      "id":"44839349","type":"article","title":"Hello","content":"<p>body</p>"
    }}}}}
    </script>
    </body></html>
    """
    out = parse_zhuanlan_html(html, "44839349")
    assert out is not None
    assert out["title"] == "Hello"
    assert "<p>body</p>" in out["content"]


def test_fetch_article_detail_uses_referer_then_html_fallback():
    client = MagicMock()
    client.get_json.return_value = {"error": {"message": "bad params", "code": 10003}}
    client.get_text.return_value = """
    <script id="js-initialData" type="text/json">
    {"a":{"id":"44839349","type":"article","title":"T","content":"<p>c</p>"}}
    </script>
    """
    out = fetch_article_detail(client, "44839349")
    assert out["title"] == "T"
    assert client.get_json.called
    kwargs = client.get_json.call_args.kwargs
    assert kwargs.get("headers", {}).get("Referer") == "https://zhuanlan.zhihu.com/p/44839349"
    client.get_text.assert_called_once()
    assert "zhuanlan.zhihu.com/p/44839349" in client.get_text.call_args.args[0]
    html_headers = client.get_text.call_args.kwargs.get("headers") or {}
    assert html_headers.get("sec-fetch-dest") == "document"
    assert html_headers.get("x-requested-with") is None


def test_fetch_article_detail_api_ok_skips_html():
    client = MagicMock()
    client.get_json.return_value = {
        "id": "9",
        "type": "article",
        "title": "API",
        "content": "<p>ok</p>",
    }
    out = fetch_article_detail(client, "9")
    assert out["title"] == "API"
    client.get_text.assert_not_called()
