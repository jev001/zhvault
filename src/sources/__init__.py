from __future__ import annotations

from collections.abc import Iterable

from http_client import ZhihuClient
from mutate.endpoints import member_collections_url
from sources.asked_question import AskedQuestionSource
from sources.base import Source
from sources.collection import CollectionSource
from sources.followed_question import FollowedQuestionSource
from sources.followers import FollowersSource
from sources.following import FollowingSource
from sources.member_page import (
    MemberPagedSource,
    unwrap_activity_row,
    unwrap_column_row,
    unwrap_content_row,
)
from sources.pin import PinSource
from sources.vote import VoteSource


def list_member_collection_ids(client: ZhihuClient, url_token: str, *, max_pages: int = 250) -> list[str]:
    """Discover public collection ids for a member (GET only)."""
    url = member_collections_url(url_token)
    ids: list[str] = []
    offset = 0
    pages = 0
    while pages < max_pages:
        data = client.get_json(url, params={"offset": offset, "limit": 20})
        rows = data.get("data") or []
        if not rows:
            break
        for row in rows:
            if not isinstance(row, dict):
                continue
            cid = str(row.get("id") or (row.get("collection") or {}).get("id") or "")
            if cid and cid not in ids:
                ids.append(cid)
        paging = data.get("paging") or {}
        if paging.get("is_end"):
            break
        offset += len(rows)
        pages += 1
    return ids


def _member_answer(client: ZhihuClient, user_id: str) -> Source:
    return MemberPagedSource(
        client,
        user_id,
        name="answer",
        path="answers",
        owner_kind="answers",
        source_tag_prefix="answer",
        unwrap=unwrap_content_row,
    )


def _member_article(client: ZhihuClient, user_id: str) -> Source:
    return MemberPagedSource(
        client,
        user_id,
        name="article",
        path="articles",
        owner_kind="articles",
        source_tag_prefix="article",
        unwrap=unwrap_content_row,
    )


def _member_column(client: ZhihuClient, user_id: str) -> Source:
    return MemberPagedSource(
        client,
        user_id,
        name="column",
        path="columns",
        owner_kind="columns",
        source_tag_prefix="column",
        unwrap=unwrap_column_row,
    )


def _member_zvideo(client: ZhihuClient, user_id: str) -> Source:
    return MemberPagedSource(
        client,
        user_id,
        name="zvideo",
        path="zvideos",
        owner_kind="zvideos",
        source_tag_prefix="zvideo",
        unwrap=unwrap_content_row,
    )


def _member_activity(client: ZhihuClient, user_id: str) -> Source:
    return MemberPagedSource(
        client,
        user_id,
        name="activity",
        path="activities",
        owner_kind="activities",
        source_tag_prefix="activity",
        unwrap=unwrap_activity_row,
    )


def build_sources(
    client: ZhihuClient,
    *,
    source: str = "all",
    collection_ids: Iterable[str] | None = None,
    user_id: str | None = None,
    url_me: str = "https://www.zhihu.com/api/v4/me",
) -> list[Source]:
    name = (source or "all").lower()
    sources: list[Source] = []
    explicit_user = bool(user_id)
    resolved_user = str(user_id).strip() if user_id else ""

    if name == "people" and not resolved_user:
        return []

    need_me = (
        not resolved_user
        and name
        in (
            "all",
            "pin",
            "pins",
            "asked",
            "asked_questions",
            "followed",
            "followed_questions",
            "vote",
            "votes",
            "following",
            "followers",
            "social",
            "answer",
            "answers",
            "article",
            "articles",
            "column",
            "columns",
            "zvideo",
            "zvideos",
            "activity",
            "activities",
            "people",
        )
    )
    if need_me:
        try:
            me = client.get_json(url_me)
        except Exception:
            me = {}
        resolved_user = str((me or {}).get("url_token") or (me or {}).get("id") or "")

    coll_ids = list(collection_ids or [])
    discover_collections = name in ("people",) or (name == "all" and explicit_user)
    if discover_collections and resolved_user and not coll_ids:
        try:
            coll_ids = list_member_collection_ids(client, resolved_user)
        except Exception:
            coll_ids = []

    if name in ("all", "collection", "collections", "people"):
        for cid in coll_ids:
            sources.append(CollectionSource(client, cid))

    if not resolved_user:
        return sources

    # people bundle
    if name == "people":
        sources.extend(
            [
                _member_activity(client, resolved_user),
                _member_answer(client, resolved_user),
                _member_zvideo(client, resolved_user),
                AskedQuestionSource(client, resolved_user),
                _member_article(client, resolved_user),
                _member_column(client, resolved_user),
                PinSource(client, resolved_user),
                FollowingSource(client, resolved_user),
                FollowersSource(client, resolved_user),
            ]
        )
        return sources

    # --source all: existing shape; with --user also includes answer/article/column/zvideo/activity
    if name == "all":
        sources.append(PinSource(client, resolved_user))
        sources.append(AskedQuestionSource(client, resolved_user))
        sources.append(FollowedQuestionSource(client, resolved_user))
        sources.append(VoteSource(client, resolved_user))
        if explicit_user:
            sources.extend(
                [
                    _member_activity(client, resolved_user),
                    _member_answer(client, resolved_user),
                    _member_article(client, resolved_user),
                    _member_column(client, resolved_user),
                    _member_zvideo(client, resolved_user),
                ]
            )
        return sources

    if name in ("pin", "pins"):
        sources.append(PinSource(client, resolved_user))
    if name in ("asked", "asked_questions"):
        sources.append(AskedQuestionSource(client, resolved_user))
    if name in ("followed", "followed_questions"):
        sources.append(FollowedQuestionSource(client, resolved_user))
    if name in ("vote", "votes"):
        sources.append(VoteSource(client, resolved_user))
    if name in ("answer", "answers"):
        sources.append(_member_answer(client, resolved_user))
    if name in ("article", "articles"):
        sources.append(_member_article(client, resolved_user))
    if name in ("column", "columns"):
        sources.append(_member_column(client, resolved_user))
    if name in ("zvideo", "zvideos"):
        sources.append(_member_zvideo(client, resolved_user))
    if name in ("activity", "activities"):
        sources.append(_member_activity(client, resolved_user))
    # NOTE: "all" must NOT include following/followers
    if name in ("following", "social"):
        sources.append(FollowingSource(client, resolved_user))
    if name in ("followers", "social"):
        sources.append(FollowersSource(client, resolved_user))

    return sources


__all__ = [
    "AskedQuestionSource",
    "CollectionSource",
    "FollowedQuestionSource",
    "FollowersSource",
    "FollowingSource",
    "MemberPagedSource",
    "PinSource",
    "Source",
    "VoteSource",
    "build_sources",
    "list_member_collection_ids",
]
