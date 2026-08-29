from __future__ import annotations

from typing import Iterator, Optional

from http_client import ZhihuClient
from models import NormalizedItem
from sources.base import Source


class FollowersSource(Source):
    name = "followers"

    def __init__(self, client: ZhihuClient, user_id: str):
        self.client = client
        self.source_id = str(user_id)
        self._api = f"https://www.zhihu.com/api/v4/members/{self.source_id}/followers"

    def total(self) -> Optional[int]:
        data = self.client.get_json(self._api, params={"offset": 0, "limit": 1})
        return int((data.get("paging") or {}).get("totals") or 0)

    def iter_items(self, offset: int = 0, limit: int = 20) -> Iterator[tuple[int, list[NormalizedItem]]]:
        from parse import normalize_member

        current = offset
        while True:
            data = self.client.get_json(self._api, params={"offset": current, "limit": limit})
            rows = data.get("data") or []
            items: list[NormalizedItem] = []
            for row in rows:
                member = row.get("author") if isinstance(row.get("author"), dict) else row
                if not isinstance(member, dict):
                    continue
                item = normalize_member(
                    member, center_id=self.source_id, source_name=self.name
                )
                if item:
                    items.append(item)
            next_offset = current + len(rows)
            yield next_offset, items
            paging = data.get("paging") or {}
            if not rows or paging.get("is_end"):
                break
            current = next_offset
