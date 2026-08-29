import math
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

    def __init__(self) -> None:
        self._records: dict[str, VectorRecord] = {}

    def upsert(self, records: Sequence[VectorRecord]) -> None:
        for record in records:
            self._records[record.id] = record

    def delete(self, ids: Sequence[str]) -> None:
        for rid in ids:
            self._records.pop(rid, None)

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
