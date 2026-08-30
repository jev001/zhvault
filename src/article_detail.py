"""Fetch Zhihu article JSON: API (+ Referer) with zhuanlan HTML fallback."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from http_client import ZHUANLAN_DOCUMENT_HEADERS, ZhihuClient

log = logging.getLogger("zhvault.article")

API_V4 = "https://www.zhihu.com/api/v4"
ZHUANLAN_P = "https://zhuanlan.zhihu.com/p/{aid}"


def article_payload_usable(data: dict[str, Any] | None) -> bool:
    if not isinstance(data, dict) or not data:
        return False
    err = data.get("error")
    if isinstance(err, dict) and err.get("code") is not None:
        return False
    if err:
        return False
    content = data.get("content")
    if isinstance(content, str) and content.strip():
        return True
    return bool(data.get("title") and (data.get("id") or data.get("url")))


def _walk_find_article(obj: Any, aid: str) -> dict[str, Any] | None:
    """DFS for a dict that looks like this article."""
    if isinstance(obj, dict):
        oid = str(obj.get("id") or obj.get("articleId") or "")
        typ = str(obj.get("type") or "").lower()
        if (
            oid == aid
            and (typ in ("", "article", "post") or obj.get("content") or obj.get("title"))
            and (obj.get("content") or obj.get("title"))
        ):
            out = dict(obj)
            if not out.get("type"):
                out["type"] = "article"
            return out
        for v in obj.values():
            found = _walk_find_article(v, aid)
            if found:
                return found
    elif isinstance(obj, list):
        for v in obj:
            found = _walk_find_article(v, aid)
            if found:
                return found
    return None


_JS_INITIAL = re.compile(
    r'<script[^>]*id=["\']js-initialData["\'][^>]*>(.*?)</script>',
    re.I | re.S,
)
_NEXT_DATA = re.compile(
    r'<script[^>]*id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>',
    re.I | re.S,
)
_OG_TITLE = re.compile(
    r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)["\']',
    re.I,
)
# Rich text block sometimes in #content or .Post-RichText
_POST_HTML = re.compile(
    r'<div[^>]+class=["\'][^"\']*Post-RichText[^"\']*["\'][^>]*>(.*?)</div>\s*(?:</div>|<div)',
    re.I | re.S,
)


def parse_zhuanlan_html(html: str, article_id: str) -> dict[str, Any] | None:
    """Extract article-like dict from zhuanlan HTML (best-effort)."""
    aid = str(article_id).strip()
    if not html or not aid:
        return None

    for rx in (_JS_INITIAL, _NEXT_DATA):
        m = rx.search(html)
        if not m:
            continue
        raw = (m.group(1) or "").strip()
        if not raw:
            continue
        try:
            blob = json.loads(raw)
        except json.JSONDecodeError:
            continue
        found = _walk_find_article(blob, aid)
        if found and article_payload_usable(found):
            found.setdefault("url", ZHUANLAN_P.format(aid=aid))
            return found

    # og:title + Post-RichText fallback
    title = ""
    tm = _OG_TITLE.search(html)
    if tm:
        title = tm.group(1).strip()
    body = ""
    pm = _POST_HTML.search(html)
    if pm:
        body = pm.group(1).strip()
    if title or body:
        return {
            "id": aid,
            "type": "article",
            "title": title or f"article_{aid}",
            "content": body,
            "url": ZHUANLAN_P.format(aid=aid),
        }
    return None


def fetch_article_detail(client: ZhihuClient, article_id: str) -> dict[str, Any]:
    """API with zhuanlan Referer; on 10003/empty fall back to zhuanlan HTML page."""
    aid = str(article_id).strip()
    if not aid:
        return {}
    page_url = ZHUANLAN_P.format(aid=aid)
    api_url = f"{API_V4}/articles/{aid}"
    headers = {
        "Referer": page_url,
        "Origin": "https://zhuanlan.zhihu.com",
    }

    data: dict[str, Any] | None = None
    try:
        raw = client.get_json(api_url, headers=headers)
        data = raw if isinstance(raw, dict) else {}
    except Exception as e:
        log.info("article API failed id=%s: %s — try zhuanlan HTML", aid, e)
        data = None

    if isinstance(data, dict) and article_payload_usable(data):
        data.setdefault("url", page_url)
        return data

    if isinstance(data, dict) and data.get("error"):
        log.info(
            "article API error id=%s code=%s — try zhuanlan HTML (hint: --x-zse-96)",
            aid,
            (data.get("error") or {}).get("code"),
        )

    try:
        html = client.get_text(page_url, headers=dict(ZHUANLAN_DOCUMENT_HEADERS))
    except Exception as e:
        log.info("zhuanlan HTML failed id=%s: %s", aid, e)
        if isinstance(data, dict):
            return data
        raise

    parsed = parse_zhuanlan_html(html, aid)
    if parsed and article_payload_usable(parsed):
        log.info("article ok via zhuanlan HTML id=%s", aid)
        return parsed
    if isinstance(data, dict):
        return data
    return {}
