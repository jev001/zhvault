from __future__ import annotations

from collections.abc import Iterator

from http_client import ZhihuClient
from models import NormalizedItem
from parse import normalize_collection_item
from sources.base import Source


class CollectionSource(Source):
    name = "collection"

    def __init__(self, client: ZhihuClient, collection_id: str):
        self.client = client
        self.source_id = str(collection_id)
        self._api = f"https://www.zhihu.com/api/v4/collections/{self.source_id}/items"

    def total(self) -> int | None:
        data = self.client.get_json(self._api, params={"offset": 0, "limit": 1})
        return int((data.get("paging") or {}).get("totals") or 0)

    def iter_items(self, offset: int = 0, limit: int = 20) -> Iterator[tuple[int, list[NormalizedItem]]]:
        current = offset
        while True:
            data = self.client.get_json(self._api, params={"offset": current, "limit": limit})
            rows = data.get("data") or []
            items: list[NormalizedItem] = []
            for row in rows:
                item = normalize_collection_item(row, collection_id=self.source_id)
                if item:
                    items.append(item)
            next_offset = current + len(rows)
            yield next_offset, items
            paging = data.get("paging") or {}
            if not rows or paging.get("is_end"):
                break
            current = next_offset
