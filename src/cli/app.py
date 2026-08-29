from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Literal

import typer

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
from .common import setup_logging

EngineName = Literal["sqlite", "json", "rocksdb", "rocks"]
AssetLinkStyle = Literal["wikilink", "rel", "assets-root"]
VectorBackend = Literal["chroma", "memory"]
EmbedProvider = Literal["hash", "local", "http"]
GraphSyncBackend = Literal["kuzu"]
GraphQueryBackend = Literal["auto", "memory", "kuzu"]
AccountMode = Literal["prune", "migrate"]

app = typer.Typer(name="zhvault", help="Zhihu backup CLI (zhvault)", no_args_is_help=True)
auth_app = typer.Typer(help="authentication helpers", no_args_is_help=True)
graph_app = typer.Typer(help="relationship graph helpers", no_args_is_help=True)
edge_app = typer.Typer(help="manual edge mutations", no_args_is_help=True)
search_app = typer.Typer(help="semantic search over backed-up markdown", no_args_is_help=True)
account_app = typer.Typer(
    help="DANGER-gated Zhihu follow/collect mutations (plan=safe, apply=writes)",
    no_args_is_help=True,
)

app.add_typer(auth_app, name="auth")
app.add_typer(graph_app, name="graph")
graph_app.add_typer(edge_app, name="edge")
app.add_typer(search_app, name="search")
app.add_typer(account_app, name="account")


def _run(handler: Callable[..., int], **kwargs: object) -> None:
    ns = SimpleNamespace(**kwargs)
    setup_logging(
        json_mode=bool(getattr(ns, "json", False)),
        data_dir=Path(getattr(ns, "data_dir", "data")),
        verbose=bool(getattr(ns, "verbose", False)),
        log_file=Path(ns.log_file) if getattr(ns, "log_file", None) else None,
    )
    raise typer.Exit(int(handler(ns)))


def _common_options(
    data_dir: str = typer.Option("data", "--data-dir", help="root data directory"),
    engine: EngineName = typer.Option("sqlite", "--engine", help="meta engine"),
    json: bool = typer.Option(False, "--json", help="machine-readable stdout"),
    verbose: bool = typer.Option(False, "--verbose", help="debug console + per-item skip logs"),
    log_file: str | None = typer.Option(
        None, "--log-file", help="override log path (default data/logs/backup_YYYYMMDD.log)"
    ),
) -> dict[str, object]:
    return {
        "data_dir": data_dir,
        "engine": engine,
        "json": json,
        "verbose": verbose,
        "log_file": log_file,
    }


def _backup_options(
    source: str = typer.Option(
        "all",
        "--source",
        help="collection|pin|asked|followed|vote|answer|article|column|zvideo|activity|social|people|all",
    ),
    full: bool = typer.Option(False, "--full", help="re-validate from offset 0 (ignores checkpoint)"),
    limit: int = typer.Option(20, "--limit"),
    cookie_file: str | None = typer.Option(None, "--cookie-file"),
    url_config: str = typer.Option("url.json", "--url-config"),
    collection_id: list[str] = typer.Option([], "--collection-id"),
    user: str | None = typer.Option(
        None,
        "--user",
        help="target url_token or people URL (default: logged-in /me for member sources)",
    ),
    x_zse_96: str | None = typer.Option(None, "--x-zse-96", help="optional x-zse-96 header override"),
    asset_workers: int = typer.Option(
        8,
        "--asset-workers",
        help="parallel image download workers (default 8; use 1 for serial)",
    ),
    asset_link: AssetLinkStyle = typer.Option(
        "wikilink",
        "--asset-link",
        help="image link style in markdown (default wikilink for Obsidian)",
    ),
    max_depth: int = typer.Option(
        1, "--max-depth", help="social crawl depth (MVP: only 1 supported)"
    ),
) -> dict[str, object]:
    return {
        "source": source,
        "full": full,
        "limit": limit,
        "cookie_file": cookie_file,
        "url_config": url_config,
        "collection_id": collection_id,
        "user": user,
        "x_zse_96": x_zse_96,
        "asset_workers": asset_workers,
        "asset_link": asset_link,
        "max_depth": max_depth,
    }


