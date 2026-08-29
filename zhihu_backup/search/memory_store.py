import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

from zhihu_backup.search.types import VectorHit, VectorRecord


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


def _matches_where(metadata: Mapping[str, Any], where: Mapping[str, Any] | None) -> bool:
    if not where:
        return True
    return all(metadata.get(k) == v for k, v in where.items())


class MemoryVectorStore:
    name = "memory"

    def __init__(self, persist_path: Path | None = None) -> None:
        self._persist_path = Path(persist_path) if persist_path else None
        self._records: dict[str, VectorRecord] = {}
        self._load()

    def _load(self) -> None:
        if not self._persist_path or not self._persist_path.is_file():
            return
        try:
            data = json.loads(self._persist_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        for row in data.get("records") or []:
            rec = VectorRecord(
                id=row["id"],
                vector=list(row["vector"]),
                document=row.get("document") or "",
                metadata=dict(row.get("metadata") or {}),
            )
            self._records[rec.id] = rec

    def _save(self) -> None:
        # ponytail: file dump so CLI index→semantic roundtrip works; chroma is the durable backend
        if not self._persist_path:
            return
        self._persist_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "records": [
                {
                    "id": r.id,
                    "vector": r.vector,
                    "document": r.document,
                    "metadata": r.metadata,
                }
                for r in self._records.values()
            ]
        }
        self._persist_path.write_text(json.dumps(payload), encoding="utf-8")

    def upsert(self, records: Sequence[VectorRecord]) -> None:
        for record in records:
            self._records[record.id] = record
        self._save()

    def delete(self, ids: Sequence[str]) -> None:
        for rid in ids:
            self._records.pop(rid, None)
        self._save()

    def query(
        self,
        vector: Sequence[float],
        *,
        top_k: int = 10,
        where: Mapping[str, Any] | None = None,
    ) -> list[VectorHit]:
        scored: list[tuple[float, VectorRecord]] = []
        for record in self._records.values():
            if not _matches_where(record.metadata, where):
                continue
            scored.append((_cosine(vector, record.vector), record))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [
            VectorHit(
                id=record.id,
                score=score,
                document=record.document,
                metadata=dict(record.metadata),
            )
            for score, record in scored[:top_k]
        ]

    def clear(self) -> None:
        self._records.clear()
        self._save()

    def count(self) -> int:
        return len(self._records)
