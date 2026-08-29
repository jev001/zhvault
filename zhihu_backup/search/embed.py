import hashlib
import struct
from typing import Protocol, Sequence


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
