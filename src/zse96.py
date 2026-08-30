"""Validate optional Zhihu x-zse-96 header overrides."""

from __future__ import annotations

# Browser tokens usually look like "2.0_<long base64-ish payload>".
_MIN_LEN = 16
_PLACEHOLDERS = frozenset({"1", "0", "true", "false", "yes", "no", "x", "test", "dummy"})


def normalize_x_zse_96(raw: str | None) -> str | None:
    """Return stripped token, or None if unset.

    Raises ValueError for obvious placeholders (e.g. ``--x-zse-96 1``).
    """
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    low = s.lower()
    if low in _PLACEHOLDERS or len(s) < _MIN_LEN:
        raise ValueError(
            "invalid --x-zse-96: copy the full header value from browser DevTools "
            "Network (usually starts with '2.0_' and is a long string). "
            f"Got {s!r} (len={len(s)}). Passing a placeholder like '1' worsens HTTP 403."
        )
    return s
