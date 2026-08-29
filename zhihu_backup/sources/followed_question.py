from __future__ import annotations

from typing import Iterator, Optional

from zhihu_backup.http_client import ZhihuClient
from zhihu_backup.models import NormalizedItem
from zhihu_backup.parse import enrich_question_detail, normalize_content, question_payload_from_row
from zhihu_backup.sources.base import Source


class FollowedQuestionSource(Source):
    name = "followed_question"

    def __init__(self, client: ZhihuClient, user_id: str):
        self.client = client
        self.source_id = str(user_id)
        self._api = f"https://www.zhihu.com/api/v4/members/{self.source_id}/following-questions"

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
                content = question_payload_from_row(row if isinstance(row, dict) else {})
                if not content:
                    continue
                content = enrich_question_detail(self.client, content)
                item = normalize_content(
                    content,
                    owner_kind="followed_questions",
                    owner_id=self.source_id,
                    source_tag=f"followed:{self.source_id}",
                )
                if item:
                    items.append(item)
            next_offset = current + len(rows)
            yield next_offset, items
            paging = data.get("paging") or {}
            if not rows or paging.get("is_end"):
                break
            current = next_offset
