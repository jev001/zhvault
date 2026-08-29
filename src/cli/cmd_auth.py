from __future__ import annotations

import argparse
from pathlib import Path

from auth import set_cookie_from_file
from storage import open_engine

from .common import data_paths, json_print, log


def cmd_auth(args: argparse.Namespace) -> int:
    _, _, meta = data_paths(Path(args.data_dir))
    engine = open_engine(args.engine, meta)
    try:
        cookies = set_cookie_from_file(engine, Path(args.cookie_file))
        result = {"ok": True, "keys": sorted(cookies.keys()), "engine": args.engine}
        log.info("cookie saved (%s keys) via %s", len(cookies), args.engine)
        if args.json:
            json_print(result)
        else:
            print(f"cookie saved ({len(cookies)} keys) via {args.engine}")
        return 0
    finally:
        engine.close()
