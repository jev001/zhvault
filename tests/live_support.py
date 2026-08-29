"""Helpers for optional live Zhihu network tests (not used by make gate)."""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeVar

import pytest
import requests

from auth import load_cookie_file, parse_people_ref

T = TypeVar("T")

_LIVE_TRUTHY = frozenset({"1", "true", "yes"})


def live_enabled() -> bool:
    return os.environ.get("ZHVAULT_LIVE", "").strip().lower() in _LIVE_TRUTHY


def live_user_token() -> str:
    raw = os.environ.get("ZHVAULT_LIVE_USER", "").strip()
    if not raw:
        pytest.skip("set ZHVAULT_LIVE_USER to a url_token or people URL")
    return parse_people_ref(raw)


def resolve_cookie_path() -> Path:
    env = os.environ.get("ZHVAULT_COOKIE_FILE", "").strip()
    if env:
        path = Path(env)
        if not path.is_file():
            pytest.skip(f"ZHVAULT_COOKIE_FILE not found: {path}")
        return path
    legacy = Path("Cookies.json")
    if legacy.is_file():
        return legacy
    pytest.skip(
        "no cookie; set ZHVAULT_COOKIE_FILE or place Cookies.json in cwd "
        "(zhvault auth set-cookie Cookies.json)"
    )


def load_live_cookies() -> dict[str, str]:
    return load_cookie_file(resolve_cookie_path())


def require_live() -> tuple[str, dict[str, str]]:
    """Skip unless ZHVAULT_LIVE + cookie + ZHVAULT_LIVE_USER. Returns (token, cookies)."""
    if not live_enabled():
        pytest.skip("set ZHVAULT_LIVE=1 to run live network tests")
    cookies = load_live_cookies()
    if not cookies:
        pytest.skip("cookie file is empty")
    return live_user_token(), cookies


def is_transient_error(exc: BaseException) -> bool:
    """External flakiness: do not fail the live suite."""
    if isinstance(exc, (TimeoutError, requests.Timeout, requests.ConnectionError)):
        return True
    if isinstance(exc, PermissionError):
        return True
    msg = str(exc).lower()
    if "http 429" in msg or "http 403" in msg:
        return True
    if "timed out" in msg or "timeout" in msg:
        return True
    if "connection" in msg and ("refused" in msg or "reset" in msg or "error" in msg):
        return True
    # requests wraps some failures
    return isinstance(exc, requests.RequestException) and not isinstance(
        exc, requests.HTTPError
    )


def call_or_skip_transient(fn: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    try:
        return fn(*args, **kwargs)
    except Exception as e:
        if is_transient_error(e):
            pytest.skip(f"transient external error: {e}")
        raise
