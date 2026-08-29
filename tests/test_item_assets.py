from __future__ import annotations

from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

from models import NormalizedItem
from pipeline import Pipeline
from sources.base import Source
from storage import open_engine


class _FakeSource(Source):
    name = "collection"

    def __init__(self):
        self.source_id = "c1"

    def total(self):
        return 0

    def iter_items(self, offset: int = 0, limit: int = 20):
        yield from ()


def test_sqlite_replace_list_item_assets(tmp_path: Path):
    engine = open_engine("sqlite", tmp_path / "meta")
    engine.replace_item_assets("answer:1:2", ["https://a.png", "https://b.png"])
    assert engine.list_item_assets("answer:1:2") == ["https://a.png", "https://b.png"]
    engine.replace_item_assets("answer:1:2", ["https://c.png"])
    assert engine.list_item_assets("answer:1:2") == ["https://c.png"]
    engine.close()


def test_json_replace_list_item_assets(tmp_path: Path):
    engine = open_engine("json", tmp_path / "meta")
    engine.replace_item_assets("pin:9", ["https://x.png", "https://x.png", "https://y.png"])
    assert engine.list_item_assets("pin:9") == ["https://x.png", "https://y.png"]
    engine.close()


def test_pipeline_links_item_assets_and_business_extra(tmp_path: Path):
    engine = open_engine("sqlite", tmp_path / "meta")
    pipe = Pipeline(engine, tmp_path / "contents", tmp_path / "assets", full=True)
    item = NormalizedItem(
        item_type="answer",
        zhihu_id="456",
        url="https://www.zhihu.com/answer/456",
        title="t",
        modified=datetime(2024, 1, 1, 12, 0, 0),
        owner_kind="collections",
        owner_id="c1",
        markdown_body="![a](https://cdn.example/a.png)",
        parent_id="123",
    )
    resp = MagicMock()
    resp.content = b"img"
    resp.headers = {"content-type": "image/png"}
    resp.raise_for_status = MagicMock()
    with patch("writers.asset.requests.get", return_value=resp):
        action = pipe.process_item(item, source=_FakeSource())
    assert action == "created"
    rec = engine.get_item(item.key)
    assert rec is not None
    assert rec.extra.get("answer_id") == "456"
    assert rec.extra.get("question_id") == "123"
    assert engine.list_item_assets(item.key) == ["https://cdn.example/a.png"]
    text = Path(rec.path).read_text(encoding="utf-8")
    assert "answer_id: '456'" in text or "answer_id: 456" in text
    assert "question_id:" in text
    engine.close()
