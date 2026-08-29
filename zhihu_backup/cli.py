from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from zhihu_backup.auth import (
    collection_ids_from_config,
    load_url_config,
    resolve_cookies,
    set_cookie_from_file,
)
from zhihu_backup.graph import rebuild_graph
from zhihu_backup.http_client import ZhihuClient
from zhihu_backup.models import GraphEdge
from zhihu_backup.pipeline import Pipeline
from zhihu_backup.sources import build_sources
from zhihu_backup.storage import open_engine

ME_URL = "https://www.zhihu.com/api/v4/me"

log = logging.getLogger("zhihu_backup")


def _setup_logging(
    *,
    json_mode: bool,
    data_dir: Path,
    verbose: bool = False,
    log_file: Optional[Path] = None,
) -> Path:
    logs_dir = Path(data_dir) / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    if log_file is None:
        log_file = logs_dir / f"backup_{datetime.now().strftime('%Y%m%d')}.log"

    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(logging.DEBUG if verbose else logging.INFO)

    fmt_console = logging.Formatter("%(levelname)s %(message)s")
    fmt_file = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")

    console = logging.StreamHandler(sys.stderr if json_mode else sys.stdout)
    console.setLevel(logging.DEBUG if verbose else logging.INFO)
    console.setFormatter(fmt_console)
    root.addHandler(console)

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(fmt_file)
    root.addHandler(file_handler)

    log.info("log file: %s", log_file)
    return log_file


def _data_paths(data_dir: Path) -> tuple[Path, Path, Path]:
    contents = data_dir / "contents"
    assets = data_dir / "assets"
    meta = data_dir / "meta"
    contents.mkdir(parents=True, exist_ok=True)
    assets.mkdir(parents=True, exist_ok=True)
    meta.mkdir(parents=True, exist_ok=True)
    (data_dir / "logs").mkdir(parents=True, exist_ok=True)
    return contents, assets, meta


def _json_print(obj: Any) -> None:
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _log_event(ev: dict[str, Any], *, verbose: bool) -> None:
    event = ev.get("event")
    if event == "source_start":
        log.info(
            "source start %s/%s offset=%s",
            ev.get("source"),
            ev.get("source_id"),
            ev.get("offset"),
        )
    elif event == "checkpoint":
        log.info(
            "checkpoint %s/%s offset=%s",
            ev.get("source"),
            ev.get("source_id"),
            ev.get("offset"),
        )
    elif event == "source_done":
        stats = ev.get("stats") or {}
        log.info(
            "source done %s/%s fetched=%s created=%s updated=%s skipped=%s failed=%s",
            ev.get("source"),
            ev.get("source_id"),
            stats.get("fetched", 0),
            stats.get("created", 0),
            stats.get("updated", 0),
            stats.get("skipped", 0),
            stats.get("failed", 0),
        )
    elif event == "item":
        action = ev.get("action")
        key = ev.get("key")
        if action == "failed":
            log.error("item %s %s", action, key)
        elif action in ("created", "updated"):
            log.info("item %s %s", action, key)
        elif verbose:
            log.debug("item %s %s", action, key)
    elif event == "auth_error":
        log.error("auth error on %s: %s", ev.get("source"), ev.get("error"))
    elif event == "source_error":
        log.error(
            "source error %s/%s code=%s: %s",
            ev.get("source"),
            ev.get("source_id"),
            ev.get("code"),
            ev.get("error"),
        )
    elif verbose:
        log.debug("event %s", ev)


def require_max_depth_mvp(n: int) -> Optional[str]:
    if int(n) != 1:
        return f"--max-depth={n} not implemented yet (only 1 supported)"
    return None


