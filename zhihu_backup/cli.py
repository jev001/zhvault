from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any, Optional

from zhihu_backup.auth import (
    collection_ids_from_config,
    load_url_config,
    resolve_cookies,
    set_cookie_from_file,
)
from zhihu_backup.http_client import ZhihuClient
from zhihu_backup.pipeline import Pipeline
from zhihu_backup.sources import build_sources
from zhihu_backup.storage import open_engine


def _setup_logging(json_mode: bool) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(message)s",
        stream=sys.stderr if json_mode else sys.stdout,
    )


def _data_paths(data_dir: Path) -> tuple[Path, Path, Path]:
    contents = data_dir / "contents"
    assets = data_dir / "assets"
    meta = data_dir / "meta"
    contents.mkdir(parents=True, exist_ok=True)
    assets.mkdir(parents=True, exist_ok=True)
    meta.mkdir(parents=True, exist_ok=True)
    return contents, assets, meta


def _json_print(obj: Any) -> None:
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def cmd_auth(args: argparse.Namespace) -> int:
    _, _, meta = _data_paths(Path(args.data_dir))
    engine = open_engine(args.engine, meta)
    try:
        cookies = set_cookie_from_file(engine, Path(args.cookie_file))
        result = {"ok": True, "keys": sorted(cookies.keys()), "engine": args.engine}
        if args.json:
            _json_print(result)
        else:
            print(f"cookie saved ({len(cookies)} keys) via {args.engine}")
        return 0
    finally:
        engine.close()


def cmd_status(args: argparse.Namespace) -> int:
    _, _, meta = _data_paths(Path(args.data_dir))
    engine = open_engine(args.engine, meta)
    try:
        summary = engine.status_summary()
        if args.json:
            _json_print(summary)
        else:
            print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0
    finally:
        engine.close()


def _run_backup(args: argparse.Namespace, *, resume: bool) -> int:
    data_dir = Path(args.data_dir)
    contents, assets, meta = _data_paths(data_dir)
    engine = open_engine(args.engine, meta)

    def on_event(ev: dict[str, Any]) -> None:
        if args.json:
            _json_print(ev)
        elif args.verbose:
            logging.getLogger("zhihu_backup").info("%s", ev)

    try:
        cookies = resolve_cookies(engine, Path(args.cookie_file) if args.cookie_file else None)
        if not cookies:
            msg = {"ok": False, "error": "no cookie; run: zhihu-backup auth set-cookie Cookies.json"}
            if args.json:
                _json_print(msg)
            else:
                print(msg["error"], file=sys.stderr)
            return 2

        headers: dict[str, str] = {}
        if args.x_zse_96:
            headers["x-zse-96"] = args.x_zse_96

        client = ZhihuClient(cookies, headers=headers or None)
        config = load_url_config(Path(args.url_config))
        coll_ids = list(args.collection_id or []) or collection_ids_from_config(config)

        sources = build_sources(client, source=args.source, collection_ids=coll_ids)
        if not sources:
            msg = {
                "ok": False,
                "error": "no sources resolved; check --source / url.json collections / login",
            }
            if args.json:
                _json_print(msg)
            else:
                print(msg["error"], file=sys.stderr)
            return 2

        pipeline = Pipeline(
            engine,
            contents,
            assets,
            full=bool(args.full),
            limit=args.limit,
            on_event=on_event,
            session=client.session,
        )
        stats = pipeline.run(sources, resume=resume)
        summary = {
            "ok": True,
            "resume": resume,
            "full": bool(args.full),
            "engine": args.engine,
            "source": args.source,
            "stats": stats.to_dict(),
            "data_dir": str(data_dir),
        }
        if args.json:
            _json_print({"event": "summary", **summary})
        else:
            print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0 if stats.failed == 0 else 1
    except PermissionError as e:
        payload = {"ok": False, "error": str(e), "code": "auth"}
        if args.json:
            _json_print(payload)
        else:
            print(str(e), file=sys.stderr)
        return 3
    finally:
        engine.close()


def cmd_backup(args: argparse.Namespace) -> int:
    return _run_backup(args, resume=True)


def cmd_resume(args: argparse.Namespace) -> int:
    return _run_backup(args, resume=True)


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--data-dir", default="data", help="root data directory")
    common.add_argument("--engine", default="sqlite", choices=["sqlite", "json", "rocksdb", "rocks"])
    common.add_argument("--json", action="store_true", help="machine-readable stdout")
    common.add_argument("--verbose", action="store_true")

    p = argparse.ArgumentParser(prog="zhihu-backup", description="Zhihu backup CLI", parents=[common])
    sub = p.add_subparsers(dest="command", required=True)

    auth = sub.add_parser("auth", help="authentication helpers", parents=[common])
    auth_sub = auth.add_subparsers(dest="auth_command", required=True)
    set_c = auth_sub.add_parser("set-cookie", help="store cookie JSON into meta engine", parents=[common])
    set_c.add_argument("cookie_file", help="path to Cookies.json")
    set_c.set_defaults(func=cmd_auth)

    st = sub.add_parser("status", help="show engine status", parents=[common])
    st.set_defaults(func=cmd_status)

    def add_backup_flags(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("--source", default="all", help="collection|pin|asked|followed|vote|all")
        sp.add_argument("--full", action="store_true", help="force re-validate all items")
        sp.add_argument("--limit", type=int, default=20)
        sp.add_argument("--cookie-file", default=None)
        sp.add_argument("--url-config", default="url.json")
        sp.add_argument("--collection-id", action="append", default=[])
        sp.add_argument("--x-zse-96", default=None, help="optional x-zse-96 header override")

    b = sub.add_parser("backup", help="incremental backup (resumes checkpoints)", parents=[common])
    add_backup_flags(b)
    b.set_defaults(func=cmd_backup)

    r = sub.add_parser("resume", help="alias of backup (continue checkpoints)", parents=[common])
    add_backup_flags(r)
    r.set_defaults(func=cmd_resume)

    return p


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    _setup_logging(bool(getattr(args, "json", False)))
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
