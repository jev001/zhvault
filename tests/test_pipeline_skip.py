from __future__ import annotations

from datetime import datetime
from pathlib import Path

from zhihu_backup.models import ItemRecord, NormalizedItem
from zhihu_backup.pipeline import Pipeline
from zhihu_backup.storage import open_engine
from zhihu_backup.writers.content import ContentWriter


def _item(modified: datetime | None = None) -> NormalizedItem:
    return NormalizedItem(
        item_type="answer",
        zhihu_id="42",
        url="https://www.zhihu.com/answer/42",
        title="t",
        modified=modified or datetime(2024, 1, 1, 12, 0, 0),
        owner_kind="collections",
        owner_id="c1",
        markdown_body="body",
    )


def test_should_skip_when_updated_at_unchanged(tmp_path: Path):
    meta = tmp_path / "meta"
    engine = open_engine("sqlite", meta)
    pipe = Pipeline(engine, tmp_path / "contents", tmp_path / "assets", full=False)
    item = _item()
    assert pipe.should_skip(item) is False
    engine.upsert_item(
        ItemRecord(
            key=item.key,
            item_type=item.item_type,
            zhihu_id=item.zhihu_id,
            content_updated_at=item.updated_at_str(),
        )
    )
    assert pipe.should_skip(item) is True
    pipe.full = True
    assert pipe.should_skip(item) is False
    engine.close()


def test_content_filename_has_no_chinese(tmp_path: Path):
    item = _item()
    item.title = "中文标题"
    path = ContentWriter(tmp_path / "contents").path_for(item)
    assert path.name == "answer_42.md"
    assert "中文" not in str(path)


def test_json_engine_roundtrip(tmp_path: Path):
    engine = open_engine("json", tmp_path / "meta")
    engine.set_cookie({"z_c0": "x"})
    assert engine.get_cookie()["z_c0"] == "x"
    from zhihu_backup.models import Checkpoint

    engine.set_checkpoint(Checkpoint(source="collection", source_id="1", offset=20))
    cp = engine.get_checkpoint("collection", "1")
    assert cp and cp.offset == 20
    summary = engine.status_summary()
    assert summary["engine"] == "json"
    assert summary["cookie_present"] is True
    engine.close()
