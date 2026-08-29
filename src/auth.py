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
    """Extract Zhihu url_token from token, /token, people/token, or people URL.

    Docs/tests use placeholders only (never real handles).
    """
    s = (raw or "").strip()
    if not s:
        raise ValueError(
            "empty --user; pass url_token, /url_token, people/url_token, "
            "or https://www.zhihu.com/people/<url_token>"
        )
    s = s.split("?", 1)[0].split("#", 1)[0].rstrip("/")
    for prefix in (
        "https://www.zhihu.com",
        "http://www.zhihu.com",
        "https://zhihu.com",
        "http://zhihu.com",
    ):
        if s.lower().startswith(prefix):
            s = s[len(prefix) :]
            break
    s = s.lstrip("/")
    if s.lower().startswith("people/"):
        s = s[7:]
    token = s.split("/", 1)[0].strip()
    if not token or token in (".", "..") or "/" in token:
        raise ValueError(f"invalid --user {raw!r}; expected url_token or people URL")
    return token


def resolve_member_profile(client: Any, url_token: str) -> dict[str, str]:
    """GET /members/{token}; raise ValueError if missing. Returns url_token + name."""
    token = parse_people_ref(url_token)
    url = f"https://www.zhihu.com/api/v4/members/{token}"
    try:
        data = client.get_json(url)
    except Exception as e:
        raise ValueError(
            f"member not found or unreachable for --user {token!r}: {e}"
        ) from e
    if not isinstance(data, dict):
        raise ValueError(f"member not found for --user {token!r}: empty response")
    # Error payloads sometimes still JSON
    if data.get("error") and not (data.get("url_token") or data.get("id")):
        raise ValueError(f"member not found for --user {token!r}: {data.get('error')}")
    resolved = str(data.get("url_token") or token).strip() or token
    name = str(data.get("name") or data.get("fullname_name") or "").strip()
    return {"url_token": resolved, "name": name}
