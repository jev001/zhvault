from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from zhihu_backup.models import NormalizedItem, business_extra, content_filename


class ContentWriter:
    def __init__(self, contents_root: Path):
        self.contents_root = Path(contents_root)

    def path_for(self, item: NormalizedItem) -> Path:
        return (
            self.contents_root
            / item.owner_kind
            / item.owner_id
            / content_filename(item.item_type, item.zhihu_id, item.parent_id)
        )

    def write(self, item: NormalizedItem, body: str) -> Path:
        path = self.path_for(item)
        path.parent.mkdir(parents=True, exist_ok=True)
        fm = self._frontmatter(item)
        text = f"---\n{fm}---\n\n{body.lstrip()}"
        path.write_text(text, encoding="utf-8")
        return path

    def _frontmatter(self, item: NormalizedItem) -> str:
        data: dict[str, Any] = {
            "id": item.zhihu_id,
            "type": item.item_type,
            "url": item.url,
            "title": item.title,
            "author": item.author,
            "created": item.created.strftime("%Y-%m-%d %H:%M") if item.created else None,
            "modified": item.modified.strftime("%Y-%m-%d %H:%M") if item.modified else None,
            "upvote_num": item.upvote_num,
            "comment_num": item.comment_num,
            "sources": item.sources or [f"{item.owner_kind}:{item.owner_id}"],
        }
        data.update(business_extra(item))
        if item.author_badge:
            data["author_badge"] = item.author_badge
        if item.location:
            data["location"] = item.location
        if item.asset_refs:
            data["assets"] = [
                {
                    "file": a.get("file", ""),
                    "path": a.get("path", ""),
                    "source": a.get("source", ""),
                    "origin": a.get("origin", ""),
                }
                for a in item.asset_refs
            ]
        data = {k: v for k, v in data.items() if v is not None}
        return yaml.dump(data, allow_unicode=True, sort_keys=False, default_flow_style=False)
