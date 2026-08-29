from __future__ import annotations

from collections.abc import Iterator

from http_client import ZhihuClient
from models import NormalizedItem
from parse import normalize_content
from sources.base import Source
from zhihu_lists import fetch_person_list


class PinSource(Source):
    name = "pin"

    def __init__(self, client: ZhihuClient, user_id: str):
        self.client = client
        self.source_id = str(user_id)
        self._bound: dict = {}

    def total(self) -> int | None:
        try:
            data = fetch_person_list(
                self.client, self.source_id, "pins", offset=0, limit=1, _bound=self._bound
            )
        except FileNotFoundError:
            return 0
        return int((data.get("paging") or {}).get("totals") or 0)

    def iter_items(self, offset: int = 0, limit: int = 20) -> Iterator[tuple[int, list[NormalizedItem]]]:
        current = offset
        while True:
            try:
                data = fetch_person_list(
                    self.client,
                    self.source_id,
                    "pins",
                    offset=current,
                    limit=limit,
                    _bound=self._bound,
                )
            except FileNotFoundError:
                return
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
