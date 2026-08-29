from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator

from models import NormalizedItem


class Source(ABC):
    name: str
    source_id: str

    @abstractmethod
    def total(self) -> int | None:
        ...

    @abstractmethod
    def iter_items(self, offset: int = 0, limit: int = 20) -> Iterator[tuple[int, list[NormalizedItem]]]:
        """Yield (next_offset, page_items). next_offset is the offset after this page."""
        ...
