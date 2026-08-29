"""Zhihu person/member list URL registry (aligned with browser DevTools).

Some tabs use /api/v4/people/..., others /api/v4/members/.... Path suffixes and
include= query strings also differ (e.g. column-contributions vs columns).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from http_client import ZhihuClient

log = logging.getLogger("zhvault.zhihu_lists")

API_V4 = "https://www.zhihu.com/api/v4"

# From browser Network on people profile tabs.
INCLUDE_COLLECTIONS = (
    "data[*].updated_time,answer_count,follower_count,creator,description,"
    "is_following,comment_count,created_time;data[*].creator.kvip_info;"
    "data[*].creator.vip_info"
)
INCLUDE_COLUMN_CONTRIBUTIONS = (
    "data[*].column.intro,followers,articles_count,voteup_count,items_count"
)
INCLUDE_ARTICLES = (
    "data[*].comment_count,suggest_edit,is_normal,thumbnail_extra_info,thumbnail,"
    "can_comment,comment_permission,admin_closed_comment,content,voteup_count,"
    "created,updated,upvoted_followees,voting,review_info,reaction_instruction,"
    "is_labeled,label_info,reaction,vessay_info;"
    "data[*].author.badge[?(type=best_answerer)].topics;"
    "data[*].author.kvip_info;data[*].author.vip_info;"
)


@dataclass(frozen=True)
class ListRoute:
    """One candidate HTTP list route for a profile resource."""

    root: str  # "people" | "members"
    path: str  # e.g. collections, articles, column-contributions
    extra_params: dict[str, str] = field(default_factory=dict)


# Ordered candidates: first success wins. Unverified resources: members then people.
LIST_ROUTES: dict[str, tuple[ListRoute, ...]] = {
    "collections": (
        ListRoute("people", "collections", {"include": INCLUDE_COLLECTIONS}),
        ListRoute("members", "collections", {"include": INCLUDE_COLLECTIONS}),
    ),
    "articles": (
        ListRoute(
            "members",
            "articles",
            {
                "include": INCLUDE_ARTICLES,
                "sort_by": "created",
                "ws_qiangzhisafe": "0",
            },
        ),
        ListRoute(
            "people",
            "articles",
            {
                "include": INCLUDE_ARTICLES,
                "sort_by": "created",
                "ws_qiangzhisafe": "0",
            },
        ),
    ),
    "columns": (
        ListRoute("members", "column-contributions", {"include": INCLUDE_COLUMN_CONTRIBUTIONS}),
        ListRoute("people", "column-contributions", {"include": INCLUDE_COLUMN_CONTRIBUTIONS}),
        ListRoute("members", "columns"),
        ListRoute("people", "columns"),
    ),
    "answers": (
        ListRoute("members", "answers"),
        ListRoute("people", "answers"),
    ),
    "pins": (
        ListRoute("members", "pins"),
        ListRoute("people", "pins"),
    ),
    "questions": (
        ListRoute("members", "questions"),
        ListRoute("people", "questions"),
    ),
    "zvideos": (
        ListRoute("members", "zvideos"),
        ListRoute("people", "zvideos"),
    ),
    "activities": (
        ListRoute("members", "activities"),
        ListRoute("people", "activities"),
    ),
    "votes": (
        ListRoute("members", "votes"),
        ListRoute("people", "votes"),
    ),
    "followees": (
        ListRoute("members", "followees"),
        ListRoute("people", "followees"),
    ),
    "followers": (
        ListRoute("members", "followers"),
        ListRoute("people", "followers"),
    ),
    "following-questions": (
        ListRoute("members", "following-questions"),
        ListRoute("people", "following-questions"),
    ),
}


def list_url(token: str, route: ListRoute) -> str:
    return f"{API_V4}/{route.root}/{token}/{route.path.lstrip('/')}"


def routes_for(resource: str) -> tuple[ListRoute, ...]:
    key = (resource or "").strip().lower()
    if key in LIST_ROUTES:
        return LIST_ROUTES[key]
    # Unknown: try members then people with the raw path as suffix.
    return (ListRoute("members", key), ListRoute("people", key))


def fetch_person_list(
    client: ZhihuClient,
    token: str,
    resource: str,
    *,
    offset: int = 0,
    limit: int = 20,
    _bound: dict[str, ListRoute] | None = None,
) -> dict[str, Any]:
    """GET a paginated person list; try registry routes until one works.

    On success, optionally record the winning route in ``_bound[resource]`` so
    later pages reuse the same prefix/path (avoids flip-flopping).
    """
    token = str(token).strip()
    resource = (resource or "").strip().lower()
    if _bound is not None and resource in _bound:
        route = _bound[resource]
        params = {"offset": offset, "limit": limit, **route.extra_params}
        return client.get_json(list_url(token, route), params=params)

    last_404: Exception | None = None
    for route in routes_for(resource):
        url = list_url(token, route)
        params = {"offset": offset, "limit": limit, **route.extra_params}
        try:
            data = client.get_json(url, params=params)
        except FileNotFoundError as e:
            last_404 = e
            log.info("list 404 %s — try next route", url)
            continue
        log.info(
            "list ok resource=%s root=%s path=%s token=%s",
            resource,
            route.root,
            route.path,
            token,
        )
        if _bound is not None:
            _bound[resource] = route
        return data if isinstance(data, dict) else {}
    if last_404:
        raise last_404
    raise FileNotFoundError(f"no list route for resource={resource!r} token={token!r}")


def fetch_profile(client: ZhihuClient, token: str) -> dict[str, Any]:
    """Resolve profile JSON via /members then /people."""
    token = str(token).strip()
    last_err: Exception | None = None
    for root in ("members", "people"):
        url = f"{API_V4}/{root}/{token}"
        try:
            data = client.get_json(url)
        except FileNotFoundError as e:
            last_err = e
            continue
        except Exception as e:
            last_err = e
            continue
        if isinstance(data, dict) and (data.get("url_token") or data.get("id") or data.get("name")):
            log.info("profile ok root=%s token=%s", root, token)
            return data
        if isinstance(data, dict) and data.get("error"):
            last_err = ValueError(str(data.get("error")))
            continue
    if last_err:
        raise last_err
    raise FileNotFoundError(f"profile not found for token={token!r}")


def column_key(column: dict[str, Any]) -> str:
    """Prefer url_token (e.g. c_…) for /columns/{key}/items."""
    token = str(column.get("url_token") or "").strip()
    if token:
        return token
    return str(column.get("id") or "").strip()


def column_items_url(column_key_s: str) -> str:
    return f"{API_V4}/columns/{str(column_key_s).strip()}/items"


def fetch_column_items(
    client: ZhihuClient,
    column_key_s: str,
    *,
    offset: int = 0,
    limit: int = 20,
) -> dict[str, Any]:
    key = str(column_key_s).strip()
    keys = [key]
    # Single fallback: if key looks numeric-only, also try as-is only; if url_token failed, caller may retry id.
    params = {"offset": offset, "limit": limit, "ws_qiangzhisafe": "0"}
    last_404: Exception | None = None
    for k in keys:
        try:
            data = client.get_json(column_items_url(k), params=params)
        except FileNotFoundError as e:
            last_404 = e
            continue
        return data if isinstance(data, dict) else {}
    if last_404:
        raise last_404
    raise FileNotFoundError(f"column items not found for key={column_key_s!r}")


def fetch_column_items_with_key_fallback(
    client: ZhihuClient,
    column: dict[str, Any],
    *,
    offset: int = 0,
    limit: int = 20,
) -> tuple[str, dict[str, Any]]:
    """Try url_token then id once each on 404. Returns (winning_key, payload)."""
    primary = column_key(column)
    alt = str(column.get("id") or "").strip()
    candidates = [primary]
    if alt and alt != primary:
        candidates.append(alt)
    last_404: Exception | None = None
    for k in candidates:
        if not k:
            continue
        try:
            data = fetch_column_items(client, k, offset=offset, limit=limit)
            return k, data
        except FileNotFoundError as e:
            last_404 = e
            log.info("column items 404 key=%s — try next", k)
            continue
    if last_404:
        raise last_404
    raise FileNotFoundError(f"column items not found for column={primary!r}")


def fetch_article_detail(client: ZhihuClient, article_id: str) -> dict[str, Any]:
    """Delegate to article_detail (API + zhuanlan HTML fallback)."""
    from article_detail import fetch_article_detail as _fetch

    return _fetch(client, article_id)
