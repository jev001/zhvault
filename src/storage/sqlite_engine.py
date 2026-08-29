from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Optional

from models import Checkpoint, GraphEdge, ItemRecord
from .base import StorageEngine


class SqliteEngine(StorageEngine):
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        cur = self._conn.cursor()
        cur.executescript(
            """
            CREATE TABLE IF NOT EXISTS kv (
                k TEXT PRIMARY KEY,
                v TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS checkpoints (
                source TEXT NOT NULL,
                source_id TEXT NOT NULL,
                offset INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT,
                PRIMARY KEY (source, source_id)
            );
            CREATE TABLE IF NOT EXISTS items (
                key TEXT PRIMARY KEY,
                item_type TEXT NOT NULL,
                zhihu_id TEXT NOT NULL,
                url TEXT,
                title TEXT,
                content_updated_at TEXT,
                content_hash TEXT,
                path TEXT,
                last_seen_at TEXT,
                orphaned INTEGER NOT NULL DEFAULT 0,
                extra TEXT
            );
            CREATE TABLE IF NOT EXISTS membership (
                key TEXT NOT NULL,
                owner_kind TEXT NOT NULL,
                owner_id TEXT NOT NULL,
                PRIMARY KEY (key, owner_kind, owner_id)
            );
            CREATE TABLE IF NOT EXISTS assets (
                url TEXT PRIMARY KEY,
                path TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS item_assets (
                item_key TEXT NOT NULL,
                asset_url TEXT NOT NULL,
                PRIMARY KEY (item_key, asset_url)
            );
            CREATE TABLE IF NOT EXISTS failed_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key TEXT,
                source TEXT,
                source_id TEXT,
                error TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS graph_edges (
                from_id TEXT NOT NULL,
                to_id TEXT NOT NULL,
                kind TEXT NOT NULL,
                origin TEXT NOT NULL,
                seen_at TEXT,
                PRIMARY KEY (from_id, to_id, kind)
            );
            """
        )
        self._migrate_assets_columns()
        self._conn.commit()

    def _migrate_assets_columns(self) -> None:
        cols = {row[1] for row in self._conn.execute("PRAGMA table_info(assets)").fetchall()}
        if "source_url" not in cols:
            self._conn.execute("ALTER TABLE assets ADD COLUMN source_url TEXT")
        if "origin_url" not in cols:
            self._conn.execute("ALTER TABLE assets ADD COLUMN origin_url TEXT")

    def get_cookie(self) -> dict[str, str]:
        row = self._conn.execute("SELECT v FROM kv WHERE k = ?", ("cookie",)).fetchone()
        if not row:
            return {}
        data = json.loads(row["v"])
        return {str(k): str(v) for k, v in data.items()}

    def set_cookie(self, cookies: dict[str, str]) -> None:
        self._conn.execute(
            "INSERT INTO kv(k, v) VALUES(?, ?) ON CONFLICT(k) DO UPDATE SET v = excluded.v",
            ("cookie", json.dumps(cookies, ensure_ascii=False)),
        )
        self._conn.commit()

    def get_checkpoint(self, source: str, source_id: str) -> Optional[Checkpoint]:
        row = self._conn.execute(
            "SELECT source, source_id, offset, updated_at FROM checkpoints WHERE source = ? AND source_id = ?",
            (source, source_id),
        ).fetchone()
        if not row:
            return None
        return Checkpoint(
            source=row["source"],
            source_id=row["source_id"],
            offset=row["offset"],
            updated_at=row["updated_at"],
        )

    def set_checkpoint(self, checkpoint: Checkpoint) -> None:
        self._conn.execute(
            """
            INSERT INTO checkpoints(source, source_id, offset, updated_at)
            VALUES(?, ?, ?, ?)
            ON CONFLICT(source, source_id) DO UPDATE SET
                offset = excluded.offset,
                updated_at = excluded.updated_at
            """,
            (checkpoint.source, checkpoint.source_id, checkpoint.offset, checkpoint.updated_at),
        )
        self._conn.commit()

    def get_item(self, key: str) -> Optional[ItemRecord]:
        row = self._conn.execute("SELECT * FROM items WHERE key = ?", (key,)).fetchone()
        if not row:
            return None
        extra = json.loads(row["extra"] or "{}")
        return ItemRecord(
            key=row["key"],
            item_type=row["item_type"],
            zhihu_id=row["zhihu_id"],
            url=row["url"] or "",
            title=row["title"] or "",
            content_updated_at=row["content_updated_at"],
            content_hash=row["content_hash"],
            path=row["path"],
            last_seen_at=row["last_seen_at"],
            orphaned=bool(row["orphaned"]),
            extra=extra,
        )

    def upsert_item(self, record: ItemRecord) -> None:
        self._conn.execute(
            """
            INSERT INTO items(
                key, item_type, zhihu_id, url, title, content_updated_at,
                content_hash, path, last_seen_at, orphaned, extra
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                item_type = excluded.item_type,
                zhihu_id = excluded.zhihu_id,
                url = excluded.url,
                title = excluded.title,
                content_updated_at = excluded.content_updated_at,
                content_hash = excluded.content_hash,
                path = excluded.path,
                last_seen_at = excluded.last_seen_at,
                orphaned = excluded.orphaned,
                extra = excluded.extra
            """,
            (
                record.key,
                record.item_type,
                record.zhihu_id,
                record.url,
                record.title,
                record.content_updated_at,
                record.content_hash,
                record.path,
                record.last_seen_at,
                1 if record.orphaned else 0,
                json.dumps(record.extra, ensure_ascii=False),
            ),
        )
        self._conn.commit()

    def link_membership(self, key: str, owner_kind: str, owner_id: str) -> None:
        self._conn.execute(
            """
            INSERT OR IGNORE INTO membership(key, owner_kind, owner_id)
            VALUES(?, ?, ?)
            """,
            (key, owner_kind, owner_id),
        )
        self._conn.commit()

    def get_asset_path(self, url: str) -> Optional[str]:
        row = self._conn.execute("SELECT path FROM assets WHERE url = ?", (url,)).fetchone()
        return row["path"] if row else None

    def get_asset_meta(self, url: str) -> dict[str, str]:
        row = self._conn.execute(
            "SELECT source_url, origin_url FROM assets WHERE url = ?", (url,)
        ).fetchone()
        if not row:
            return {}
        out: dict[str, str] = {}
        if row["source_url"]:
            out["source_url"] = str(row["source_url"])
        if row["origin_url"]:
            out["origin_url"] = str(row["origin_url"])
        return out

    def set_asset_path(
        self,
        url: str,
        path: str,
        *,
        source_url: Optional[str] = None,
        origin_url: Optional[str] = None,
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO assets(url, path, source_url, origin_url) VALUES(?, ?, ?, ?)
            ON CONFLICT(url) DO UPDATE SET
                path = excluded.path,
                source_url = COALESCE(excluded.source_url, assets.source_url),
                origin_url = COALESCE(excluded.origin_url, assets.origin_url)
            """,
            (url, path, source_url, origin_url),
        )
        self._conn.commit()

    def replace_item_assets(self, item_key: str, asset_urls: list[str]) -> None:
        self._conn.execute("DELETE FROM item_assets WHERE item_key = ?", (item_key,))
        for url in asset_urls:
            self._conn.execute(
                "INSERT OR IGNORE INTO item_assets(item_key, asset_url) VALUES(?, ?)",
                (item_key, url),
            )
        self._conn.commit()

    def list_item_assets(self, item_key: str) -> list[str]:
        rows = self._conn.execute(
            "SELECT asset_url FROM item_assets WHERE item_key = ? ORDER BY asset_url",
            (item_key,),
        ).fetchall()
        return [r["asset_url"] for r in rows]

    def record_failed(self, key: str, source: str, source_id: str, error: str) -> None:
        self._conn.execute(
            "INSERT INTO failed_items(key, source, source_id, error) VALUES(?, ?, ?, ?)",
            (key, source, source_id, error),
        )
        self._conn.commit()

    def upsert_graph_edge(self, edge: GraphEdge) -> None:
        if edge.origin == "api":
            row = self._conn.execute(
                "SELECT origin FROM graph_edges WHERE from_id = ? AND to_id = ? AND kind = ?",
                (edge.from_id, edge.to_id, edge.kind),
            ).fetchone()
            if row and row["origin"] == "manual":
                return
        self._conn.execute(
            """
            INSERT OR REPLACE INTO graph_edges(from_id, to_id, kind, origin, seen_at)
            VALUES(?, ?, ?, ?, ?)
            """,
            (edge.from_id, edge.to_id, edge.kind, edge.origin, edge.seen_at),
        )
        self._conn.commit()

    def remove_graph_edge(self, from_id: str, to_id: str, kind: str) -> None:
        self._conn.execute(
            "DELETE FROM graph_edges WHERE from_id = ? AND to_id = ? AND kind = ?",
            (from_id, to_id, kind),
        )
        self._conn.commit()

    def list_graph_edges(self) -> list[GraphEdge]:
        rows = self._conn.execute(
            "SELECT from_id, to_id, kind, origin, seen_at FROM graph_edges ORDER BY from_id, to_id, kind"
        ).fetchall()
        return [GraphEdge.from_dict(dict(r)) for r in rows]

    def list_items(self) -> list[ItemRecord]:
        rows = self._conn.execute("SELECT * FROM items ORDER BY key").fetchall()
        out: list[ItemRecord] = []
        for row in rows:
            extra = json.loads(row["extra"] or "{}")
            out.append(
                ItemRecord(
                    key=row["key"],
                    item_type=row["item_type"],
                    zhihu_id=row["zhihu_id"],
                    url=row["url"] or "",
                    title=row["title"] or "",
                    content_updated_at=row["content_updated_at"],
                    content_hash=row["content_hash"],
                    path=row["path"],
                    last_seen_at=row["last_seen_at"],
                    orphaned=bool(row["orphaned"]),
                    extra=extra,
                )
            )
        return out

    def list_membership(self) -> list[dict[str, str]]:
        rows = self._conn.execute(
            "SELECT key, owner_kind, owner_id FROM membership ORDER BY key, owner_kind, owner_id"
        ).fetchall()
        return [{"key": r["key"], "owner_kind": r["owner_kind"], "owner_id": r["owner_id"]} for r in rows]

    def status_summary(self) -> dict[str, Any]:
        items = self._conn.execute("SELECT COUNT(*) AS c FROM items").fetchone()["c"]
        orphaned = self._conn.execute(
            "SELECT COUNT(*) AS c FROM items WHERE orphaned = 1"
        ).fetchone()["c"]
        failed = self._conn.execute("SELECT COUNT(*) AS c FROM failed_items").fetchone()["c"]
        cps = self._conn.execute(
            "SELECT source, source_id, offset, updated_at FROM checkpoints ORDER BY source, source_id"
        ).fetchall()
        cookie = self.get_cookie()
        return {
            "engine": "sqlite",
            "cookie_present": bool(cookie.get("z_c0") or cookie),
            "items": items,
            "orphaned": orphaned,
            "failed": failed,
            "checkpoints": [dict(r) for r in cps],
        }

    def close(self) -> None:
        self._conn.close()
