from __future__ import annotations

import time
from typing import Any, Optional

import requests


DEFAULT_HEADERS = {
    "accept": "*/*",
    "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
    "user-agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "x-requested-with": "fetch",
    "x-zse-93": "101_3_3.0",
}


class ZhihuClient:
    def __init__(
        self,
        cookies: dict[str, str],
        headers: Optional[dict[str, str]] = None,
        timeout: float = 15.0,
        min_interval: float = 0.8,
    ):
        self.session = requests.Session()
        self.session.cookies.update(cookies or {})
        merged = dict(DEFAULT_HEADERS)
        if headers:
            merged.update(headers)
        self.session.headers.update(merged)
        self.timeout = timeout
        self.min_interval = min_interval
        self._last_request_at = 0.0

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)

    def get_json(self, url: str, params: Optional[dict[str, Any]] = None, retries: int = 3) -> dict[str, Any]:
        last_err: Optional[Exception] = None
        for attempt in range(retries):
            self._throttle()
            try:
                resp = self.session.get(url, params=params, timeout=self.timeout)
                self._last_request_at = time.monotonic()
                if resp.status_code in (401, 403):
                    raise PermissionError(f"auth failed HTTP {resp.status_code} for {url}")
                if resp.status_code == 429:
                    time.sleep(2 ** attempt)
                    continue
                resp.raise_for_status()
                return resp.json()
            except PermissionError:
                raise
            except Exception as e:
                last_err = e
                time.sleep(2 ** attempt)
        raise RuntimeError(f"GET failed {url}: {last_err}")
