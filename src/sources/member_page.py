"""Shared offset paging over Zhihu member list endpoints."""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterator
from typing import Any

from http_client import ZhihuClient
from models import NormalizedItem
from parse import normalize_content
from sources.base import Source

log = logging.getLogger("zhvault.source")


def unwrap_content_row(row: Any) -> dict[str, Any] | None:
    if not isinstance(row, dict):
        return None
    content = row.get("content")
    if isinstance(content, dict):
        return content
    return row


def unwrap_activity_row(row: Any) -> dict[str, Any] | None:
    """Prefer activity target / nested content so item_key matches direct list APIs."""
    if not isinstance(row, dict):
        return None
    for key in ("target", "content", "object"):
        nested = row.get(key)
        if isinstance(nested, dict) and (nested.get("id") or nested.get("type")):
            inner = nested.get("target")
            if isinstance(inner, dict) and inner.get("id"):
                return inner
            return nested
    if row.get("id") and row.get("type"):
        return row
    return None


def unwrap_column_row(row: Any) -> dict[str, Any] | None:
    if not isinstance(row, dict):
        return None
    col = row.get("column") if isinstance(row.get("column"), dict) else row
    if not isinstance(col, dict):
        return None
    out = dict(col)
    if not out.get("type"):
        out["type"] = "column"
    return out


class MemberPagedSource(Source):
    """GET /api/v4/members/{id}/{path} → normalize_content rows."""

    def __init__(
        self,
        client: ZhihuClient,
        user_id: str,
        *,
        name: str,
        path: str,
        owner_kind: str,
        source_tag_prefix: str,
        unwrap: Callable[[Any], dict[str, Any] | None] | None = None,
    ):
        self.client = client
        self.name = name
        self.source_id = str(user_id)
        self.owner_kind = owner_kind
        self.source_tag_prefix = source_tag_prefix
        self.unwrap = unwrap or unwrap_content_row
        self._api = f"https://www.zhihu.com/api/v4/members/{self.source_id}/{path.lstrip('/')}"

    def total(self) -> int | None:
        try:
            data = self.client.get_json(self._api, params={"offset": 0, "limit": 1})
        except FileNotFoundError:
            log.info("skip %s/%s: list 404 (private or missing)", self.name, self.source_id)
            return 0
        return int((data.get("paging") or {}).get("totals") or 0)

    def iter_items(self, offset: int = 0, limit: int = 20) -> Iterator[tuple[int, list[NormalizedItem]]]:
        current = offset
        while True:
            try:
                data = self.client.get_json(self._api, params={"offset": current, "limit": limit})
            except FileNotFoundError:
                log.info(
                    "skip %s/%s at offset=%s: list 404 (private or missing endpoint)",
                    self.name,
                    self.source_id,
                    current,
                )
                return
            rows = data.get("data") or []
            items: list[NormalizedItem] = []
            for row in rows:
                payload = self.unwrap(row)
                if not payload:
                    continue
                item = normalize_content(
                    payload,
                    owner_kind=self.owner_kind,
                    owner_id=self.source_id,
                    source_tag=f"{self.source_tag_prefix}:{self.source_id}",
                )
                if item:
                    items.append(item)
            next_offset = current + len(rows)
            yield next_offset, items
            paging = data.get("paging") or {}
            if not rows or paging.get("is_end"):
                break
            current = next_offset
