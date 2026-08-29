from __future__ import annotations

import argparse
import json
from pathlib import Path

from graph import query_graph, rebuild_graph
from graph_kuzu import KuzuBackendError, query_kuzu, sync_to_kuzu
from models import GraphEdge
from storage import open_engine

from .common import (
    cmd_fail,
    data_paths,
    engine_meta_dir,
    json_print,
    kuzu_db_path,
    log,
    now,
    resolve_ego,
    resolve_graph_query_backend,
)


def cmd_graph_rebuild(args: argparse.Namespace) -> int:
    data_dir = Path(args.data_dir)
    contents, _, meta = data_paths(data_dir)
    log.info("graph rebuild start engine=%s data_dir=%s", args.engine, data_dir)
    engine = open_engine(args.engine, meta)
    try:
        ego = resolve_ego(engine)
        meta_dir = engine_meta_dir(meta, args.engine)
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
        log.info(
            "graph rebuild done nodes=%s edges=%s",
            summary["nodes"],
            summary["edges"],
        )
        if args.json:
            json_print(summary)
        else:
            print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0
    finally:
        engine.close()


def cmd_graph_edge_add(args: argparse.Namespace) -> int:
    _, _, meta = data_paths(Path(args.data_dir))
    engine = open_engine(args.engine, meta)
    try:
        engine.upsert_graph_edge(
            GraphEdge(
                from_id=args.from_id,
                to_id=args.to_id,
                kind=args.kind,
                origin="manual",
                seen_at=now(),
            )
        )
        result = {
            "ok": True,
            "from": args.from_id,
            "to": args.to_id,
            "kind": args.kind,
            "origin": "manual",
        }
        log.info(
            "graph edge add %s -> %s kind=%s",
            args.from_id,
            args.to_id,
            args.kind,
        )
        if args.json:
            json_print(result)
        else:
            print(f"edge added {args.from_id} -> {args.to_id} ({args.kind})")
        return 0
    finally:
        engine.close()


def cmd_graph_sync(args: argparse.Namespace) -> int:
    _, _, meta = data_paths(Path(args.data_dir))
    backend = getattr(args, "backend", None) or "kuzu"
    if backend != "kuzu":
        return cmd_fail(args, f"unsupported graph sync backend: {backend!r} (only kuzu supported)")
    log.info("graph sync start backend=%s engine=%s", backend, args.engine)
    engine = open_engine(args.engine, meta)
    try:
        db_path = kuzu_db_path(meta, args.engine)
        try:
            stats = sync_to_kuzu(engine, db_path)
        except KuzuBackendError as e:
            return cmd_fail(args, str(e))
        summary = {"event": "summary", "backend": "kuzu", **stats}
        log.info("graph sync done backend=kuzu stats=%s", stats)
        if args.json:
            json_print(summary)
        else:
            print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0
    finally:
        engine.close()


def cmd_graph_query(args: argparse.Namespace) -> int:
    _, _, meta = data_paths(Path(args.data_dir))
    log.info(
        "graph query start from=%s depth=%s backend=%s engine=%s",
        args.from_id,
        args.depth,
        getattr(args, "backend", None) or "auto",
        args.engine,
    )
    engine = open_engine(args.engine, meta)
    try:
        db_path = kuzu_db_path(meta, args.engine)
        try:
            backend = resolve_graph_query_backend(getattr(args, "backend", None), db_path)
        except KuzuBackendError as e:
            return cmd_fail(args, str(e))
        kinds = None if args.kind and "all" in args.kind else (set(args.kind) if args.kind else None)
        if backend == "kuzu":
            out = query_kuzu(
                db_path,
                start=args.from_id,
                depth=int(args.depth),
                kinds=kinds,
            )
        else:
            out = query_graph(
                engine,
                start=args.from_id,
                depth=int(args.depth),
                kinds=kinds,
            )
        log.info(
            "graph query done backend=%s nodes=%s edges=%s",
            backend,
            len(out.get("nodes") or []),
            len(out.get("edges") or []),
        )
        if args.json:
            json_print(out)
        else:
            print(f"{len(out['nodes'])} nodes, {len(out['edges'])} edges")
        return 0
    finally:
        engine.close()


def cmd_graph_edge_remove(args: argparse.Namespace) -> int:
    _, _, meta = data_paths(Path(args.data_dir))
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
        log.info(
            "graph edge remove %s -> %s kind=%s",
            args.from_id,
            args.to_id,
            args.kind,
        )
        if args.json:
            json_print(result)
        else:
            print(f"edge removed {args.from_id} -> {args.to_id} ({args.kind})")
        return 0
    finally:
        engine.close()
