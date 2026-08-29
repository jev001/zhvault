import hashlib
import os
import struct
from collections.abc import Sequence
from typing import Protocol

DEFAULT_LOCAL_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


class EmbedderError(RuntimeError):
    """Raised when an embedder cannot be opened or used."""


class EmbeddingProvider(Protocol):
    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...

    @property
    def dimensions(self) -> int: ...

    @property
    def model_id(self) -> str: ...


def _hash_text(text: str, dimensions: int) -> list[float]:
    out: list[float] = []
    for i in range(dimensions):
        digest = hashlib.sha256(f"{text}:{i}".encode()).digest()
        val = struct.unpack(">I", digest[:4])[0] / (2**32 - 1) * 2.0 - 1.0
        out.append(val)
    return out


class HashEmbeddingProvider:
    model_id = "hash-v1"
    dimensions = 32

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [_hash_text(text, self.dimensions) for text in texts]


class LocalEmbeddingProvider:
    def __init__(self, model: str | None = None) -> None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise EmbedderError(
                "local embedder requires sentence-transformers. "
                "Install with: pip install 'zhvault[search-ml]'"
            ) from exc
        self.model_id = model or DEFAULT_LOCAL_MODEL
        self._model = SentenceTransformer(self.model_id)
        dim = getattr(self._model, "get_sentence_embedding_dimension", None)
        self._dimensions = dim() if callable(dim) else None

    @property
    def dimensions(self) -> int:
        if self._dimensions is None:
            raise EmbedderError("dimensions unknown until first embed")
        return self._dimensions

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        vectors = [list(map(float, vec)) for vec in self._model.encode(list(texts))]
        if vectors and self._dimensions is None:
            self._dimensions = len(vectors[0])
        return vectors


class HttpEmbeddingProvider:
    def __init__(
        self,
        *,
        model: str,
        api_base: str,
        api_key: str | None = None,
    ) -> None:
        self.model_id = model
        self._api_base = api_base.rstrip("/")
        self._api_key = api_key or os.environ.get("ZHIHU_EMBED_API_KEY")
        self._dimensions: int | None = None

    @property
    def dimensions(self) -> int:
        if self._dimensions is None:
            raise EmbedderError("dimensions unknown until first embed")
        return self._dimensions

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        import requests

        headers = {}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        resp = requests.post(
            f"{self._api_base}/embeddings",
            json={"model": self.model_id, "input": list(texts)},
            headers=headers,
        )
        resp.raise_for_status()
        vectors = [list(map(float, row["embedding"])) for row in resp.json()["data"]]
        if vectors:
            self._dimensions = len(vectors[0])
        return vectors


def open_embedder(
    name: str,
    *,
    model: str | None = None,
    api_base: str | None = None,
    api_key: str | None = None,
) -> EmbeddingProvider:
    if name == "hash":
        return HashEmbeddingProvider()
    if name == "local":
        return LocalEmbeddingProvider(model)
    if name == "http":
        if not model or not api_base:
            raise EmbedderError("http embedder requires model and api_base")
        return HttpEmbeddingProvider(model=model, api_base=api_base, api_key=api_key)
    raise EmbedderError(f"unknown embedder {name!r}")
