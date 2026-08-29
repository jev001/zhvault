from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from zhihu_backup.models import Checkpoint, ItemRecord
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
            "failed_items": [],
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
            return (self._data.get("assets") or {}).get(url)

    def set_asset_path(self, url: str, path: str) -> None:
        with self._lock:
            self._data.setdefault("assets", {})[url] = path
            self._save()

    def record_failed(self, key: str, source: str, source_id: str, error: str) -> None:
        with self._lock:
            self._data.setdefault("failed_items", []).append(
                {"key": key, "source": source, "source_id": source_id, "error": error, "created_at": _now()}
            )
            self._save()

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
