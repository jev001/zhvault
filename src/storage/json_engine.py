from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from models import Checkpoint, GraphEdge, ItemRecord
from .base import StorageEngine


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class JsonEngine(StorageEngine):
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._data = self._load()

    def _default(self) -> dict[str, Any]:
        return {
            "cookie": {},
            "checkpoints": {},
            "items": {},
            "membership": [],
            "assets": {},
            "item_assets": {},
            "failed_items": [],
            "graph_edges": {},
        }

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return self._default()
        with open(self.path, "r", encoding="utf-8") as f:
            data = json.load(f)
        base = self._default()
        base.update(data or {})
        return base

    def _save(self) -> None:
        tmp = self.path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)
        tmp.replace(self.path)

    def _cp_key(self, source: str, source_id: str) -> str:
        return f"{source}:{source_id}"

    def get_cookie(self) -> dict[str, str]:
        with self._lock:
            return {str(k): str(v) for k, v in (self._data.get("cookie") or {}).items()}

    def set_cookie(self, cookies: dict[str, str]) -> None:
        with self._lock:
            self._data["cookie"] = dict(cookies)
            self._save()

    def get_checkpoint(self, source: str, source_id: str) -> Optional[Checkpoint]:
        with self._lock:
            raw = (self._data.get("checkpoints") or {}).get(self._cp_key(source, source_id))
            if not raw:
                return None
            return Checkpoint.from_dict(raw)

    def set_checkpoint(self, checkpoint: Checkpoint) -> None:
        with self._lock:
            self._data.setdefault("checkpoints", {})[self._cp_key(checkpoint.source, checkpoint.source_id)] = (
                checkpoint.to_dict()
            )
            self._save()

    def get_item(self, key: str) -> Optional[ItemRecord]:
        with self._lock:
            raw = (self._data.get("items") or {}).get(key)
            if not raw:
                return None
            return ItemRecord.from_dict(raw)

    def upsert_item(self, record: ItemRecord) -> None:
        with self._lock:
            self._data.setdefault("items", {})[record.key] = record.to_dict()
            self._save()

    def link_membership(self, key: str, owner_kind: str, owner_id: str) -> None:
        with self._lock:
            entry = {"key": key, "owner_kind": owner_kind, "owner_id": owner_id}
            mem = self._data.setdefault("membership", [])
            if entry not in mem:
                mem.append(entry)
                self._save()

    def get_asset_path(self, url: str) -> Optional[str]:
        with self._lock:
            raw = (self._data.get("assets") or {}).get(url)
            if raw is None:
                return None
            if isinstance(raw, dict):
                return raw.get("path")
            return str(raw)

    def get_asset_meta(self, url: str) -> dict[str, str]:
        with self._lock:
            raw = (self._data.get("assets") or {}).get(url)
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
        source_url: Optional[str] = None,
        origin_url: Optional[str] = None,
    ) -> None:
        with self._lock:
            assets = self._data.setdefault("assets", {})
            prev = assets.get(url)
            prev_dict = prev if isinstance(prev, dict) else {}
            entry = {"path": path}
            src = source_url or prev_dict.get("source_url")
            ori = origin_url or prev_dict.get("origin_url")
            if src:
                entry["source_url"] = src
            if ori:
                entry["origin_url"] = ori
            assets[url] = entry
            self._save()

    def replace_item_assets(self, item_key: str, asset_urls: list[str]) -> None:
        with self._lock:
            # dedupe preserve order
            seen: set[str] = set()
            urls: list[str] = []
            for u in asset_urls:
                if u not in seen:
                    seen.add(u)
                    urls.append(u)
            self._data.setdefault("item_assets", {})[item_key] = urls
            self._save()

    def list_item_assets(self, item_key: str) -> list[str]:
        with self._lock:
            return list((self._data.get("item_assets") or {}).get(item_key) or [])

    def record_failed(self, key: str, source: str, source_id: str, error: str) -> None:
        with self._lock:
            self._data.setdefault("failed_items", []).append(
                {"key": key, "source": source, "source_id": source_id, "error": error, "created_at": _now()}
            )
            self._save()

    def _graph_edge_key(self, from_id: str, to_id: str, kind: str) -> str:
        return f"{from_id}\t{to_id}\t{kind}"

    def upsert_graph_edge(self, edge: GraphEdge) -> None:
        with self._lock:
            key = self._graph_edge_key(edge.from_id, edge.to_id, edge.kind)
            edges = self._data.setdefault("graph_edges", {})
            existing = edges.get(key)
            if edge.origin == "api" and existing and existing.get("origin") == "manual":
                return
            edges[key] = edge.to_dict()
            self._save()

    def remove_graph_edge(self, from_id: str, to_id: str, kind: str) -> None:
        with self._lock:
            key = self._graph_edge_key(from_id, to_id, kind)
            self._data.setdefault("graph_edges", {}).pop(key, None)
            self._save()

    def list_graph_edges(self) -> list[GraphEdge]:
        with self._lock:
            edges = self._data.get("graph_edges") or {}
            return [GraphEdge.from_dict(v) for v in edges.values()]

    def list_items(self) -> list[ItemRecord]:
        with self._lock:
            items = self._data.get("items") or {}
            return [ItemRecord.from_dict(v) for v in items.values()]

    def list_membership(self) -> list[dict[str, str]]:
        with self._lock:
            return list(self._data.get("membership") or [])

    def status_summary(self) -> dict[str, Any]:
        with self._lock:
            items = self._data.get("items") or {}
            orphaned = sum(1 for v in items.values() if v.get("orphaned"))
            cps = list((self._data.get("checkpoints") or {}).values())
            cookie = self._data.get("cookie") or {}
            return {
                "engine": "json",
                "cookie_present": bool(cookie.get("z_c0") or cookie),
                "items": len(items),
                "orphaned": orphaned,
                "failed": len(self._data.get("failed_items") or []),
                "checkpoints": cps,
            }
