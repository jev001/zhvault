from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from storage.base import StorageEngine


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


def parse_people_ref(raw: str) -> str:
    """Extract Zhihu url_token from a token or people URL. Docs/tests use placeholders only."""
    s = (raw or "").strip()
    if not s:
        raise ValueError("empty --user; pass url_token or https://www.zhihu.com/people/<url_token>")
    s = s.split("?", 1)[0].split("#", 1)[0].rstrip("/")
    marker = "/people/"
    if marker in s:
        part = s.split(marker, 1)[1]
        token = part.split("/", 1)[0].strip()
    else:
        token = s.strip().strip("/")
    if not token or "/" in token or token in (".", ".."):
        raise ValueError(f"invalid --user {raw!r}; expected url_token or people URL")
    return token
