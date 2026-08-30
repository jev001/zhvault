from __future__ import annotations

import logging
import time
from typing import Any

import requests

log = logging.getLogger("zhvault.http")

DEFAULT_HEADERS = {
    "accept": "*/*",
    "accept-language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
    "user-agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/152.0.0.0 Safari/537.36"
    ),
    "x-requested-with": "fetch",
    "x-zse-93": "101_3_3.0",
}

# Browser document navigation to zhuanlan (no x-zse-96 / x-requested-with).
# Setting a header to None makes requests omit the session default.
ZHUANLAN_DOCUMENT_HEADERS: dict[str, str | None] = {
    "accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,image/apng,*/*;q=0.8"
    ),
    "cache-control": "no-cache",
    "pragma": "no-cache",
    "upgrade-insecure-requests": "1",
    "sec-fetch-dest": "document",
    "sec-fetch-mode": "navigate",
    "sec-fetch-site": "none",
    "sec-fetch-user": "?1",
    "referer": "https://zhuanlan.zhihu.com/",
    "x-requested-with": None,
    "x-zse-93": None,
}


class ZhihuClient:
    def __init__(
        self,
        cookies: dict[str, str],
        headers: dict[str, str] | None = None,
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

    def get_json(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        retries: int = 3,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        return self.request_json(
            "GET", url, params=params, retries=retries, headers=headers
        )

    def get_text(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, Any] | None = None,
        retries: int = 3,
    ) -> str:
        """GET raw text (HTML pages)."""
        method_u = "GET"
        last_err: Exception | None = None
        for attempt in range(retries):
            self._throttle()
            try:
                resp = self.session.request(
                    method_u,
                    url,
                    params=params,
                    headers=headers,
                    timeout=self.timeout,
                )
                self._last_request_at = time.monotonic()
                if resp.status_code in (401, 403):
                    preview = (resp.text or "").strip().replace("\n", " ")[:240]
                    log.info("auth failed HTTP %s for GET %s", resp.status_code, url)
                    if preview:
                        log.debug("auth response body: %s", preview)
                    raise PermissionError(f"auth failed HTTP {resp.status_code} for GET {url}")
                if resp.status_code == 404:
                    raise FileNotFoundError(f"HTTP 404 for GET {url}")
                if resp.status_code == 429:
                    delay = 2 ** attempt
                    time.sleep(delay)
                    continue
                resp.raise_for_status()
                return resp.text or ""
            except PermissionError:
                raise
            except FileNotFoundError:
                raise
            except Exception as e:
                last_err = e
                if attempt + 1 < retries:
                    time.sleep(2**attempt)
        raise RuntimeError(f"GET failed {url}: {last_err}")

    def request_json(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        data: Any | None = None,
        retries: int = 3,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """HTTP JSON helper. Write methods (POST/PUT/DELETE/PATCH) are for account apply only."""
        method_u = method.upper()
        last_err: Exception | None = None
        for attempt in range(retries):
            self._throttle()
            log.debug("%s %s attempt=%s/%s", method_u, url, attempt + 1, retries)
            try:
                resp = self.session.request(
                    method_u,
                    url,
                    params=params,
                    json=json_body,
                    data=data,
                    headers=headers,
                    timeout=self.timeout,
                )
                self._last_request_at = time.monotonic()
                if resp.status_code in (401, 403):
                    preview = (resp.text or "").strip().replace("\n", " ")[:240]
                    # GET article/list 403 is often WAF; soft-skip callers use INFO not ERROR spam.
                    level = logging.ERROR if method_u != "GET" else logging.INFO
                    log.log(
                        level,
                        "auth failed HTTP %s for %s %s",
                        resp.status_code,
                        method_u,
                        url,
                    )
                    if preview:
                        log.debug("auth response body: %s", preview)
                    raise PermissionError(f"auth failed HTTP {resp.status_code} for {method_u} {url}")
                if resp.status_code == 404:
                    log.info("HTTP 404 %s %s (not found / private list)", method_u, url)
                    raise FileNotFoundError(f"HTTP 404 for {method_u} {url}")
                if resp.status_code == 429:
                    delay = 2 ** attempt
                    log.info(
                        "HTTP 429 %s %s; backoff %ss (attempt %s/%s)",
                        method_u,
                        url,
                        delay,
                        attempt + 1,
                        retries,
                    )
                    time.sleep(delay)
                    continue
                resp.raise_for_status()
                if not resp.content:
                    return {}
                try:
                    out = resp.json()
                except ValueError:
                    log.info(
                        "non-JSON response HTTP %s for %s %s",
                        resp.status_code,
                        method_u,
                        url,
                    )
                    return {"_raw": resp.text, "_status": resp.status_code}
                return out if isinstance(out, dict) else {"data": out}
            except PermissionError:
                raise
            except Exception as e:
                last_err = e
                delay = 2 ** attempt
                if attempt + 1 < retries:
                    log.info(
                        "%s %s failed (%s); retry in %ss (attempt %s/%s)",
                        method_u,
                        url,
                        e,
                        delay,
                        attempt + 1,
                        retries,
                    )
                time.sleep(delay)
        log.error("%s failed %s after %s attempts: %s", method_u, url, retries, last_err)
        raise RuntimeError(f"{method_u} failed {url}: {last_err}")
