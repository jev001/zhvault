from __future__ import annotations

from collections.abc import Iterator

from http_client import ZhihuClient
from models import NormalizedItem
from parse import enrich_question_detail, normalize_content, question_payload_from_row
from sources.base import Source
from zhihu_lists import fetch_person_list


class FollowedQuestionSource(Source):
    name = "followed_question"

    def __init__(self, client: ZhihuClient, user_id: str):
        self.client = client
        self.source_id = str(user_id)
        self._bound: dict = {}

    def total(self) -> int | None:
        try:
            data = fetch_person_list(
                self.client,
                self.source_id,
                "following-questions",
                offset=0,
                limit=1,
                _bound=self._bound,
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
                    "following-questions",
                    offset=current,
                    limit=limit,
                    _bound=self._bound,
                )
            except FileNotFoundError:
                return
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
