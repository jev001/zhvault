from __future__ import annotations

"""RocksDB-backed engine.

MVP: file-backed stub with the same JSON schema as JsonEngine so --engine rocksdb
works without a native rocksdb dependency. Swap internals later without changing callers.
# ponytail: ceiling = real python-rocksdb; upgrade when dependency is acceptable.
"""

from pathlib import Path

from .json_engine import JsonEngine


class RocksEngine(JsonEngine):
    def __init__(self, path: Path):
        path = Path(path)
        path.mkdir(parents=True, exist_ok=True)
        super().__init__(path / "state.json")

    def status_summary(self):
        summary = super().status_summary()
        summary["engine"] = "rocksdb"
        summary["note"] = "file-backed stub; API-compatible with StorageEngine"
        return summary
