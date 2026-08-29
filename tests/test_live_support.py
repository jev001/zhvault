"""Unit tests for live_support (always run; no network)."""

from __future__ import annotations

import pytest
import requests

from live_support import call_or_skip_transient, is_transient_error, live_enabled


def test_live_enabled_truthy(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("ZHVAULT_LIVE", raising=False)
    assert live_enabled() is False
    monkeypatch.setenv("ZHVAULT_LIVE", "1")
    assert live_enabled() is True
    monkeypatch.setenv("ZHVAULT_LIVE", "YES")
    assert live_enabled() is True
    monkeypatch.setenv("ZHVAULT_LIVE", "0")
    assert live_enabled() is False


def test_is_transient_classifies():
    assert is_transient_error(PermissionError("auth failed HTTP 403"))
    assert is_transient_error(RuntimeError("GET failed: HTTP 429"))
    assert is_transient_error(requests.Timeout("timed out"))
    assert is_transient_error(TimeoutError("timeout"))
    assert not is_transient_error(FileNotFoundError("HTTP 404 for GET ..."))
    assert not is_transient_error(ValueError("member not found"))
    assert not is_transient_error(AssertionError("missing data"))


def test_call_or_skip_transient_skips(monkeypatch: pytest.MonkeyPatch):
    with pytest.raises(pytest.skip.Exception, match="transient"):
        call_or_skip_transient(_raise_perm)


def _raise_perm() -> None:
    raise PermissionError("auth failed HTTP 403 for GET x")


def test_call_or_skip_transient_reraises_contract():
    with pytest.raises(FileNotFoundError, match="404"):
        call_or_skip_transient(_raise_404)


def _raise_404() -> None:
    raise FileNotFoundError("HTTP 404 for GET x")