def _vector_backend_options(
    vector_backend: VectorBackend | None = typer.Option(
        None,
        "--vector-backend",
        help="vector store backend (default: chroma if installed, else error)",
    ),
) -> dict[str, object]:
    return {"vector_backend": vector_backend}


def _embed_options(
    embed_provider: EmbedProvider | None = typer.Option(
        None,
        "--embed-provider",
        help="embedding provider (default: local if sentence-transformers installed, else error)",
    ),
    embed_model: str | None = typer.Option(None, "--embed-model", help="model id (local/http)"),
    embed_api_base: str | None = typer.Option(None, "--embed-api-base", help="API base URL (http)"),
    embed_api_key: str | None = typer.Option(
        None,
        "--embed-api-key",
        help="API key (http; default from ZHIHU_EMBED_API_KEY env)",
    ),
) -> dict[str, object]:
    return {
        "embed_provider": embed_provider,
        "embed_model": embed_model,
        "embed_api_base": embed_api_base,
        "embed_api_key": embed_api_key,
    }


def _edge_key_options(
    from_id: str = typer.Option(..., "--from", help="from node key"),
    to_id: str = typer.Option(..., "--to", help="to node key"),
    kind: str = typer.Option("follows", "--kind", help="edge kind (default follows)"),
) -> dict[str, object]:
    return {"from_id": from_id, "to_id": to_id, "kind": kind}


@auth_app.command("set-cookie", help="store cookie JSON into meta engine")
def auth_set_cookie(
    cookie_file: str = typer.Argument(help="path to Cookies.json"),
    data_dir: str = typer.Option("data", "--data-dir", help="root data directory"),
    engine: EngineName = typer.Option("sqlite", "--engine"),
    json: bool = typer.Option(False, "--json", help="machine-readable stdout"),
    verbose: bool = typer.Option(False, "--verbose", help="debug console + per-item skip logs"),
    log_file: str | None = typer.Option(None, "--log-file"),
) -> None:
    _run(
        cmd_auth,
        cookie_file=cookie_file,
        **_common_options(data_dir, engine, json, verbose, log_file),
    )


@app.command("status", help="show engine status")
def status(
    data_dir: str = typer.Option("data", "--data-dir", help="root data directory"),
    engine: EngineName = typer.Option("sqlite", "--engine"),
    json: bool = typer.Option(False, "--json", help="machine-readable stdout"),
    verbose: bool = typer.Option(False, "--verbose", help="debug console + per-item skip logs"),
    log_file: str | None = typer.Option(None, "--log-file"),
) -> None:
    _run(cmd_status, **_common_options(data_dir, engine, json, verbose, log_file))


@app.command("backup", help="incremental backup (resumes checkpoints)")
def backup(
    data_dir: str = typer.Option("data", "--data-dir", help="root data directory"),
    engine: EngineName = typer.Option("sqlite", "--engine"),
    json: bool = typer.Option(False, "--json", help="machine-readable stdout"),
    verbose: bool = typer.Option(False, "--verbose", help="debug console + per-item skip logs"),
    log_file: str | None = typer.Option(None, "--log-file"),
    source: str = typer.Option(
        "all",
        "--source",
        help="collection|pin|asked|followed|vote|answer|article|column|zvideo|activity|social|people|all",
    ),
    full: bool = typer.Option(False, "--full", help="re-validate from offset 0 (ignores checkpoint)"),
    limit: int = typer.Option(20, "--limit"),
    cookie_file: str | None = typer.Option(None, "--cookie-file"),
    url_config: str = typer.Option("url.json", "--url-config"),
    collection_id: list[str] = typer.Option([], "--collection-id"),
    user: str | None = typer.Option(
        None,
        "--user",
        help="target url_token or people URL (default: logged-in /me for member sources)",
    ),
    x_zse_96: str | None = typer.Option(None, "--x-zse-96", help="optional x-zse-96 header override"),
    asset_workers: int = typer.Option(8, "--asset-workers"),
    asset_link: AssetLinkStyle = typer.Option("wikilink", "--asset-link"),
    max_depth: int = typer.Option(1, "--max-depth", help="social crawl depth (MVP: only 1 supported)"),
) -> None:
    _run(
        cmd_backup,
        **_common_options(data_dir, engine, json, verbose, log_file),
        **_backup_options(
            source,
            full,
            limit,
            cookie_file,
            url_config,
            collection_id,
            user,
            x_zse_96,
            asset_workers,
            asset_link,
            max_depth,
        ),
    )


