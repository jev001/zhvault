from __future__ import annotations

import importlib.util
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from graph_kuzu import KuzuBackendError
from http_client import ZhihuClient
from search.embed import open_embedder
from search.store import VectorBackendError

ME_URL = "https://www.zhihu.com/api/v4/me"

log = logging.getLogger("zhvault")


def setup_logging(
    *,
    json_mode: bool,
    data_dir: Path,
    verbose: bool = False,
    log_file: Path | None = None,
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


def data_paths(data_dir: Path) -> tuple[Path, Path, Path]:
    contents = data_dir / "contents"
    assets = data_dir / "assets"
    meta = data_dir / "meta"
    contents.mkdir(parents=True, exist_ok=True)
    assets.mkdir(parents=True, exist_ok=True)
    meta.mkdir(parents=True, exist_ok=True)
    (data_dir / "logs").mkdir(parents=True, exist_ok=True)
    return contents, assets, meta


def json_print(obj: Any) -> None:
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def log_event(ev: dict[str, Any], *, verbose: bool) -> None:
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


def require_max_depth_mvp(n: int) -> str | None:
    if int(n) != 1:
        return f"--max-depth={n} not implemented yet (only 1 supported)"
    return None


def engine_meta_dir(meta: Path, engine_name: str) -> Path:
    from storage import normalize_engine_name

    return Path(meta) / normalize_engine_name(engine_name)


def vectors_root(meta: Path, engine_name: str) -> Path:
    return engine_meta_dir(meta, engine_name) / "vectors"


def chroma_importable() -> bool:
    return importlib.util.find_spec("chromadb") is not None


def sentence_transformers_importable() -> bool:
    return importlib.util.find_spec("sentence_transformers") is not None


def kuzu_importable() -> bool:
    return importlib.util.find_spec("kuzu") is not None


def kuzu_db_path(meta: Path, engine_name: str) -> Path:
    return engine_meta_dir(meta, engine_name) / "graph_query" / "kuzu"


def resolve_graph_query_backend(explicit: str | None, db_path: Path) -> str:
    backend = explicit or "auto"
    if backend == "memory":
        return "memory"
    if backend == "kuzu":
        if not kuzu_importable():
            raise KuzuBackendError(
                "kuzu backend requires kuzu. "
                "Install with: pip install 'zhvault[kuzu]'"
            )
        if not db_path.exists():
            raise KuzuBackendError(
                f"kuzu graph index not found at {db_path}; "
                "run: zhvault graph sync --backend kuzu"
            )
        return "kuzu"
    if backend == "auto":
        if kuzu_importable() and db_path.exists():
            return "kuzu"
        return "memory"
    raise ValueError(f"unsupported graph query backend: {backend!r}")


class EmbedProviderError(RuntimeError):
    """Raised when --embed-provider cannot be resolved."""


def resolve_embed_provider(explicit: str | None) -> str:
    if explicit:
        return explicit
    if sentence_transformers_importable():
        return "local"
    raise EmbedProviderError(
        "no embed provider specified and sentence-transformers not installed. "
        "Install with: pip install 'zhvault[search-ml]' "
        "or pass --embed-provider hash|http"
    )


def open_embedder_from_args(args) -> Any:
    name = resolve_embed_provider(getattr(args, "embed_provider", None))
    return open_embedder(
        name,
        model=getattr(args, "embed_model", None),
        api_base=getattr(args, "embed_api_base", None),
        api_key=getattr(args, "embed_api_key", None),
    )


def resolve_vector_backend(explicit: str | None) -> str:
    if explicit:
        return explicit
    if chroma_importable():
        return "chroma"
    raise VectorBackendError(
        "chroma backend requires chromadb. "
        "Install with: pip install 'zhvault[chroma]' "
        "(or pass --vector-backend memory)"
    )


def kinds_from_args(kind: list[str] | None) -> set[str] | None:
    if kind is None:
        return None
    if "all" in kind:
        return None
    return set(kind)


def cmd_fail(args, msg: str, code: int = 2) -> int:
    log.error("%s", msg)
    if args.json:
        json_print({"event": "error", "error": msg})
    else:
        print(msg, file=sys.stderr)
    return code


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def resolve_ego(engine) -> str | None:
    cookies = engine.get_cookie()
    if not cookies:
        return None
    try:
        me = ZhihuClient(cookies).get_json(ME_URL)
        token = str((me or {}).get("url_token") or (me or {}).get("id") or "")
        return token or None
    except Exception:
        return None
