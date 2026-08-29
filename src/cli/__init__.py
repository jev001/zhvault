from __future__ import annotations

from .app import app
from .common import require_max_depth_mvp, resolve_embed_provider


def main(argv: list[str] | None = None) -> int:
    return int(app(args=argv, prog_name="zhvault", standalone_mode=False))


__all__ = ["app", "main", "require_max_depth_mvp", "resolve_embed_provider"]