@app.command("resume", help="alias of backup (continue checkpoints)")
def resume(
    data_dir: str = typer.Option("data", "--data-dir", help="root data directory"),
    engine: EngineName = typer.Option("sqlite", "--engine"),
    json: bool = typer.Option(False, "--json", help="machine-readable stdout"),
    verbose: bool = typer.Option(False, "--verbose", help="debug console + per-item skip logs"),
    log_file: str | None = typer.Option(None, "--log-file"),
    source: str = typer.Option(
        "all",
        "--source",
        help="collection|pin|asked|followed|vote|answer|article|column|zvideo|activity|social|people|all",
    ),
    full: bool = typer.Option(False, "--full", help="re-validate from offset 0 (ignores checkpoint)"),
    limit: int = typer.Option(20, "--limit"),
    cookie_file: str | None = typer.Option(None, "--cookie-file"),
    url_config: str = typer.Option("url.json", "--url-config"),
    collection_id: list[str] = typer.Option([], "--collection-id"),
    user: str | None = typer.Option(
        None,
        "--user",
        help="target url_token or people URL (default: logged-in /me for member sources)",
    ),
    x_zse_96: str | None = typer.Option(None, "--x-zse-96", help="optional x-zse-96 header override"),
    asset_workers: int = typer.Option(8, "--asset-workers"),
    asset_link: AssetLinkStyle = typer.Option("wikilink", "--asset-link"),
    max_depth: int = typer.Option(1, "--max-depth", help="social crawl depth (MVP: only 1 supported)"),
) -> None:
    _run(
        cmd_resume,
        **_common_options(data_dir, engine, json, verbose, log_file),
        **_backup_options(
            source,
            full,
            limit,
            cookie_file,
            url_config,
            collection_id,
            user,
            x_zse_96,
            asset_workers,
            asset_link,
            max_depth,
        ),
    )


@graph_app.command("rebuild", help="offline rebuild graph.json from meta")
def graph_rebuild(
    data_dir: str = typer.Option("data", "--data-dir", help="root data directory"),
    engine: EngineName = typer.Option("sqlite", "--engine"),
    json: bool = typer.Option(False, "--json", help="machine-readable stdout"),
    verbose: bool = typer.Option(False, "--verbose", help="debug console + per-item skip logs"),
    log_file: str | None = typer.Option(None, "--log-file"),
) -> None:
    _run(cmd_graph_rebuild, **_common_options(data_dir, engine, json, verbose, log_file))


@graph_app.command("sync", help="build derived graph query index")
def graph_sync(
    data_dir: str = typer.Option("data", "--data-dir", help="root data directory"),
    engine: EngineName = typer.Option("sqlite", "--engine"),
    json: bool = typer.Option(False, "--json", help="machine-readable stdout"),
    verbose: bool = typer.Option(False, "--verbose", help="debug console + per-item skip logs"),
    log_file: str | None = typer.Option(None, "--log-file"),
    backend: GraphSyncBackend = typer.Option(
        "kuzu", "--backend", help="derived index backend (default kuzu)"
    ),
) -> None:
    _run(
        cmd_graph_sync,
        **_common_options(data_dir, engine, json, verbose, log_file),
        backend=backend,
    )


