from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from zhihu_backup.storage.base import StorageEngine


def load_cookie_file(path: Path) -> dict[str, str]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("cookie file must be a JSON object")
    return {str(k): str(v) for k, v in data.items()}


def set_cookie_from_file(engine: StorageEngine, path: Path) -> dict[str, str]:
    cookies = load_cookie_file(path)
    engine.set_cookie(cookies)
    return cookies


def resolve_cookies(engine: StorageEngine, cookie_file: Path | None = None) -> dict[str, str]:
    if cookie_file:
        cookies = load_cookie_file(cookie_file)
        engine.set_cookie(cookies)
        return cookies
    cookies = engine.get_cookie()
    if cookies:
        return cookies
    legacy = Path("Cookies.json")
    if legacy.exists():
        cookies = load_cookie_file(legacy)
        engine.set_cookie(cookies)
        return cookies
    return {}


def load_url_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"collections": []}
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {"collections": []}


def collection_ids_from_config(config: dict[str, Any]) -> list[str]:
    ids: list[str] = []
    for entry in config.get("collections") or []:
        url = (entry or {}).get("url") or ""
        if not url:
            continue
        cid = str(url).rstrip("/").split("/")[-1]
        if cid:
            ids.append(cid)
    return ids
