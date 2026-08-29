from __future__ import annotations

from typing import Iterable

from http_client import ZhihuClient
from sources.base import Source
from sources.collection import CollectionSource
from sources.pin import PinSource
from sources.asked_question import AskedQuestionSource
from sources.followed_question import FollowedQuestionSource
from sources.vote import VoteSource
from sources.following import FollowingSource
from sources.followers import FollowersSource


def build_sources(
    client: ZhihuClient,
    *,
    source: str = "all",
    collection_ids: Iterable[str] | None = None,
    url_me: str = "https://www.zhihu.com/api/v4/me",
) -> list[Source]:
    name = (source or "all").lower()
    sources: list[Source] = []

    if name in ("all", "collection", "collections"):
        ids = list(collection_ids or [])
        if not ids:
            # Discover from config elsewhere; empty means caller must pass ids.
            pass
        for cid in ids:
            sources.append(CollectionSource(client, cid))

    me = None
    need_me = name in (
        "all", "pin", "pins", "asked", "asked_questions", "followed", "followed_questions",
        "vote", "votes", "following", "followers", "social",
    )
    if need_me and name != "collection" and name != "collections":
        try:
            me = client.get_json(url_me)
        except Exception:
            me = {}
    user_id = str((me or {}).get("url_token") or (me or {}).get("id") or "")

    if name in ("all", "pin", "pins") and user_id:
        sources.append(PinSource(client, user_id))
    if name in ("all", "asked", "asked_questions") and user_id:
        sources.append(AskedQuestionSource(client, user_id))
    if name in ("all", "followed", "followed_questions") and user_id:
        sources.append(FollowedQuestionSource(client, user_id))
    if name in ("all", "vote", "votes") and user_id:
        sources.append(VoteSource(client, user_id))
    # NOTE: "all" must NOT include following/followers
    if name in ("following", "social") and user_id:
        sources.append(FollowingSource(client, user_id))
    if name in ("followers", "social") and user_id:
        sources.append(FollowersSource(client, user_id))

    return sources


__all__ = [
    "Source",
    "CollectionSource",
    "PinSource",
    "AskedQuestionSource",
    "FollowedQuestionSource",
    "VoteSource",
    "FollowingSource",
    "FollowersSource",
    "build_sources",
]