@graph_app.command("query", help="subgraph from a node key")
def graph_query(
    from_id: str = typer.Option(
        ...,
        "--from",
        help=(
            "start node key (e.g. user:{token}, answer:{qid}:{aid}); "
            "legacy data may have both user:numeric and user:token nodes"
        ),
    ),
    depth: int = typer.Option(1, "--depth", help="max hop depth (default 1)"),
    kind: list[str] | None = typer.Option(
        None, "--kind", help="edge kind filter (repeatable); use 'all' for no filter"
    ),
    backend: GraphQueryBackend = typer.Option(
        "auto",
        "--backend",
        help="query backend: auto (kuzu if synced), memory (BFS), or kuzu (require sync)",
    ),
    data_dir: str = typer.Option("data", "--data-dir", help="root data directory"),
    engine: EngineName = typer.Option("sqlite", "--engine"),
    json: bool = typer.Option(False, "--json", help="machine-readable stdout"),
    verbose: bool = typer.Option(False, "--verbose", help="debug console + per-item skip logs"),
    log_file: str | None = typer.Option(None, "--log-file"),
) -> None:
    _run(
        cmd_graph_query,
        **_common_options(data_dir, engine, json, verbose, log_file),
        from_id=from_id,
        depth=depth,
        kind=kind,
        backend=backend,
    )


@edge_app.command("add", help="upsert a manual graph edge")
def graph_edge_add(
    from_id: str = typer.Option(..., "--from", help="from node key"),
    to_id: str = typer.Option(..., "--to", help="to node key"),
    kind: str = typer.Option("follows", "--kind", help="edge kind (default follows)"),
    data_dir: str = typer.Option("data", "--data-dir", help="root data directory"),
    engine: EngineName = typer.Option("sqlite", "--engine"),
    json: bool = typer.Option(False, "--json", help="machine-readable stdout"),
    verbose: bool = typer.Option(False, "--verbose", help="debug console + per-item skip logs"),
    log_file: str | None = typer.Option(None, "--log-file"),
) -> None:
    _run(
        cmd_graph_edge_add,
        **_common_options(data_dir, engine, json, verbose, log_file),
        **_edge_key_options(from_id, to_id, kind),
    )


@edge_app.command("remove", help="delete a graph edge")
def graph_edge_remove(
    from_id: str = typer.Option(..., "--from", help="from node key"),
    to_id: str = typer.Option(..., "--to", help="to node key"),
    kind: str = typer.Option("follows", "--kind", help="edge kind (default follows)"),
    data_dir: str = typer.Option("data", "--data-dir", help="root data directory"),
    engine: EngineName = typer.Option("sqlite", "--engine"),
    json: bool = typer.Option(False, "--json", help="machine-readable stdout"),
    verbose: bool = typer.Option(False, "--verbose", help="debug console + per-item skip logs"),
    log_file: str | None = typer.Option(None, "--log-file"),
) -> None:
    _run(
        cmd_graph_edge_remove,
        **_common_options(data_dir, engine, json, verbose, log_file),
        **_edge_key_options(from_id, to_id, kind),
    )


@search_app.command("index", help="chunk, embed, and upsert into VectorStore")
def search_index(
    data_dir: str = typer.Option("data", "--data-dir", help="root data directory"),
    engine: EngineName = typer.Option("sqlite", "--engine"),
    json: bool = typer.Option(False, "--json", help="machine-readable stdout"),
    verbose: bool = typer.Option(False, "--verbose", help="debug console + per-item skip logs"),
    log_file: str | None = typer.Option(None, "--log-file"),
    vector_backend: VectorBackend | None = typer.Option(None, "--vector-backend"),
    embed_provider: EmbedProvider | None = typer.Option(None, "--embed-provider"),
    embed_model: str | None = typer.Option(None, "--embed-model", help="model id (local/http)"),
    embed_api_base: str | None = typer.Option(None, "--embed-api-base", help="API base URL (http)"),
    embed_api_key: str | None = typer.Option(
        None, "--embed-api-key", help="API key (http; default from ZHIHU_EMBED_API_KEY env)"
    ),
) -> None:
    _run(
        cmd_search_index,
        **_common_options(data_dir, engine, json, verbose, log_file),
        **_vector_backend_options(vector_backend),
        **_embed_options(embed_provider, embed_model, embed_api_base, embed_api_key),
    )


