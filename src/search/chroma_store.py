from pathlib import Path
from typing import Any, Mapping, Sequence

from search.types import VectorHit, VectorRecord

_COLLECTION = "zhihu_chunks"


class ChromaVectorStore:
    name = "chroma"

    def __init__(self, root: Path) -> None:
        import chromadb

        persist_directory = str(root / "chroma")
        self._client = chromadb.PersistentClient(path=persist_directory)
        self._collection = self._client.get_or_create_collection(name=_COLLECTION)

    def upsert(self, records: Sequence[VectorRecord]) -> None:
        if not records:
            return
        self._collection.upsert(
            ids=[record.id for record in records],
            embeddings=[list(record.vector) for record in records],
            documents=[record.document for record in records],
            # ponytail: chroma rejects empty metadata; dummy key stripped on query
            metadatas=[dict(record.metadata) or {"_": True} for record in records],
        )

    def delete(self, ids: Sequence[str]) -> None:
        if not ids:
            return
        self._collection.delete(ids=list(ids))

    def query(
        self,
        vector: Sequence[float],
        *,
        top_k: int = 10,
        where: Mapping[str, Any] | None = None,
    ) -> list[VectorHit]:
        count = self._collection.count()
        if count == 0 or top_k <= 0:
            return []
        kwargs: dict[str, Any] = {
            "query_embeddings": [list(vector)],
            "n_results": min(top_k, count),
        }
        if where:
            kwargs["where"] = {k: {"$eq": v} for k, v in where.items()}
        result = self._collection.query(**kwargs)
        ids = (result.get("ids") or [[]])[0]
        distances = (result.get("distances") or [[]])[0]
        documents = (result.get("documents") or [[]])[0]
        metadatas = (result.get("metadatas") or [[]])[0]
        hits: list[VectorHit] = []
        for i, rid in enumerate(ids):
            dist = float(distances[i]) if i < len(distances) else 0.0
            raw_doc = documents[i] if i < len(documents) else ""
            raw_meta = metadatas[i] if i < len(metadatas) else None
            meta = dict(raw_meta or {})
            meta.pop("_", None)
            hits.append(
                VectorHit(
                    id=rid,
                    score=1.0 - dist,
                    document=raw_doc or "",
                    metadata=meta,
                )
            )
        return hits

    def clear(self) -> None:
        self._client.delete_collection(_COLLECTION)
        self._collection = self._client.get_or_create_collection(name=_COLLECTION)

    def count(self) -> int:
        return self._collection.count()
