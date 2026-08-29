from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from zhihu_backup.search.chunk import chunk_markdown
from zhihu_backup.search.embed import EmbeddingProvider
from zhihu_backup.search.store import VectorStore
from zhihu_backup.search.types import VectorRecord
from zhihu_backup.storage.base import StorageEngine


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _split_frontmatter(text: str) -> str:
    if not text.startswith("---"):
        return text
    end = text.find("\n---", 3)
    if end < 0:
        return text
    return text[end + 4 :].lstrip("\n")


def _resolve_path(contents_root: Path, stored: str) -> Path | None:
    p = Path(stored)
    candidates = [p] if p.is_absolute() else []
    candidates.append(contents_root / stored)
    parts = p.parts
    if parts and parts[0] == "contents":
        candidates.append(contents_root / Path(*parts[1:]))
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def _manifest_mismatch(path: Path, embedder: EmbeddingProvider) -> bool:
    if not path.is_file():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return True
    return data.get("model_id") != embedder.model_id or data.get("dimensions") != embedder.dimensions


def build_index(
    engine: StorageEngine,
    contents_root: Path,
    vectors_root: Path,
    *,
    store: VectorStore,
    embedder: EmbeddingProvider,
) -> dict[str, Any]:
    """Read items with path, chunk files, embed, upsert; write manifest.json; return stats."""
    contents_root = Path(contents_root)
    vectors_root = Path(vectors_root)
    vectors_root.mkdir(parents=True, exist_ok=True)
    manifest_path = vectors_root / "manifest.json"

    if _manifest_mismatch(manifest_path, embedder):
        store.clear()

    records: list[VectorRecord] = []
    items = 0
    skipped = 0
    for item in engine.list_items():
        if not item.path:
            skipped += 1
            continue
        md_path = _resolve_path(contents_root, item.path)
        if md_path is None:
            skipped += 1
            continue
        body = _split_frontmatter(md_path.read_text(encoding="utf-8"))
        chunks = chunk_markdown(body)
        if not chunks:
            skipped += 1
            continue
        vectors = embedder.embed(chunks)
        for i, (chunk, vector) in enumerate(zip(chunks, vectors)):
            records.append(
                VectorRecord(
                    id=f"{item.key}#{i}",
                    vector=vector,
                    document=chunk,
                    metadata={
                        "item_key": item.key,
                        "item_type": item.item_type,
                        "path": item.path,
                        "title": item.title or "",
                        "chunk_index": i,
                    },
                )
            )
        items += 1

    if records:
        store.upsert(records)

    manifest = {
        "model_id": embedder.model_id,
        "dimensions": embedder.dimensions,
        "backend": store.name,
        "updated_at": _now(),
        "chunks": len(records),
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    return {"chunks": len(records), "items": items, "skipped": skipped}
