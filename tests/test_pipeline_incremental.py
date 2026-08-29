from __future__ import annotations

from datetime import datetime
from pathlib import Path

from zhihu_backup.models import ItemRecord, NormalizedItem
from zhihu_backup.pipeline import Pipeline
from zhihu_backup.storage import open_engine


def _item(zhihu_id: str, modified: datetime, parent_id: str | None = "99") -> NormalizedItem:
    return NormalizedItem(
        item_type="answer",
        zhihu_id=zhihu_id,
        url=f"https://www.zhihu.com/answer/{zhihu_id}",
        title=f"t-{zhihu_id}",
        modified=modified,
        markdown_body="hello",
        owner_kind="collections",
        owner_id="c1",
        sources=["collection:c1"],
        parent_id=parent_id,
    )


def test_should_skip_when_updated_at_unchanged(tmp_path: Path) -> None:
    engine = open_engine("sqlite", tmp_path / "meta")
    pipe = Pipeline(engine, tmp_path / "contents", tmp_path / "assets")
    modified = datetime(2024, 5, 1, 12, 0, 0)
    item = _item("42", modified)
    engine.upsert_item(
        ItemRecord(
            key=item.key,
            item_type="answer",
            zhihu_id="42",
            content_updated_at=item.updated_at_str(),
            path="x.md",
        )
    )
    assert pipe.should_skip(item) is True
    engine.close()


def test_should_not_skip_when_full(tmp_path: Path) -> None:
    engine = open_engine("sqlite", tmp_path / "meta")
    pipe = Pipeline(engine, tmp_path / "contents", tmp_path / "assets", full=True)
    modified = datetime(2024, 5, 1, 12, 0, 0)
    item = _item("42", modified)
    engine.upsert_item(
        ItemRecord(
            key=item.key,
            item_type="answer",
            zhihu_id="42",
            content_updated_at=item.updated_at_str(),
        )
    )
    assert pipe.should_skip(item) is False
    engine.close()


def test_content_writer_filename_no_chinese(tmp_path: Path) -> None:
    from zhihu_backup.writers.content import ContentWriter

    writer = ContentWriter(tmp_path / "contents")
    item = _item("99", datetime(2024, 1, 1), parent_id="123")
    item.title = "中文标题不应进路径"
    path = writer.write(item, "body")
    assert path.name == "answer_123_99.md"
    assert item.key == "answer:123:99"
    assert "中文" not in str(path)
