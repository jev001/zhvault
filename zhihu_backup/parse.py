from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

import html2text

from zhihu_backup.models import NormalizedItem


def _dt(unix_ts: Any) -> Optional[datetime]:
    if not unix_ts:
        return None
    try:
        return datetime.fromtimestamp(int(unix_ts))
    except (TypeError, ValueError, OSError):
        return None


def _html_to_md(html: str) -> str:
    converter = html2text.HTML2Text()
    converter.body_width = 0
    converter.ignore_links = False
    converter.ignore_images = False
    try:
        return converter.handle(str(html or ""))
    except Exception:
        return "错误: HTML转Markdown失败。"


def normalize_content(
    content_data: dict[str, Any],
    *,
    owner_kind: str,
    owner_id: str,
    source_tag: str,
) -> Optional[NormalizedItem]:
    if not content_data:
        return None

    item_type = content_data.get("type") or "unknown"
    zhihu_id = str(content_data.get("id") or "")
    if not zhihu_id:
        return None

    author = (content_data.get("author") or {}).get("name", "未知作者")
    author_badge = (content_data.get("author") or {}).get("headline", "")
    created = _dt(content_data.get("created_time", content_data.get("created")))
    modified = _dt(content_data.get("updated_time", content_data.get("updated"))) or created
    upvote = int(content_data.get("voteup_count") or 0)
    comment = int(content_data.get("comment_count") or 0)
    location = (content_data.get("author") or {}).get("ip_info", "") or ""
    url = content_data.get("url") or "#"
    title = "untitled"
    html = ""
    parent_id: Optional[str] = None

    if item_type == "answer":
        q = content_data.get("question") or {}
        parent_id = str(q.get("id") or "") or None
        title = q.get("title") or f"answer_{zhihu_id}"
        html = content_data.get("content") or ""
        if not url or url == "#":
            url = f"https://www.zhihu.com/answer/{zhihu_id}"
    elif item_type == "article":
        col = content_data.get("column") or {}
        parent_id = str(col.get("id") or "") or None
        title = content_data.get("title") or f"article_{zhihu_id}"
        html = content_data.get("content") or ""
        if not url or url == "#":
            url = f"https://www.zhihu.com/p/{zhihu_id}"
    elif item_type == "pin":
        base = content_data.get("excerpt_title") or ""
        blocks = content_data.get("content") or []
        if not base and blocks:
            first = blocks[0] if isinstance(blocks, list) else {}
            if isinstance(first, dict) and first.get("type") == "text":
                base = (first.get("content") or "")[:30]
        title = base or f"pin_{zhihu_id}"
        parts = []
        for block in blocks if isinstance(blocks, list) else []:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "text":
                parts.append(f"<p>{block.get('content', '')}</p>")
            elif block.get("type") == "image":
                parts.append(f'<img src="{block.get("url", "#")}" alt="pin">')
        html = "".join(parts)
        if not url or url == "#":
            url = f"https://www.zhihu.com/pin/{zhihu_id}"
    elif item_type == "zvideo":
        title = content_data.get("title") or f"zvideo_{zhihu_id}"
        if not url or url == "#":
            url = f"https://www.zhihu.com/zvideo/{zhihu_id}"
        thumb = (content_data.get("video") or {}).get("thumbnail", "")
        html = (
            f"<p><strong>视频: {title}</strong></p>"
            f"<p><a href='{url}'>在知乎观看</a></p>"
            f"<p>作者: {author}</p>"
            f"<p><img src='{thumb}' alt='cover'></p>"
        )
    elif item_type == "question":
        title = content_data.get("title") or f"question_{zhihu_id}"
        html = content_data.get("detail") or content_data.get("excerpt") or ""
        if not url or url == "#":
            url = f"https://www.zhihu.com/question/{zhihu_id}"
    else:
        title = content_data.get("title") or f"{item_type}_{zhihu_id}"
        raw = content_data.get("content", "")
        if isinstance(raw, list) and raw:
            html = raw[0].get("content", "") if isinstance(raw[0], dict) else str(raw[0])
        elif isinstance(raw, str):
            html = raw

    return NormalizedItem(
        item_type=item_type,
        zhihu_id=zhihu_id,
        url=url,
        title=title,
        author=author,
        author_badge=author_badge,
        created=created,
        modified=modified,
        upvote_num=upvote,
        comment_num=comment,
        location=location,
        markdown_body=_html_to_md(html),
        owner_kind=owner_kind,
        owner_id=owner_id,
        sources=[source_tag],
        parent_id=parent_id,
    )


def normalize_collection_item(
    item_json: dict[str, Any],
    *,
    collection_id: str,
) -> Optional[NormalizedItem]:
    content = item_json.get("content") or item_json
    return normalize_content(
        content,
        owner_kind="collections",
        owner_id=collection_id,
        source_tag=f"collection:{collection_id}",
    )
