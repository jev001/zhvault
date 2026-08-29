"""Pinned Zhihu write/list URL helpers for account mutate (FCQ).

Paths verified against community clients / userscripts; live smoke is manual.
"""

from __future__ import annotations

ME_URL = "https://www.zhihu.com/api/v4/me"


def follow_user_url(url_token: str) -> str:
    return f"https://www.zhihu.com/api/v4/members/{url_token}/followers"


def follow_question_url(question_id: str) -> str:
    return f"https://www.zhihu.com/api/v4/questions/{question_id}/followers"


def collection_contents_url(collection_id: str) -> str:
    return f"https://www.zhihu.com/api/v4/collections/{collection_id}/contents"


def collection_content_item_url(collection_id: str, content_id: str) -> str:
    return f"https://www.zhihu.com/api/v4/collections/{collection_id}/contents/{content_id}"


def collection_meta_url(collection_id: str) -> str:
    return f"https://www.zhihu.com/api/v4/collections/{collection_id}"


def create_collection_url() -> str:
    return "https://www.zhihu.com/api/v4/favlists"


def member_collections_url(url_token: str) -> str:
    return f"https://www.zhihu.com/api/v4/members/{url_token}/collections"
