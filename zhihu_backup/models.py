from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Optional


def item_key(item_type: str, zhihu_id: str, parent_id: Optional[str] = None) -> str:
    if parent_id:
        return f"{item_type}:{parent_id}:{zhihu_id}"
    return f"{item_type}:{zhihu_id}"


def content_filename(item_type: str, zhihu_id: str, parent_id: Optional[str] = None) -> str:
    if parent_id:
        return f"{item_type}_{parent_id}_{zhihu_id}.md"
    return f"{item_type}_{zhihu_id}.md"


def business_extra(item: "NormalizedItem") -> dict[str, str]:
    """Typed Zhihu IDs for meta.extra / frontmatter (migration-friendly)."""
    t = item.item_type
    zid = item.zhihu_id
    parent = item.parent_id
    if t == "answer":
        out = {"answer_id": zid}
        if parent:
            out["question_id"] = parent
            out["parent_id"] = parent
        return out
    if t == "article":
        out = {"article_id": zid}
        if parent:
            out["column_id"] = parent
            out["parent_id"] = parent
        return out
    if t == "question":
        return {"question_id": zid}
    if t == "pin":
        return {"pin_id": zid}
    if t == "zvideo":
        return {"zvideo_id": zid}
    out = {f"{t}_id": zid}
    if parent:
        out["parent_id"] = parent
    return out


@dataclass
class Checkpoint:
    source: str
    source_id: str
    offset: int = 0
    updated_at: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Checkpoint":
        return cls(
            source=data["source"],
            source_id=data["source_id"],
            offset=int(data.get("offset", 0)),
            updated_at=data.get("updated_at"),
        )


@dataclass
class ItemRecord:
    key: str
    item_type: str
    zhihu_id: str
    url: str = ""
    title: str = ""
    content_updated_at: Optional[str] = None
    content_hash: Optional[str] = None
    path: Optional[str] = None
    last_seen_at: Optional[str] = None
    orphaned: bool = False
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ItemRecord":
        return cls(
            key=data["key"],
            item_type=data["item_type"],
            zhihu_id=str(data["zhihu_id"]),
            url=data.get("url", ""),
            title=data.get("title", ""),
            content_updated_at=data.get("content_updated_at"),
            content_hash=data.get("content_hash"),
            path=data.get("path"),
            last_seen_at=data.get("last_seen_at"),
            orphaned=bool(data.get("orphaned", False)),
            extra=data.get("extra") or {},
        )


@dataclass
class NormalizedItem:
    item_type: str
    zhihu_id: str
    url: str
    title: str
    author: str = ""
    author_badge: str = ""
    created: Optional[datetime] = None
    modified: Optional[datetime] = None
    upvote_num: int = 0
    comment_num: int = 0
    location: str = ""
    markdown_body: str = ""
    owner_kind: str = "collections"
    owner_id: str = "default"
    sources: list[str] = field(default_factory=list)
    parent_id: Optional[str] = None

    @property
    def key(self) -> str:
        return item_key(self.item_type, self.zhihu_id, self.parent_id)

    def updated_at_str(self) -> Optional[str]:
        if not self.modified:
            return None
        return self.modified.strftime("%Y-%m-%d %H:%M:%S")


@dataclass
class RunStats:
    fetched: int = 0
    created: int = 0
    updated: int = 0
    skipped: int = 0
    failed: int = 0
    source_errors: int = 0

    def to_dict(self) -> dict[str, int]:
        return asdict(self)

    def merge(self, other: "RunStats") -> None:
        self.fetched += other.fetched
        self.created += other.created
        self.updated += other.updated
        self.skipped += other.skipped
        self.failed += other.failed
        self.source_errors += other.source_errors
