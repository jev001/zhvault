from __future__ import annotations

from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

from models import NormalizedItem
from pipeline import Pipeline
from sources.base import Source
from storage import open_engine
from writers.asset import AssetWriter, normalize_asset_url


class _FakeSource(Source):
    name = "collection"

    def __init__(self):
        self.source_id = "c1"

    def total(self):
        return 0

    def iter_items(self, offset: int = 0, limit: int = 20):
        yield from ()


def test_normalize_strips_720w():
    src = "https://pic1.zhimg.com/v2-abcdef_720w.jpg"
    assert normalize_asset_url(src) == "https://pic1.zhimg.com/v2-abcdef.jpg"


def test_normalize_leaves_non_zhimg():
    src = "https://cdn.example/a_720w.png"
    assert normalize_asset_url(src) == src


def test_localize_wikilink_and_frontmatter(tmp_path: Path):
    engine = open_engine("sqlite", tmp_path / "meta")
    writer = AssetWriter(tmp_path / "assets", engine, asset_link="wikilink")
    source = "https://pic2.zhimg.com/v2-deadbeef_720w.jpg"
    origin = "https://pic2.zhimg.com/v2-deadbeef.jpg"
    calls: list[str] = []

    def fake_get(url, timeout=15):
        calls.append(url)
        resp = MagicMock()
        resp.content = b"IMG"
        resp.headers = {"content-type": "image/jpeg"}
        resp.raise_for_status = MagicMock()
        if url == origin:
            return resp
        raise AssertionError(f"unexpected url {url}")

    md_dir = tmp_path / "contents" / "collections" / "c1"
    md_dir.mkdir(parents=True)
    with patch("writers.asset.requests.get", side_effect=fake_get):
        body, urls, refs = writer.localize_markdown(f"![x]({source})", md_dir)
    assert calls == [origin]
    assert urls == [origin]
    assert "asset-source:" in body and source in body
    assert "asset-origin:" in body and origin in body
    assert "![[assets/" in body
    assert refs[0].source == source
    assert refs[0].origin == origin
    meta = engine.get_asset_meta(origin)
    assert meta.get("source_url") == source
    assert meta.get("origin_url") == origin
    engine.close()


def test_localize_falls_back_to_source(tmp_path: Path):
    engine = open_engine("sqlite", tmp_path / "meta")
    writer = AssetWriter(tmp_path / "assets", engine)
    source = "https://pic1.zhimg.com/v2-fb_720w.jpg"
    origin = normalize_asset_url(source)

    def download_side_effect(url, timeout=15):
        if url == origin:
            raise ConnectionError("fail")
        resp = MagicMock()
        resp.content = b"IMG"
        resp.headers = {"content-type": "image/jpeg"}
        resp.raise_for_status = MagicMock()
        return resp

    md_dir = tmp_path / "md"
    md_dir.mkdir()
    with patch("writers.asset.requests.get", side_effect=download_side_effect):
        body, urls, refs = writer.localize_markdown(f"![x]({source})", md_dir)
    assert refs[0].origin == origin
    assert refs[0].source == source
    assert urls == [origin]
    assert "![[" in body
    engine.close()


def test_pipeline_frontmatter_assets_list(tmp_path: Path):
    engine = open_engine("sqlite", tmp_path / "meta")
    pipe = Pipeline(
        engine, tmp_path / "contents", tmp_path / "assets", full=True, asset_link="wikilink"
    )
    item = NormalizedItem(
        item_type="answer",
        zhihu_id="456",
        url="https://www.zhihu.com/answer/456",
        title="t",
        modified=datetime(2024, 1, 1, 12, 0, 0),
        owner_kind="collections",
        owner_id="c1",
        markdown_body="![a](https://pic1.zhimg.com/v2-abc_720w.jpg)",
        parent_id="123",
    )
    resp = MagicMock()
    resp.content = b"img"
    resp.headers = {"content-type": "image/jpeg"}
    resp.raise_for_status = MagicMock()
    with patch("writers.asset.requests.get", return_value=resp):
        action = pipe.process_item(item, source=_FakeSource())
    assert action == "created"
    text = Path(engine.get_item(item.key).path).read_text(encoding="utf-8")
    assert "assets:" in text
    assert "origin:" in text
    assert "source:" in text
    assert "![[assets/" in text
    engine.close()


def test_asset_link_rel(tmp_path: Path):
    engine = open_engine("json", tmp_path / "meta")
    writer = AssetWriter(tmp_path / "assets", engine, asset_link="rel")
    resp = MagicMock()
    resp.content = b"x"
    resp.headers = {"content-type": "image/png"}
    resp.raise_for_status = MagicMock()
    md_dir = tmp_path / "contents" / "c"
    md_dir.mkdir(parents=True)
    with patch("writers.asset.requests.get", return_value=resp):
        body, _, _ = writer.localize_markdown("![a](https://cdn.example/a.png)", md_dir)
    assert "![](" in body or "![a](" in body
    assert "![[" not in body
    engine.close()
