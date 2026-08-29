from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from auth import collection_ids_from_config, load_url_config, parse_people_ref, resolve_cookies
from http_client import ZhihuClient
from pipeline import Pipeline
from sources import build_sources
from storage import open_engine

from .common import data_paths, json_print, log, log_event, require_max_depth_mvp


def cmd_status(args: argparse.Namespace) -> int:
    _, _, meta = data_paths(Path(args.data_dir))
    engine = open_engine(args.engine, meta)
    try:
        summary = engine.status_summary()
        if args.json:
            json_print(summary)
        else:
            print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0
    finally:
        engine.close()


def _run_backup(args: argparse.Namespace, *, resume: bool) -> int:
    msg = require_max_depth_mvp(getattr(args, "max_depth", 1))
    if msg:
        if args.json:
            json_print({"event": "error", "error": msg})
        else:
            log.error(msg)
        return 2

    user_ref = getattr(args, "user", None)
    user_id: str | None = None
    if user_ref:
        try:
            user_id = parse_people_ref(str(user_ref))
        except ValueError as e:
            err = str(e)
            log.error("%s", err)
            if args.json:
                json_print({"event": "error", "error": err})
            else:
                print(err, file=sys.stderr)
            return 2

    source_name = (args.source or "all").lower()
    if source_name == "people" and not user_id:
        err = "--source people requires --user <url_token or people URL>"
        log.error("%s", err)
        if args.json:
            json_print({"event": "error", "error": err})
        else:
            print(err, file=sys.stderr)
        return 2

    data_dir = Path(args.data_dir)
    contents, assets, meta = data_paths(data_dir)
    engine = open_engine(args.engine, meta)

    def on_event(ev: dict[str, Any]) -> None:
        if args.json:
            json_print(ev)
        log_event(ev, verbose=bool(args.verbose))

    try:
        cookies = resolve_cookies(engine, Path(args.cookie_file) if args.cookie_file else None)
        if not cookies:
            msg = {"ok": False, "error": "no cookie; run: zhvault auth set-cookie Cookies.json"}
            log.error("%s", msg["error"])
            if args.json:
                json_print(msg)
            else:
                print(msg["error"], file=sys.stderr)
            return 2

        headers: dict[str, str] = {}
        if args.x_zse_96:
            headers["x-zse-96"] = args.x_zse_96

        client = ZhihuClient(cookies, headers=headers or None)
        config = load_url_config(Path(args.url_config))
        coll_ids = list(args.collection_id or []) or collection_ids_from_config(config)

        log.info(
            "backup resolve source=%s user=%s collections=%s",
            source_name,
            user_id or "(me)",
            len(coll_ids),
        )
        sources = build_sources(
            client,
            source=args.source,
            collection_ids=coll_ids,
            user_id=user_id,
        )
        if not sources:
            msg = {
                "ok": False,
                "error": "no sources resolved; check --source / --user / url.json collections / login",
            }
            log.error("%s", msg["error"])
            if args.json:
                json_print(msg)
            else:
                print(msg["error"], file=sys.stderr)
            return 2

        log.info(
            "backup start engine=%s source=%s user=%s full=%s resume=%s sources=%s",
            args.engine,
            args.source,
            user_id or "(me)",
            bool(args.full),
            resume,
            len(sources),
        )
        pipeline = Pipeline(
            engine,
            contents,
            assets,
            full=bool(args.full),
            limit=args.limit,
            on_event=on_event,
            session=client.session,
            asset_workers=int(args.asset_workers),
            asset_link=str(getattr(args, "asset_link", "wikilink")),
        )
        stats = pipeline.run(sources, resume=resume)
        ok = stats.failed == 0 and stats.source_errors == 0
        summary = {
            "ok": ok,
            "resume": resume,
            "full": bool(args.full),
            "engine": args.engine,
            "source": args.source,
            "user": user_id,
            "stats": stats.to_dict(),
            "data_dir": str(data_dir),
        }
        log.info(
            "backup done fetched=%s created=%s updated=%s skipped=%s failed=%s source_errors=%s",
            stats.fetched,
            stats.created,
            stats.updated,
            stats.skipped,
            stats.failed,
            stats.source_errors,
        )
        if args.json:
            json_print({"event": "summary", **summary})
        else:
            print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0 if ok else 1
    except PermissionError as e:
        payload = {"ok": False, "error": str(e), "code": "auth"}
        log.error("auth failed: %s", e)
        if args.json:
            json_print(payload)
        else:
            print(str(e), file=sys.stderr)
        return 3
    finally:
        engine.close()


def cmd_backup(args: argparse.Namespace) -> int:
    return _run_backup(args, resume=not bool(args.full))


def cmd_resume(args: argparse.Namespace) -> int:
    return _run_backup(args, resume=True)
