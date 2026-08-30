from __future__ import annotations

import pytest

from zse96 import normalize_x_zse_96


def test_normalize_x_zse_96_none_and_empty():
    assert normalize_x_zse_96(None) is None
    assert normalize_x_zse_96("") is None
    assert normalize_x_zse_96("   ") is None


def test_normalize_x_zse_96_rejects_placeholder():
    with pytest.raises(ValueError, match="invalid --x-zse-96"):
        normalize_x_zse_96("1")
    with pytest.raises(ValueError, match="invalid --x-zse-96"):
        normalize_x_zse_96("short")


def test_normalize_x_zse_96_accepts_long_token():
    tok = "2.0_" + ("A" * 40)
    assert normalize_x_zse_96(tok) == tok
