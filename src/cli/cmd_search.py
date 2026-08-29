from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from graph import query_graph
from search.embed import EmbedderError
from search.index import build_index, read_manifest
from search.store import VectorBackendError, open_vector_store
from storage import open_engine

from .common import (
    EmbedProviderError,
    cmd_fail,
    data_paths,
    json_print,
    kinds_from_args,
    open_embedder_from_args,
    resolve_vector_backend,
    vectors_root,
)


def cmd_search_index(args: argparse.Namespace) -> int:
    data_dir = Path(args.data_dir)
    contents, _, meta = data_paths(data_dir)
    try:
        backend = resolve_vector_backend(getattr(args, "vector_backend", None))
    except VectorBackendError as e:
        return cmd_fail(args, str(e))
    engine = open_engine(args.engine, meta)
    try:
        vectors = vectors_root(meta, args.engine)
        try:
            store = open_vector_store(backend, vectors)
        except VectorBackendError as e:
            return cmd_fail(args, str(e))
        try:
            embedder = open_embedder_from_args(args)
        except (EmbedProviderError, EmbedderError) as e:
            return cmd_fail(args, str(e))
        stats = build_index(
            engine,
            contents,
            vectors,
            store=store,
            embedder=embedder,
        )
        summary = {"event": "summary", "backend": backend, **stats}
        if args.json:
            json_print(summary)
        else:
            print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0
    finally:
        engine.close()


def cmd_search_semantic(args: argparse.Namespace) -> int:
    data_dir = Path(args.data_dir)
    _, _, meta = data_paths(data_dir)
    try:
        backend = resolve_vector_backend(getattr(args, "vector_backend", None))
    except VectorBackendError as e:
        return cmd_fail(args, str(e))
    engine = open_engine(args.engine, meta)
    try:
        vectors = vectors_root(meta, args.engine)
        manifest_path = vectors / "manifest.json"
        manifest = read_manifest(manifest_path)
        try:
            store = open_vector_store(backend, vectors)
        except VectorBackendError as e:
            return cmd_fail(args, str(e))
        if manifest is not None and manifest.get("backend") != backend:
            return cmd_fail(
                args,
                f"vector index backend mismatch: manifest has {manifest.get('backend')!r}, "
                f"requested {backend!r}; re-run `search index --vector-backend {backend}`",
            )
        if manifest is None and store.count() == 0:
            return cmd_fail(args, "no vector index found; run search index first")
        try:
            embedder = open_embedder_from_args(args)
        except (EmbedProviderError, EmbedderError) as e:
            return cmd_fail(args, str(e))
        query_vec = embedder.embed([args.query])[0]
        hits = store.query(query_vec, top_k=int(args.top_k))
        expand = getattr(args, "expand_graph", None)
        kinds = kinds_from_args(getattr(args, "kind", None)) if expand is not None else None
        graph_cache: dict[str, list[dict[str, Any]]] = {}
        out_hits: list[dict[str, Any]] = []
        for h in hits:
            meta_d = dict(h.metadata or {})
            row: dict[str, Any] = {
                "id": h.id,
                "score": h.score,
                "document": h.document,
                "item_key": meta_d.get("item_key"),
                "path": meta_d.get("path"),
                "metadata": meta_d,
            }
            if expand is not None:
                key = row.get("item_key")
                if not key:
                    row["neighbors"] = []
                elif key in graph_cache:
                    row["neighbors"] = graph_cache[key]
                else:
                    try:
                        g = query_graph(engine, start=str(key), depth=int(expand), kinds=kinds)
                        neighbors = [n for n in (g.get("nodes") or []) if n.get("id") != key]
                    except Exception:
                        neighbors = []
                    graph_cache[str(key)] = neighbors
                    row["neighbors"] = neighbors
            out_hits.append(row)
        result = {
            "event": "hits",
            "query": args.query,
            "backend": backend,
            "hits": out_hits,
        }
        if args.json:
            json_print(result)
        else:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    finally:
        engine.close()