def _engine_meta_dir(meta: Path, engine_name: str) -> Path:
    return Path(meta) / (engine_name or "sqlite").lower()


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _resolve_ego(engine) -> Optional[str]:
    cookies = engine.get_cookie()
    if not cookies:
        return None
    try:
        me = ZhihuClient(cookies).get_json(ME_URL)
        token = str((me or {}).get("url_token") or (me or {}).get("id") or "")
        return token or None
    except Exception:
        return None


def cmd_auth(args: argparse.Namespace) -> int:
    _, _, meta = _data_paths(Path(args.data_dir))
    engine = open_engine(args.engine, meta)
    try:
        cookies = set_cookie_from_file(engine, Path(args.cookie_file))
        result = {"ok": True, "keys": sorted(cookies.keys()), "engine": args.engine}
        log.info("cookie saved (%s keys) via %s", len(cookies), args.engine)
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
    msg = require_max_depth_mvp(getattr(args, "max_depth", 1))
    if msg:
        if args.json:
            _json_print({"event": "error", "error": msg})
        else:
            log.error(msg)
        return 2

    data_dir = Path(args.data_dir)
    contents, assets, meta = _data_paths(data_dir)
    engine = open_engine(args.engine, meta)

    def on_event(ev: dict[str, Any]) -> None:
        if args.json:
            _json_print(ev)
        _log_event(ev, verbose=bool(args.verbose))

    try:
        cookies = resolve_cookies(engine, Path(args.cookie_file) if args.cookie_file else None)
        if not cookies:
            msg = {"ok": False, "error": "no cookie; run: zhihu-backup auth set-cookie Cookies.json"}
            log.error("%s", msg["error"])
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
            log.error("%s", msg["error"])
            if args.json:
                _json_print(msg)
            else:
                print(msg["error"], file=sys.stderr)
            return 2

        log.info(
            "backup start engine=%s source=%s full=%s resume=%s sources=%s",
            args.engine,
            args.source,
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
        )
        stats = pipeline.run(sources, resume=resume)
        ok = stats.failed == 0 and stats.source_errors == 0
        summary = {
            "ok": ok,
            "resume": resume,
            "full": bool(args.full),
            "engine": args.engine,
            "source": args.source,
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
            _json_print({"event": "summary", **summary})
        else:
            print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0 if ok else 1
    except PermissionError as e:
        # Rare path (e.g. unexpected raise outside run()); per-source 403 is handled in Pipeline.run
        payload = {"ok": False, "error": str(e), "code": "auth"}
        log.error("auth failed: %s", e)
        if args.json:
            _json_print(payload)
        else:
            print(str(e), file=sys.stderr)
        return 3
    finally:
        engine.close()


def cmd_backup(args: argparse.Namespace) -> int:
    # --full revalidates from the start; checkpoint resume would skip already-scanned offsets
    return _run_backup(args, resume=not bool(args.full))


def cmd_resume(args: argparse.Namespace) -> int:
    return _run_backup(args, resume=True)


def cmd_graph_rebuild(args: argparse.Namespace) -> int:
    data_dir = Path(args.data_dir)
    contents, _, meta = _data_paths(data_dir)
    engine = open_engine(args.engine, meta)
    try:
        ego = _resolve_ego(engine)
        meta_dir = _engine_meta_dir(meta, args.engine)
        out = rebuild_graph(
            engine,
            contents,
            meta_dir,
            ego=ego,
            max_depth_requested=int(getattr(args, "max_depth", 1)),
        )
        summary = {
            "event": "summary",
            "nodes": len(out.get("nodes") or []),
            "edges": len(out.get("edges") or []),
        }
        if args.json:
            _json_print(summary)
        else:
            print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0
    finally:
        engine.close()


def cmd_graph_edge_add(args: argparse.Namespace) -> int:
    _, _, meta = _data_paths(Path(args.data_dir))
    engine = open_engine(args.engine, meta)
    try:
        engine.upsert_graph_edge(
            GraphEdge(
                from_id=args.from_id,
                to_id=args.to_id,
                kind=args.kind,
                origin="manual",
                seen_at=_now(),
            )
        )
        result = {
            "ok": True,
            "from": args.from_id,
            "to": args.to_id,
            "kind": args.kind,
            "origin": "manual",
        }
        if args.json:
            _json_print(result)
        else:
            print(f"edge added {args.from_id} -> {args.to_id} ({args.kind})")
        return 0
    finally:
        engine.close()


def cmd_graph_edge_remove(args: argparse.Namespace) -> int:
    _, _, meta = _data_paths(Path(args.data_dir))
    engine = open_engine(args.engine, meta)
    try:
        engine.remove_graph_edge(args.from_id, args.to_id, args.kind)
        result = {
            "ok": True,
            "from": args.from_id,
            "to": args.to_id,
            "kind": args.kind,
            "removed": True,
        }
        if args.json:
            _json_print(result)
        else:
            print(f"edge removed {args.from_id} -> {args.to_id} ({args.kind})")
        return 0
    finally:
        engine.close()


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--data-dir", default="data", help="root data directory")
    common.add_argument("--engine", default="sqlite", choices=["sqlite", "json", "rocksdb", "rocks"])
    common.add_argument("--json", action="store_true", help="machine-readable stdout")
    common.add_argument("--verbose", action="store_true", help="debug console + per-item skip logs")
    common.add_argument("--log-file", default=None, help="override log path (default data/logs/backup_YYYYMMDD.log)")

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
        sp.add_argument("--full", action="store_true", help="re-validate from offset 0 (ignores checkpoint)")
        sp.add_argument("--limit", type=int, default=20)
        sp.add_argument("--cookie-file", default=None)
        sp.add_argument("--url-config", default="url.json")
        sp.add_argument("--collection-id", action="append", default=[])
        sp.add_argument("--x-zse-96", default=None, help="optional x-zse-96 header override")
        sp.add_argument(
            "--asset-workers",
            type=int,
            default=8,
            help="parallel image download workers (default 8; use 1 for serial)",
        )
        sp.add_argument(
            "--max-depth",
            type=int,
            default=1,
            dest="max_depth",
            help="social crawl depth (MVP: only 1 supported)",
        )

    b = sub.add_parser("backup", help="incremental backup (resumes checkpoints)", parents=[common])
    add_backup_flags(b)
    b.set_defaults(func=cmd_backup)

    r = sub.add_parser("resume", help="alias of backup (continue checkpoints)", parents=[common])
    add_backup_flags(r)
    r.set_defaults(func=cmd_resume)

    g = sub.add_parser("graph", help="relationship graph helpers", parents=[common])
    g_sub = g.add_subparsers(dest="graph_command", required=True)
    rb = g_sub.add_parser("rebuild", help="offline rebuild graph.json from meta", parents=[common])
    rb.set_defaults(func=cmd_graph_rebuild)

    edge = g_sub.add_parser("edge", help="manual edge mutations", parents=[common])
    edge_sub = edge.add_subparsers(dest="edge_command", required=True)

    def add_edge_keys(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("--from", dest="from_id", required=True, help="from node key")
        sp.add_argument("--to", dest="to_id", required=True, help="to node key")
        sp.add_argument("--kind", default="follows", help="edge kind (default follows)")

    ea = edge_sub.add_parser("add", help="upsert a manual graph edge", parents=[common])
    add_edge_keys(ea)
    ea.set_defaults(func=cmd_graph_edge_add)

    er = edge_sub.add_parser("remove", help="delete a graph edge", parents=[common])
    add_edge_keys(er)
    er.set_defaults(func=cmd_graph_edge_remove)

    return p


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    _setup_logging(
        json_mode=bool(getattr(args, "json", False)),
        data_dir=Path(getattr(args, "data_dir", "data")),
        verbose=bool(getattr(args, "verbose", False)),
        log_file=Path(args.log_file) if getattr(args, "log_file", None) else None,
    )
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
