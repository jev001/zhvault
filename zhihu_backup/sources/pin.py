from __future__ import annotations

from typing import Iterator, Optional

from zhihu_backup.http_client import ZhihuClient
from zhihu_backup.models import NormalizedItem
from zhihu_backup.parse import normalize_content
from zhihu_backup.sources.base import Source


class PinSource(Source):
    name = "pin"

    def __init__(self, client: ZhihuClient, user_id: str):
        self.client = client
        self.source_id = str(user_id)
        self._api = f"https://www.zhihu.com/api/v4/members/{self.source_id}/pins"

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
                item = normalize_content(
                    content if isinstance(content, dict) else row,
                    owner_kind="pins",
                    owner_id=self.source_id,
                    source_tag=f"pin:{self.source_id}",
                )
                if item:
                    items.append(item)
            next_offset = current + len(rows)
            yield next_offset, items
            paging = data.get("paging") or {}
            if not rows or paging.get("is_end"):
                break
            current = next_offset
