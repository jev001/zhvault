"""RocksDB-backed StorageEngine via rocksdict (optional extra zhvault[rocksdb]).

`rocks` is a CLI alias for `rocksdb` (same meta dir: meta/rocksdb/).
"""

from __future__ import annotations

import importlib.util
import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from models import Checkpoint, GraphEdge, ItemRecord

from .base import StorageEngine

_PREFIX_CP = "cp:"
_PREFIX_ITEM = "item:"
_PREFIX_MEM = "mem:"
_PREFIX_ASSET = "asset:"
_PREFIX_ITEM_ASSETS = "item_assets:"
_PREFIX_FAILED = "failed:"
_PREFIX_GRAPH = "graph:"
_KEY_COOKIE = "cookie"


def rocksdict_available() -> bool:
    return importlib.util.find_spec("rocksdict") is not None


def require_rocksdict() -> None:
    if not rocksdict_available():
        raise RuntimeError(
            "rocksdb engine requires rocksdict. Install with: pip install 'zhvault[rocksdb]'"
        )


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class RocksEngine(StorageEngine):
    def __init__(self, engine_dir: Path):
        require_rocksdict()
        from rocksdict import Rdict

        self.engine_dir = Path(engine_dir)
        self.engine_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.engine_dir / "db"
        self._lock = threading.Lock()
        self._db = Rdict(str(self.db_path))
        self._maybe_migrate_json_stub()

    def _dumps(self, value: Any) -> str:
        return json.dumps(value, ensure_ascii=False)

    def _loads(self, raw: Any) -> Any:
        if raw is None:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        return json.loads(raw)

    def _get(self, key: str) -> Any | None:
        return self._loads(self._db.get(key))

    def _put(self, key: str, value: Any) -> None:
        self._db[key] = self._dumps(value)

    def _delete(self, key: str) -> None:
        if key in self._db:
            del self._db[key]

    def _iter_keys(self):
        # rocksdict: must use .keys(); bare iter(Rdict) indexes by int.
        return self._db.keys()

    def _keys_with_prefix(self, prefix: str) -> list[str]:
        return [k for k in self._iter_keys() if isinstance(k, str) and k.startswith(prefix)]

    def _db_empty(self) -> bool:
        return next(iter(self._iter_keys()), None) is None

    def _maybe_migrate_json_stub(self) -> None:
        """One-shot import from MVP JsonEngine stub at rocks/state.json."""
        stub = self.engine_dir / "rocks" / "state.json"
        if not stub.is_file() or not self._db_empty():
            return
        data = json.loads(stub.read_text(encoding="utf-8"))
        if data.get("cookie"):
            self._put(_KEY_COOKIE, data["cookie"])
        for ck, raw in (data.get("checkpoints") or {}).items():
            self._put(f"{_PREFIX_CP}{ck}", raw)
        for key, raw in (data.get("items") or {}).items():
            self._put(f"{_PREFIX_ITEM}{key}", raw)
        for entry in data.get("membership") or []:
            mk = (
                f"{_PREFIX_MEM}{entry['key']}\t{entry['owner_kind']}\t{entry['owner_id']}"
            )
            self._put(mk, entry)
        for url, raw in (data.get("assets") or {}).items():
            self._put(f"{_PREFIX_ASSET}{url}", raw)
        for item_key, urls in (data.get("item_assets") or {}).items():
            self._put(f"{_PREFIX_ITEM_ASSETS}{item_key}", urls)
        for i, row in enumerate(data.get("failed_items") or []):
            self._put(f"{_PREFIX_FAILED}{i:08d}", row)
        for gk, raw in (data.get("graph_edges") or {}).items():
            self._put(f"{_PREFIX_GRAPH}{gk}", raw)

    def get_cookie(self) -> dict[str, str]:
        with self._lock:
            raw = self._get(_KEY_COOKIE) or {}
            return {str(k): str(v) for k, v in raw.items()}

    def set_cookie(self, cookies: dict[str, str]) -> None:
        with self._lock:
            self._put(_KEY_COOKIE, dict(cookies))

    def get_checkpoint(self, source: str, source_id: str) -> Checkpoint | None:
        with self._lock:
            raw = self._get(f"{_PREFIX_CP}{source}:{source_id}")
            if not raw:
                return None
            return Checkpoint.from_dict(raw)

    def set_checkpoint(self, checkpoint: Checkpoint) -> None:
        with self._lock:
            self._put(
                f"{_PREFIX_CP}{checkpoint.source}:{checkpoint.source_id}",
                checkpoint.to_dict(),
            )

    def get_item(self, key: str) -> ItemRecord | None:
        with self._lock:
            raw = self._get(f"{_PREFIX_ITEM}{key}")
            if not raw:
                return None
            return ItemRecord.from_dict(raw)

    def upsert_item(self, record: ItemRecord) -> None:
        with self._lock:
            self._put(f"{_PREFIX_ITEM}{record.key}", record.to_dict())

    def link_membership(self, key: str, owner_kind: str, owner_id: str) -> None:
        with self._lock:
            mk = f"{_PREFIX_MEM}{key}\t{owner_kind}\t{owner_id}"
            if self._db.get(mk) is None:
                self._put(mk, {"key": key, "owner_kind": owner_kind, "owner_id": owner_id})

    def get_asset_path(self, url: str) -> str | None:
        with self._lock:
            raw = self._get(f"{_PREFIX_ASSET}{url}")
            if raw is None:
                return None
            if isinstance(raw, dict):
                return raw.get("path")
            return str(raw)

    def get_asset_meta(self, url: str) -> dict[str, str]:
        with self._lock:
            raw = self._get(f"{_PREFIX_ASSET}{url}")
            if not isinstance(raw, dict):
                return {}
            out: dict[str, str] = {}
            if raw.get("source_url"):
                out["source_url"] = str(raw["source_url"])
            if raw.get("origin_url"):
                out["origin_url"] = str(raw["origin_url"])
            return out

    def set_asset_path(
        self,
        url: str,
        path: str,
        *,
        source_url: str | None = None,
        origin_url: str | None = None,
    ) -> None:
        with self._lock:
            prev = self._get(f"{_PREFIX_ASSET}{url}")
            prev_dict = prev if isinstance(prev, dict) else {}
            entry: dict[str, str] = {"path": path}
            src = source_url or prev_dict.get("source_url")
            ori = origin_url or prev_dict.get("origin_url")
            if src:
                entry["source_url"] = str(src)
            if ori:
                entry["origin_url"] = str(ori)
            self._put(f"{_PREFIX_ASSET}{url}", entry)

    def replace_item_assets(self, item_key: str, asset_urls: list[str]) -> None:
        with self._lock:
            seen: set[str] = set()
            urls: list[str] = []
            for u in asset_urls:
                if u not in seen:
                    seen.add(u)
                    urls.append(u)
            self._put(f"{_PREFIX_ITEM_ASSETS}{item_key}", urls)

    def list_item_assets(self, item_key: str) -> list[str]:
        with self._lock:
            return list(self._get(f"{_PREFIX_ITEM_ASSETS}{item_key}") or [])

    def record_failed(self, key: str, source: str, source_id: str, error: str) -> None:
        with self._lock:
            n = len(self._keys_with_prefix(_PREFIX_FAILED))
            self._put(
                f"{_PREFIX_FAILED}{n:08d}",
                {
                    "key": key,
                    "source": source,
                    "source_id": source_id,
                    "error": error,
                    "created_at": _now(),
                },
            )

    def _graph_edge_key(self, from_id: str, to_id: str, kind: str) -> str:
        return f"{from_id}\t{to_id}\t{kind}"

    def upsert_graph_edge(self, edge: GraphEdge) -> None:
        with self._lock:
            key = f"{_PREFIX_GRAPH}{self._graph_edge_key(edge.from_id, edge.to_id, edge.kind)}"
            existing = self._get(key)
            if edge.origin == "api" and existing and existing.get("origin") == "manual":
                return
            self._put(key, edge.to_dict())

    def remove_graph_edge(self, from_id: str, to_id: str, kind: str) -> None:
        with self._lock:
            self._delete(
                f"{_PREFIX_GRAPH}{self._graph_edge_key(from_id, to_id, kind)}"
            )

    def list_graph_edges(self) -> list[GraphEdge]:
        with self._lock:
            out: list[GraphEdge] = []
            for k in self._keys_with_prefix(_PREFIX_GRAPH):
                raw = self._get(k)
                if raw:
                    out.append(GraphEdge.from_dict(raw))
            return out

    def list_items(self) -> list[ItemRecord]:
        with self._lock:
            out: list[ItemRecord] = []
            for k in self._keys_with_prefix(_PREFIX_ITEM):
                raw = self._get(k)
                if raw:
                    out.append(ItemRecord.from_dict(raw))
            return out

    def list_membership(self) -> list[dict[str, str]]:
        with self._lock:
            out: list[dict[str, str]] = []
            for k in self._keys_with_prefix(_PREFIX_MEM):
                raw = self._get(k)
                if isinstance(raw, dict):
                    out.append(
                        {
                            "key": str(raw["key"]),
                            "owner_kind": str(raw["owner_kind"]),
                            "owner_id": str(raw["owner_id"]),
                        }
                    )
            return out

    def status_summary(self) -> dict[str, Any]:
        with self._lock:
            items = []
            orphaned = 0
            for k in self._keys_with_prefix(_PREFIX_ITEM):
                raw = self._get(k)
                if not raw:
                    continue
                items.append(raw)
                if raw.get("orphaned"):
                    orphaned += 1
            cps = [self._get(k) for k in self._keys_with_prefix(_PREFIX_CP)]
            cps = [c for c in cps if c]
            cookie = self._get(_KEY_COOKIE) or {}
            return {
                "engine": "rocksdb",
                "backend": "rocksdict",
                "cookie_present": bool(cookie.get("z_c0") or cookie),
                "items": len(items),
                "orphaned": orphaned,
                "failed": len(self._keys_with_prefix(_PREFIX_FAILED)),
                "checkpoints": cps,
            }

    def close(self) -> None:
        with self._lock:
            self._db.close()
