from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional

from zhihu_backup.models import Checkpoint, ItemRecord


class StorageEngine(ABC):
    @abstractmethod
    def get_cookie(self) -> dict[str, str]:
        ...

    @abstractmethod
    def set_cookie(self, cookies: dict[str, str]) -> None:
        ...

    @abstractmethod
    def get_checkpoint(self, source: str, source_id: str) -> Optional[Checkpoint]:
        ...

    @abstractmethod
    def set_checkpoint(self, checkpoint: Checkpoint) -> None:
        ...

    @abstractmethod
    def get_item(self, key: str) -> Optional[ItemRecord]:
        ...

    @abstractmethod
    def upsert_item(self, record: ItemRecord) -> None:
        ...

    @abstractmethod
    def link_membership(self, key: str, owner_kind: str, owner_id: str) -> None:
        ...

    @abstractmethod
    def get_asset_path(self, url: str) -> Optional[str]:
        ...

    @abstractmethod
    def set_asset_path(self, url: str, path: str) -> None:
        ...

    @abstractmethod
    def replace_item_assets(self, item_key: str, asset_urls: list[str]) -> None:
        ...

    @abstractmethod
    def list_item_assets(self, item_key: str) -> list[str]:
        ...

    @abstractmethod
    def record_failed(self, key: str, source: str, source_id: str, error: str) -> None:
        ...

    @abstractmethod
    def status_summary(self) -> dict[str, Any]:
        ...

    def close(self) -> None:
        return None
