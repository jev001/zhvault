from __future__ import annotations

import argparse
import json
from pathlib import Path

from auth import resolve_cookies
from http_client import ZhihuClient
from mutate.apply import ApplyGateError, apply_plan
from mutate.plan import build_plan, load_plan, parse_map_collection, parse_sources
from storage import open_engine
from zse96 import normalize_x_zse_96

from .common import ME_URL, cmd_fail, data_paths, json_print, log


def cmd_account_plan(args: argparse.Namespace) -> int:
    """Safe: build plan JSON from local inventory (GET only for migrate resolve)."""
    try:
        sources = parse_sources(args.source)
        map_collection = parse_map_collection(getattr(args, "map_collection", None))
    except ValueError as e:
        return cmd_fail(args, str(e))

    mode = args.mode
    data_dir = Path(args.data_dir)
    log.info(
        "account plan start mode=%s source=%s engine=%s data_dir=%s",
        mode,
        args.source,
        args.engine,
        data_dir,
    )
    if mode == "migrate":
        if not args.from_data_dir:
            return cmd_fail(args, "migrate requires --from-data-dir")
        inv_root = Path(args.from_data_dir)
    else:
        inv_root = data_dir

    inv_meta_path = inv_root / "meta"
    inv_meta_path.mkdir(parents=True, exist_ok=True)
    inv_engine = open_engine(args.engine, inv_meta_path)

    client: ZhihuClient | None = None
    actor_token: str | None = None
    try:
        _, _, meta = data_paths(data_dir)
        act_engine = open_engine(args.engine, meta)
        try:
            cookies = resolve_cookies(
                act_engine, Path(args.cookie_file) if args.cookie_file else None
            )
            if cookies:
                headers: dict[str, str] = {}
                try:
                    zse = normalize_x_zse_96(getattr(args, "x_zse_96", None))
                except ValueError as e:
                    return cmd_fail(args, str(e))
                if zse:
                    headers["x-zse-96"] = zse
                client = ZhihuClient(cookies, headers=headers or None)
                try:
                    me = client.get_json(ME_URL)
                    actor_token = str(me.get("url_token") or me.get("id") or "") or None
                except Exception as e:
                    log.warning("account plan: /me failed (continuing offline): %s", e)
        finally:
            act_engine.close()

        inventory_meta = {
            "mode": mode,
            "data_dir": str(data_dir.resolve()),
            "from_data_dir": str(Path(args.from_data_dir).resolve()) if args.from_data_dir else None,
            "engine": args.engine,
            "map_collection": map_collection,
        }
        plan = build_plan(
            mode=mode,
            sources=sources,
            inventory_engine=inv_engine,
            map_collection=map_collection,
            limit=args.limit,
            client=client if mode == "migrate" else None,
            actor_token=actor_token,
            inventory_meta=inventory_meta,
        )
        summary = {
            "event": "plan_summary",
            "writes_executed": False,
            "mode": mode,
            "sources": sources,
            "actor_hint": actor_token,
            "fingerprint": plan["fingerprint"],
            "counts": plan["counts"],
            "action_count": len(plan["actions"]),
            "collection_resolve": plan.get("collection_resolve") or [],
        }
        if args.json:
            json_print(plan)
        else:
            print(json.dumps(summary, ensure_ascii=False, indent=2))
            print(json.dumps(plan, ensure_ascii=False, indent=2))
        log.info(
            "account plan ready mode=%s actions=%s fingerprint=%s",
            mode,
            len(plan["actions"]),
            plan["fingerprint"][:12],
        )
        return 0
    finally:
        inv_engine.close()


def cmd_account_apply(args: argparse.Namespace) -> int:
    """DANGER: execute plan against Zhihu with stacked confirmations."""
    plan_path = Path(args.plan)
    if not plan_path.exists():
        return cmd_fail(args, f"plan not found: {plan_path}")
    try:
        plan = load_plan(plan_path)
    except Exception as e:
        return cmd_fail(args, f"invalid plan: {e}")

    data_dir = Path(args.data_dir)
    log.info(
        "account apply start plan=%s actions=%s engine=%s",
        plan_path,
        len(plan.get("actions") or []),
        args.engine,
    )
    _, _, meta = data_paths(data_dir)
    engine = open_engine(args.engine, meta)
    try:
        cookies = resolve_cookies(engine, Path(args.cookie_file) if args.cookie_file else None)
        if not cookies:
            return cmd_fail(args, "no cookie; run: zhvault auth set-cookie Cookies.json")
        headers: dict[str, str] = {}
        try:
            zse = normalize_x_zse_96(getattr(args, "x_zse_96", None))
        except ValueError as e:
            return cmd_fail(args, str(e))
        if zse:
            headers["x-zse-96"] = zse
        client = ZhihuClient(cookies, headers=headers or None)
        try:
            result = apply_plan(
                plan,
                client,
                i_understand_danger=bool(args.i_understand_danger),
                confirm=args.confirm,
                open_engine_fn=open_engine,
                skip_rebuild=False,
            )
        except ApplyGateError as e:
            return cmd_fail(args, str(e), code=2)
        log.info(
            "account apply done failed_count=%s ok=%s",
            result.get("failed_count"),
            result.get("ok"),
        )
        if args.json:
            json_print(result)
        else:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1 if result.get("failed_count") else 0
    finally:
        engine.close()
