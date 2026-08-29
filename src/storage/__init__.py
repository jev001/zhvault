from __future__ import annotations

from pathlib import Path

from .base import StorageEngine
from .json_engine import JsonEngine
from .rocks_engine import RocksEngine
from .sqlite_engine import SqliteEngine


def open_engine(name: str, meta_root: Path) -> StorageEngine:
    name = (name or "sqlite").lower()
    engine_dir = meta_root / name
    engine_dir.mkdir(parents=True, exist_ok=True)
    if name == "sqlite":
        return SqliteEngine(engine_dir / "state.sqlite")
    if name == "json":
        return JsonEngine(engine_dir / "state.json")
    if name in ("rocksdb", "rocks"):
        return RocksEngine(engine_dir / "rocks")
    raise ValueError(f"unknown engine: {name}")


__all__ = [
    "JsonEngine",
    "RocksEngine",
    "SqliteEngine",
    "StorageEngine",
    "open_engine",
]