@search_app.command("semantic", help="embed query and retrieve nearest chunks")
def search_semantic(
    query: str = typer.Argument(help="search query text"),
    top_k: int = typer.Option(10, "--top-k", help="number of hits (default 10)"),
    expand_graph: int | None = typer.Option(
        None,
        "--expand-graph",
        help="BFS graph depth from each hit item_key (best-effort neighbors)",
    ),
    kind: list[str] | None = typer.Option(
        None,
        "--kind",
        help="edge kind filter for --expand-graph (repeatable); use 'all' for no filter",
    ),
    data_dir: str = typer.Option("data", "--data-dir", help="root data directory"),
    engine: EngineName = typer.Option("sqlite", "--engine"),
    json: bool = typer.Option(False, "--json", help="machine-readable stdout"),
    verbose: bool = typer.Option(False, "--verbose", help="debug console + per-item skip logs"),
    log_file: str | None = typer.Option(None, "--log-file"),
    vector_backend: VectorBackend | None = typer.Option(None, "--vector-backend"),
    embed_provider: EmbedProvider | None = typer.Option(None, "--embed-provider"),
    embed_model: str | None = typer.Option(None, "--embed-model", help="model id (local/http)"),
    embed_api_base: str | None = typer.Option(None, "--embed-api-base", help="API base URL (http)"),
    embed_api_key: str | None = typer.Option(
        None, "--embed-api-key", help="API key (http; default from ZHIHU_EMBED_API_KEY env)"
    ),
) -> None:
    _run(
        cmd_search_semantic,
        query=query,
        top_k=top_k,
        expand_graph=expand_graph,
        kind=kind,
        **_common_options(data_dir, engine, json, verbose, log_file),
        **_vector_backend_options(vector_backend),
        **_embed_options(embed_provider, embed_model, embed_api_base, embed_api_key),
    )


@account_app.command("plan", help="build mutate plan from local inventory (no Zhihu writes)")
def account_plan(
    mode: AccountMode = typer.Option(..., "--mode"),
    source: str = typer.Option(
        ..., "--source", help="comma list: following,collection,followed (required; no default)"
    ),
    from_data_dir: str | None = typer.Option(None, "--from-data-dir", help="account A data dir (migrate)"),
    map_collection: list[str] = typer.Option(
        [], "--map-collection", help="A_id=B_id collection map (repeatable; migrate)"
    ),
    limit: int | None = typer.Option(None, "--limit", help="cap actions in plan"),
    cookie_file: str | None = typer.Option(None, "--cookie-file"),
    x_zse_96: str | None = typer.Option(None, "--x-zse-96"),
    data_dir: str = typer.Option("data", "--data-dir", help="root data directory"),
    engine: EngineName = typer.Option("sqlite", "--engine"),
    json: bool = typer.Option(False, "--json", help="machine-readable stdout"),
    verbose: bool = typer.Option(False, "--verbose", help="debug console + per-item skip logs"),
    log_file: str | None = typer.Option(None, "--log-file"),
) -> None:
    _run(
        cmd_account_plan,
        mode=mode,
        source=source,
        from_data_dir=from_data_dir,
        map_collection=map_collection,
        limit=limit,
        cookie_file=cookie_file,
        x_zse_96=x_zse_96,
        **_common_options(data_dir, engine, json, verbose, log_file),
    )


@account_app.command(
    "apply",
    help="DANGER: apply plan (requires --i-understand-danger and --confirm APPLY)",
)
def account_apply(
    plan: str = typer.Option(..., "--plan", help="path to plan JSON from account plan"),
    i_understand_danger: bool = typer.Option(
        False, "--i-understand-danger", help="acknowledge live Zhihu account mutation"
    ),
    confirm: str | None = typer.Option(None, "--confirm", help="must be exactly APPLY to proceed"),
    cookie_file: str | None = typer.Option(None, "--cookie-file"),
    x_zse_96: str | None = typer.Option(None, "--x-zse-96"),
    data_dir: str = typer.Option("data", "--data-dir", help="root data directory"),
    engine: EngineName = typer.Option("sqlite", "--engine"),
    json: bool = typer.Option(False, "--json", help="machine-readable stdout"),
    verbose: bool = typer.Option(False, "--verbose", help="debug console + per-item skip logs"),
    log_file: str | None = typer.Option(None, "--log-file"),
) -> None:
    _run(
        cmd_account_apply,
        plan=plan,
        i_understand_danger=i_understand_danger,
        confirm=confirm,
        cookie_file=cookie_file,
        x_zse_96=x_zse_96,
        **_common_options(data_dir, engine, json, verbose, log_file),
    )
