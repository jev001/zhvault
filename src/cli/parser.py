from __future__ import annotations

import argparse

from .cmd_account import cmd_account_apply, cmd_account_plan
from .cmd_auth import cmd_auth
from .cmd_backup import cmd_backup, cmd_resume, cmd_status
from .cmd_graph import (
    cmd_graph_edge_add,
    cmd_graph_edge_remove,
    cmd_graph_query,
    cmd_graph_rebuild,
    cmd_graph_sync,
)
from .cmd_search import cmd_search_index, cmd_search_semantic


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--data-dir", default="data", help="root data directory")
    common.add_argument("--engine", default="sqlite", choices=["sqlite", "json", "rocksdb", "rocks"])
    common.add_argument("--json", action="store_true", help="machine-readable stdout")
    common.add_argument("--verbose", action="store_true", help="debug console + per-item skip logs")
    common.add_argument("--log-file", default=None, help="override log path (default data/logs/backup_YYYYMMDD.log)")

    p = argparse.ArgumentParser(prog="zhvault", description="Zhihu backup CLI (zhvault)", parents=[common])
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
            "--asset-link",
            choices=["wikilink", "rel", "assets-root"],
            default="wikilink",
            help="image link style in markdown (default wikilink for Obsidian)",
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

    gs = g_sub.add_parser("sync", help="build derived graph query index", parents=[common])
    gs.add_argument(
        "--backend",
        choices=["kuzu"],
        default="kuzu",
        help="derived index backend (default kuzu)",
    )
    gs.set_defaults(func=cmd_graph_sync)

    gq = g_sub.add_parser("query", help="subgraph from a node key", parents=[common])
    gq.add_argument(
        "--from",
        dest="from_id",
        required=True,
        help=(
            "start node key (e.g. user:{token}, answer:{qid}:{aid}); "
            "legacy data may have both user:numeric and user:token nodes"
        ),
    )
    gq.add_argument("--depth", type=int, default=1, help="max hop depth (default 1)")
    gq.add_argument(
        "--kind",
        action="append",
        default=None,
        help="edge kind filter (repeatable); use 'all' for no filter",
    )
    gq.add_argument(
        "--backend",
        choices=["auto", "memory", "kuzu"],
        default="auto",
        help="query backend: auto (kuzu if synced), memory (BFS), or kuzu (require sync)",
    )
    gq.set_defaults(func=cmd_graph_query)

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

    search = sub.add_parser("search", help="semantic search over backed-up markdown", parents=[common])
    search_sub = search.add_subparsers(dest="search_command", required=True)

    def add_vector_backend(sp: argparse.ArgumentParser) -> None:
        sp.add_argument(
            "--vector-backend",
            choices=["chroma", "memory"],
            default=None,
            help="vector store backend (default: chroma if installed, else error)",
        )

    def add_embed_flags(sp: argparse.ArgumentParser) -> None:
        sp.add_argument(
            "--embed-provider",
            choices=["hash", "local", "http"],
            default=None,
            help="embedding provider (default: local if sentence-transformers installed, else error)",
        )
        sp.add_argument("--embed-model", default=None, help="model id (local/http)")
        sp.add_argument("--embed-api-base", default=None, help="API base URL (http)")
        sp.add_argument(
            "--embed-api-key",
            default=None,
            help="API key (http; default from ZHIHU_EMBED_API_KEY env)",
        )

    si = search_sub.add_parser("index", help="chunk, embed, and upsert into VectorStore", parents=[common])
    add_vector_backend(si)
    add_embed_flags(si)
    si.set_defaults(func=cmd_search_index)

    ss = search_sub.add_parser("semantic", help="embed query and retrieve nearest chunks", parents=[common])
    ss.add_argument("query", help="search query text")
    ss.add_argument("--top-k", type=int, default=10, dest="top_k", help="number of hits (default 10)")
    add_vector_backend(ss)
    add_embed_flags(ss)
    ss.add_argument(
        "--expand-graph",
        type=int,
        default=None,
        dest="expand_graph",
        metavar="N",
        help="BFS graph depth from each hit item_key (best-effort neighbors)",
    )
    ss.add_argument(
        "--kind",
        action="append",
        default=None,
        help="edge kind filter for --expand-graph (repeatable); use 'all' for no filter",
    )
    ss.set_defaults(func=cmd_search_semantic)

    acct = sub.add_parser(
        "account",
        help="DANGER-gated Zhihu follow/collect mutations (plan=safe, apply=writes)",
        parents=[common],
    )
    acct_sub = acct.add_subparsers(dest="account_command", required=True)

    ap = acct_sub.add_parser(
        "plan",
        help="build mutate plan from local inventory (no Zhihu writes)",
        parents=[common],
    )
    ap.add_argument("--mode", choices=["prune", "migrate"], required=True)
    ap.add_argument(
        "--source",
        required=True,
        help="comma list: following,collection,followed (required; no default)",
    )
    ap.add_argument("--from-data-dir", default=None, help="account A data dir (migrate)")
    ap.add_argument(
        "--map-collection",
        action="append",
        default=[],
        help="A_id=B_id collection map (repeatable; migrate)",
    )
    ap.add_argument("--limit", type=int, default=None, help="cap actions in plan")
    ap.add_argument("--cookie-file", default=None)
    ap.add_argument("--x-zse-96", default=None)
    ap.set_defaults(func=cmd_account_plan)

    aa = acct_sub.add_parser(
        "apply",
        help="DANGER: apply plan (requires --i-understand-danger and --confirm APPLY)",
        parents=[common],
    )
    aa.add_argument("--plan", required=True, help="path to plan JSON from account plan")
    aa.add_argument(
        "--i-understand-danger",
        action="store_true",
        help="acknowledge live Zhihu account mutation",
    )
    aa.add_argument(
        "--confirm",
        default=None,
        help="must be exactly APPLY to proceed",
    )
    aa.add_argument("--cookie-file", default=None)
    aa.add_argument("--x-zse-96", default=None)
    aa.set_defaults(func=cmd_account_apply)

    return p
