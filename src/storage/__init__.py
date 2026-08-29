from __future__ import annotations

import logging
from pathlib import Path

from .base import StorageEngine
from .json_engine import JsonEngine
from .rocks_engine import RocksEngine
from .sqlite_engine import SqliteEngine

log = logging.getLogger("zhvault.storage")


def normalize_engine_name(name: str | None) -> str:
    """Map CLI aliases; `rocks` → `rocksdb` (same meta directory)."""
    n = (name or "sqlite").lower().strip()
    if n == "rocks":
        return "rocksdb"
    return n


def open_engine(name: str, meta_root: Path) -> StorageEngine:
    name = normalize_engine_name(name)
    engine_dir = meta_root / name
    engine_dir.mkdir(parents=True, exist_ok=True)
    log.info("open engine=%s path=%s", name, engine_dir)
    if name == "sqlite":
        return SqliteEngine(engine_dir / "state.sqlite")
    if name == "json":
        return JsonEngine(engine_dir / "state.json")
    if name == "rocksdb":
        return RocksEngine(engine_dir)
    raise ValueError(f"unknown engine: {name}")


__all__ = [
    "JsonEngine",
    "RocksEngine",
    "SqliteEngine",
    "StorageEngine",
    "normalize_engine_name",
    "open_engine",
]
