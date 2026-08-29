"""Column contributions → column stub + per-column items → article detail."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from datetime import datetime, timezone
from typing import Any

from article_detail import fetch_article_detail
from http_client import ZhihuClient
from models import NormalizedItem, content_filename
from parse import normalize_content
from sources.base import Source
from sources.member_page import unwrap_column_row
from zhihu_lists import (
    column_key,
    fetch_column_items,
    fetch_column_items_with_key_fallback,
    fetch_person_list,
)

log = logging.getLogger("zhvault.source")


def article_id_from_column_item_row(row: Any) -> str | None:
    if not isinstance(row, dict):
        return None
    for candidate in (row.get("content"), row.get("object"), row.get("target"), row):
        if not isinstance(candidate, dict):
            continue
        typ = str(candidate.get("type") or "").lower()
        if typ and typ not in ("article", "post"):
            continue
        aid = str(candidate.get("id") or "").strip()
        if aid:
            return aid
        # nested article
        art = candidate.get("article")
        if isinstance(art, dict):
            aid = str(art.get("id") or "").strip()
            if aid:
                return aid
    # row may be article without type
    if row.get("id") and (row.get("title") is not None or row.get("content") is not None):
        return str(row.get("id")).strip() or None
    return None


def _wikilink_for_article(*, owner_id: str, column_key_s: str, article_id: str) -> str:
    stem = content_filename("article", article_id, column_key_s).removesuffix(".md")
    return f"contents/articles/{owner_id}/{stem}"


class ColumnExpandSource(Source):
    """List member columns, then expand each column's items into article details."""

    name = "column"

    def __init__(self, client: ZhihuClient, user_id: str):
        self.client = client
        self.source_id = str(user_id)
        self._bound: dict[str, Any] = {}

    def total(self) -> int | None:
        try:
            data = fetch_person_list(
                self.client,
                self.source_id,
                "columns",
                offset=0,
                limit=1,
                _bound=self._bound,
            )
        except FileNotFoundError:
            log.info("skip column/%s: list 404", self.source_id)
            return 0
        return int((data.get("paging") or {}).get("totals") or 0)

    def _iter_articles_for_column(
        self, column: dict[str, Any], *, column_key_s: str
    ) -> list[NormalizedItem]:
        articles: list[NormalizedItem] = []
        offset = 0
        limit = 20
        first = True
        winning_key = column_key_s
        while True:
            try:
                if first:
                    winning_key, data = fetch_column_items_with_key_fallback(
                        self.client, column, offset=offset, limit=limit
                    )
                    first = False
                else:
                    data = fetch_column_items(
                        self.client, winning_key, offset=offset, limit=limit
                    )
            except FileNotFoundError:
                log.info(
                    "column items missing key=%s member=%s",
                    winning_key,
                    self.source_id,
                )
                break
            rows = data.get("data") or []
            for row in rows:
                aid = article_id_from_column_item_row(row)
                if not aid:
                    continue
                try:
                    detail = fetch_article_detail(self.client, aid)
                except (FileNotFoundError, PermissionError, TimeoutError, OSError) as e:
                    log.info("skip article detail id=%s: %s", aid, e)
                    continue
                except Exception as e:
                    # RuntimeError from retries, etc.
                    msg = str(e).lower()
                    if any(x in msg for x in ("404", "403", "429", "timeout", "timed out")):
                        log.info("skip article detail id=%s: %s", aid, e)
                        continue
                    log.info("skip article detail id=%s: %s", aid, e)
                    continue
                if not detail:
                    continue
                payload = dict(detail)
                if not payload.get("type"):
                    payload["type"] = "article"
                payload["column"] = {
                    "id": winning_key,
                    "url_token": winning_key,
                }
                item = normalize_content(
                    payload,
                    owner_kind="articles",
                    owner_id=self.source_id,
                    source_tag=f"column-items:{winning_key}",
                )
                if item:
                    # Ensure parent/column_id matches items URL key
                    item.parent_id = winning_key
                    articles.append(item)
            paging = data.get("paging") or {}
            next_offset = offset + len(rows)
            if not rows or paging.get("is_end"):
                break
            offset = next_offset
        return articles

    def iter_items(self, offset: int = 0, limit: int = 20) -> Iterator[tuple[int, list[NormalizedItem]]]:
        current = offset
        while True:
            try:
                data = fetch_person_list(
                    self.client,
                    self.source_id,
                    "columns",
                    offset=current,
                    limit=limit,
                    _bound=self._bound,
                )
            except FileNotFoundError:
                log.info(
                    "skip column/%s at offset=%s: list 404",
                    self.source_id,
                    current,
                )
                return
            rows = data.get("data") or []
            batch: list[NormalizedItem] = []
            for row in rows:
                col = unwrap_column_row(row)
                if not col:
                    continue
                ckey = column_key(col)
                if not ckey:
                    continue
                articles = self._iter_articles_for_column(col, column_key_s=ckey)
                links = [
                    _wikilink_for_article(
                        owner_id=self.source_id,
                        column_key_s=str(a.parent_id or ckey),
                        article_id=a.zhihu_id,
                    )
                    for a in articles
                ]
                col_item = normalize_content(
                    col,
                    owner_kind="columns",
                    owner_id=self.source_id,
                    source_tag=f"column:{self.source_id}",
                )
                if col_item:
                    intro = (col_item.markdown_body or "").rstrip()
                    if links:
                        section_lines = ["## Articles", ""]
                        for lk in links:
                            section_lines.append(f"- [[{lk}]]")
                        section_lines.append("")
                        col_item.markdown_body = (
                            (intro + "\n\n" if intro else "") + "\n".join(section_lines)
                        )
                        # bump modified so incremental rewrites pick up link section when timestamps match
                        col_item.modified = datetime.now(timezone.utc)
                    batch.append(col_item)
                batch.extend(articles)

            next_offset = current + len(rows)
            yield next_offset, batch
            paging = data.get("paging") or {}
            if not rows or paging.get("is_end"):
                break
            current = next_offset
