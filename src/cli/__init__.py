from __future__ import annotations

from typing import Optional

from .app import app
from .common import require_max_depth_mvp, resolve_embed_provider


def main(argv: Optional[list[str]] = None) -> int:
    return int(app(args=argv, prog_name="zhvault", standalone_mode=False))


__all__ = ["app", "main", "require_max_depth_mvp", "resolve_embed_provider"]
