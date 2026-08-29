from __future__ import annotations

from typing import Iterator, Optional

from http_client import ZhihuClient
from models import NormalizedItem
from parse import normalize_content
from sources.base import Source


class VoteSource(Source):
    name = "vote"

    def __init__(self, client: ZhihuClient, user_id: str):
        self.client = client
        self.source_id = str(user_id)
        self._api = f"https://www.zhihu.com/api/v4/members/{self.source_id}/votes"

    def total(self) -> Optional[int]:
        data = self.client.get_json(self._api, params={"offset": 0, "limit": 1})
        return int((data.get("paging") or {}).get("totals") or 0)

    def iter_items(self, offset: int = 0, limit: int = 20) -> Iterator[tuple[int, list[NormalizedItem]]]:
        current = offset
        while True:
            data = self.client.get_json(self._api, params={"offset": current, "limit": limit})
            rows = data.get("data") or []
            items: list[NormalizedItem] = []
            for row in rows:
                content = row.get("content") if isinstance(row.get("content"), dict) else row
                if not isinstance(content, dict):
                    continue
                item = normalize_content(
                    content,
                    owner_kind="votes",
                    owner_id=self.source_id,
                    source_tag=f"vote:{self.source_id}",
                )
                if item:
                    items.append(item)
            next_offset = current + len(rows)
            yield next_offset, items
            paging = data.get("paging") or {}
            if not rows or paging.get("is_end"):
                break
            current = next_offset
