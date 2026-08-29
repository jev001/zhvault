from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from zhihu_backup.storage import open_engine
from zhihu_backup.writers.asset import AssetWriter


def _resp(content: bytes = b"img", content_type: str = "image/png") -> MagicMock:
    r = MagicMock()
    r.content = content
    r.headers = {"content-type": content_type}
    r.raise_for_status = MagicMock()
    return r


def test_localize_downloads_unique_urls(tmp_path: Path):
    engine = open_engine("sqlite", tmp_path / "meta")
    aw = AssetWriter(tmp_path / "assets", engine, workers=4)
    md_dir = tmp_path / "contents" / "collections" / "c1"
    md_dir.mkdir(parents=True)
    body = "\n".join(
        [
            "![a](https://cdn.example/a.png)",
            "![b](https://cdn.example/b.png)",
            "![c](https://cdn.example/c.png)",
        ]
    )
    with patch("zhihu_backup.writers.asset.requests.get", side_effect=lambda *a, **k: _resp()) as get:
        out = aw.localize_markdown(body, md_dir)
    assert get.call_count == 3
    assert "https://cdn.example/" not in out
    assert len(list((tmp_path / "assets").iterdir())) == 3
    engine.close()


def test_localize_dedupes_same_url(tmp_path: Path):
    engine = open_engine("sqlite", tmp_path / "meta")
    aw = AssetWriter(tmp_path / "assets", engine, workers=4)
    md_dir = tmp_path / "md"
    md_dir.mkdir()
    body = "![a](https://cdn.example/same.png)\n![b](https://cdn.example/same.png)"
    with patch("zhihu_backup.writers.asset.requests.get", return_value=_resp()) as get:
        out = aw.localize_markdown(body, md_dir)
    assert get.call_count == 1
    assert out.count("https://cdn.example/same.png") == 0
    engine.close()


def test_localize_keeps_url_on_download_failure(tmp_path: Path):
    engine = open_engine("sqlite", tmp_path / "meta")
    aw = AssetWriter(tmp_path / "assets", engine, workers=4)
    md_dir = tmp_path / "md"
    md_dir.mkdir()
    body = "![ok](https://cdn.example/ok.png)\n![bad](https://cdn.example/bad.png)"

    def fake_get(url, **kwargs):
        if "bad" in url:
            raise RuntimeError("boom")
        return _resp()

    with patch("zhihu_backup.writers.asset.requests.get", side_effect=fake_get):
        out = aw.localize_markdown(body, md_dir)
    assert "https://cdn.example/bad.png" in out
    assert "https://cdn.example/ok.png" not in out
    engine.close()


def test_localize_skips_cached_asset(tmp_path: Path):
    engine = open_engine("sqlite", tmp_path / "meta")
    assets = tmp_path / "assets"
    assets.mkdir()
    cached = assets / "cached0123456789.png"
    cached.write_bytes(b"x")
    url = "https://cdn.example/cached.png"
    engine.set_asset_path(url, str(cached))
    aw = AssetWriter(assets, engine, workers=4)
    md_dir = tmp_path / "md"
    md_dir.mkdir()
    with patch("zhihu_backup.writers.asset.requests.get") as get:
        out = aw.localize_markdown(f"![c]({url})", md_dir)
    get.assert_not_called()
    assert "cached0123456789.png" in out
    engine.close()
