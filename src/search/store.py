from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Protocol

from search.types import VectorHit, VectorRecord


class VectorBackendError(Exception):
    """Raised when a vector backend cannot be opened (missing extra, etc.)."""


class VectorStore(Protocol):
    name: str

    def upsert(self, records: Sequence[VectorRecord]) -> None:
        """Idempotent upsert by record.id."""

    def delete(self, ids: Sequence[str]) -> None: ...

    def query(
        self,
        vector: Sequence[float],
        *,
        top_k: int = 10,
        where: Mapping[str, Any] | None = None,
    ) -> list[VectorHit]:
        """Nearest neighbors; where filters metadata (equality on keys)."""

    def clear(self) -> None: ...

    def count(self) -> int: ...


_BACKENDS = ("memory", "chroma")


def open_vector_store(backend: str, root: Path) -> VectorStore:
    if backend == "memory":
        from search.memory_store import MemoryVectorStore

        return MemoryVectorStore(persist_path=Path(root) / "memory.json")
    if backend == "chroma":
        try:
            import chromadb  # noqa: F401
        except ImportError as exc:
            raise VectorBackendError(
                "chroma backend requires chromadb. "
                "Install with: pip install 'zhvault[chroma]'"
            ) from exc
        from search.chroma_store import ChromaVectorStore

        return ChromaVectorStore(root)
    raise ValueError(
        f"unknown vector backend {backend!r}; installed backends: {', '.join(_BACKENDS)}"
    )
