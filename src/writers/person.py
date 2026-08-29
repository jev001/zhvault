from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from graph import (
    _refresh_people_wikilinks,
    _section,
    _split_frontmatter,
    _strip_link_sections,
)
from models import NormalizedItem, business_extra


class PersonWriter:
    def __init__(self, contents_root: Path):
        self.root = Path(contents_root) / "people"

    def path_for(self, token: str) -> Path:
        return self.root / f"{token}.md"

    def write(self, item: NormalizedItem, body: str) -> Path:
        path = self.path_for(item.zhihu_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        data: dict[str, Any] = {
            "id": item.zhihu_id,
            "type": "user",
            "url": item.url,
            "title": item.title,
            "url_token": item.zhihu_id,
            "sources": item.sources,
        }
        data.update(business_extra(item))
        if item.author_badge:
            data["headline"] = item.author_badge
        data = {k: v for k, v in data.items() if v is not None}
        fm = yaml.dump(data, allow_unicode=True, sort_keys=False, default_flow_style=False)
        path.write_text(f"---\n{fm}---\n\n{body.lstrip()}", encoding="utf-8")
        return path


__all__ = [
    "PersonWriter",
    "_refresh_people_wikilinks",
    "_section",
    "_split_frontmatter",
    "_strip_link_sections",
]
