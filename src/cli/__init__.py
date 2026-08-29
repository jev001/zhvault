from __future__ import annotations

from pathlib import Path
from typing import Optional

from .common import require_max_depth_mvp, resolve_embed_provider, setup_logging
from .parser import build_parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    setup_logging(
        json_mode=bool(getattr(args, "json", False)),
        data_dir=Path(getattr(args, "data_dir", "data")),
        verbose=bool(getattr(args, "verbose", False)),
        log_file=Path(args.log_file) if getattr(args, "log_file", None) else None,
    )
    return int(args.func(args))


__all__ = ["main", "build_parser", "require_max_depth_mvp", "resolve_embed_provider"]
