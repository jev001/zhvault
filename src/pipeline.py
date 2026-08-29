from __future__ import annotations

import hashlib
import logging
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from models import Checkpoint, GraphEdge, ItemRecord, NormalizedItem, RunStats, business_extra
from sources.base import Source
from storage.base import StorageEngine
from writers.asset import AssetWriter
from writers.content import ContentWriter
from writers.person import PersonWriter

log = logging.getLogger("zhvault")


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _hash_body(body: str) -> str:
    return hashlib.sha256(body.encode("utf-8")).hexdigest()[:32]


class Pipeline:
    def __init__(
        self,
        engine: StorageEngine,
        contents_root: Path,
        assets_root: Path,
        *,
        full: bool = False,
        limit: int = 20,
        on_event: Callable[[dict[str, Any]], None] | None = None,
        session=None,
        asset_workers: int = 8,
        asset_link: str = "wikilink",
    ):
        self.engine = engine
        self.contents = ContentWriter(contents_root)
        self.people = PersonWriter(contents_root)
        self.assets = AssetWriter(
            assets_root, engine, session=session, workers=asset_workers, asset_link=asset_link
        )
        self.full = full
        self.limit = limit
        self.on_event = on_event

    def _emit(self, event: dict[str, Any]) -> None:
        if self.on_event:
            self.on_event(event)

    def should_skip(self, item: NormalizedItem) -> bool:
        if self.full:
            return False
        existing = self.engine.get_item(item.key)
        if not existing:
            return False
        if item.item_type == "user":
            return True
        new_updated = item.updated_at_str()
        if existing.content_updated_at and new_updated and existing.content_updated_at == new_updated:
            return True
        return bool(existing.content_updated_at and new_updated is None)

    def _upsert_follows_edge(self, item: NormalizedItem, source: Source) -> None:
        if source.name == "following":
            from_id = f"user:{source.source_id}"
            to_id = f"user:{item.zhihu_id}"
        elif source.name == "followers":
            from_id = f"user:{item.zhihu_id}"
            to_id = f"user:{source.source_id}"
        else:
            return
        self.engine.upsert_graph_edge(
            GraphEdge(
                from_id=from_id,
                to_id=to_id,
                kind="follows",
                origin="api",
                seen_at=_now(),
            )
        )

    def process_person(self, item: NormalizedItem, *, source: Source) -> str:
        """Skip existing user shells unless --full; always refresh follows edge."""
        try:
            existing = self.engine.get_item(item.key)
            if not self.full and existing:
                existing.last_seen_at = _now()
                existing.orphaned = False
                self.engine.upsert_item(existing)
                self._upsert_follows_edge(item, source)
                return "skipped"

            path = self.people.write(item, item.markdown_body)
            record = ItemRecord(
                key=item.key,
                item_type=item.item_type,
                zhihu_id=item.zhihu_id,
                url=item.url,
                title=item.title,
                content_updated_at=item.updated_at_str(),
                content_hash=_hash_body(item.markdown_body),
                path=str(path),
                last_seen_at=_now(),
                orphaned=False,
                extra=business_extra(item),
            )
            self.engine.upsert_item(record)
            self._upsert_follows_edge(item, source)
            return "updated" if existing else "created"
        except Exception as e:
            self.engine.record_failed(item.key, source.name, source.source_id, str(e))
            log.exception("failed item %s", item.key)
            return "failed"

    def process_item(self, item: NormalizedItem, *, source: Source) -> str:
        """Returns action: created|updated|skipped|failed."""
        if item.item_type == "user":
            return self.process_person(item, source=source)
        try:
            existing = self.engine.get_item(item.key)
            if self.should_skip(item):
                if existing:
                    existing.last_seen_at = _now()
                    existing.orphaned = False
                    self.engine.upsert_item(existing)
                self.engine.link_membership(item.key, item.owner_kind, item.owner_id)
                return "skipped"

            body, asset_urls, refs = self.assets.localize_markdown(
                item.markdown_body, self.contents.path_for(item).parent
            )
            item.asset_refs = [
                {"file": r.file, "path": r.path, "source": r.source, "origin": r.origin}
                for r in refs
            ]
            path = self.contents.write(item, body)
            record = ItemRecord(
                key=item.key,
                item_type=item.item_type,
                zhihu_id=item.zhihu_id,
                url=item.url,
                title=item.title,
                content_updated_at=item.updated_at_str(),
                content_hash=_hash_body(body),
                path=str(path),
                last_seen_at=_now(),
                orphaned=False,
                extra=business_extra(item),
            )
            self.engine.upsert_item(record)
            self.engine.replace_item_assets(item.key, asset_urls)
            self.engine.link_membership(item.key, item.owner_kind, item.owner_id)
            return "updated" if existing else "created"
        except Exception as e:
            self.engine.record_failed(item.key, source.name, source.source_id, str(e))
            log.exception("failed item %s", item.key)
            return "failed"

    def run_source(self, source: Source, *, resume: bool = True) -> RunStats:
        stats = RunStats()
        start_offset = 0
        if resume:
            cp = self.engine.get_checkpoint(source.name, source.source_id)
            if cp:
                start_offset = cp.offset
                log.info("resume %s/%s from offset %s", source.name, source.source_id, start_offset)

        self._emit(
            {
                "event": "source_start",
                "source": source.name,
                "source_id": source.source_id,
                "offset": start_offset,
            }
        )

        try:
            for page_no, (next_offset, page) in enumerate(
                source.iter_items(offset=start_offset, limit=self.limit),
                start=1,
            ):
                page_created = page_updated = page_skipped = page_failed = 0
                log.info(
                    "page %s %s/%s size=%s -> offset %s",
                    page_no,
                    source.name,
                    source.source_id,
                    len(page),
                    next_offset,
                )
                for item in page:
                    stats.fetched += 1
                    action = self.process_item(item, source=source)
                    if action == "created":
                        stats.created += 1
                        page_created += 1
                    elif action == "updated":
                        stats.updated += 1
                        page_updated += 1
                    elif action == "skipped":
                        stats.skipped += 1
                        page_skipped += 1
                    else:
                        stats.failed += 1
                        page_failed += 1
                    self._emit(
                        {
                            "event": "item",
                            "key": item.key,
                            "action": action,
                            "source": source.name,
                            "source_id": source.source_id,
                        }
                    )

                self.engine.set_checkpoint(
                    Checkpoint(
                        source=source.name,
                        source_id=source.source_id,
                        offset=next_offset,
                        updated_at=_now(),
                    )
                )
                log.info(
                    "page %s done created=%s updated=%s skipped=%s failed=%s",
                    page_no,
                    page_created,
                    page_updated,
                    page_skipped,
                    page_failed,
                )
                self._emit(
                    {
                        "event": "checkpoint",
                        "source": source.name,
                        "source_id": source.source_id,
                        "offset": next_offset,
                    }
                )
                if not page:
                    break
        except PermissionError as e:
            log.error("auth error %s/%s: %s", source.name, source.source_id, e)
            self._emit({"event": "auth_error", "error": str(e), "source": source.name})
            raise

        self._emit(
            {
                "event": "source_done",
                "source": source.name,
                "source_id": source.source_id,
                "stats": stats.to_dict(),
            }
        )
        return stats

    def run(self, sources: list[Source], *, resume: bool = True) -> RunStats:
        total = RunStats()
        log.info("pipeline run sources=%s resume=%s full=%s", len(sources), resume, self.full)
        for source in sources:
            try:
                total.merge(self.run_source(source, resume=resume))
            except PermissionError as e:
                total.source_errors += 1
                log.error(
                    "source error %s/%s (skipped; continuing): %s",
                    source.name,
                    source.source_id,
                    e,
                )
                log.error(
                    "CLI 403 while browser works often needs --x-zse-96 (cookie may still be valid)"
                )
                self._emit(
                    {
                        "event": "source_error",
                        "source": source.name,
                        "source_id": source.source_id,
                        "error": str(e),
                        "code": "auth",
                    }
                )
            except FileNotFoundError as e:
                # Private / missing member lists (e.g. others' votes) — not a hard failure.
                log.info(
                    "source unavailable %s/%s (404, continuing): %s",
                    source.name,
                    source.source_id,
                    e,
                )
                self._emit(
                    {
                        "event": "source_unavailable",
                        "source": source.name,
                        "source_id": source.source_id,
                        "error": str(e),
                        "code": "not_found",
                    }
                )
            except Exception as e:
                total.source_errors += 1
                log.exception(
                    "source error %s/%s (skipped; continuing): %s",
                    source.name,
                    source.source_id,
                    e,
                )
                self._emit(
                    {
                        "event": "source_error",
                        "source": source.name,
                        "source_id": source.source_id,
                        "error": str(e),
                        "code": "error",
                    }
                )
        log.info(
            "pipeline done fetched=%s created=%s updated=%s skipped=%s failed=%s source_errors=%s",
            total.fetched,
            total.created,
            total.updated,
            total.skipped,
            total.failed,
            total.source_errors,
        )
        return total
