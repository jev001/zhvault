import importlib.util
from pathlib import Path

import pytest

from models import Checkpoint, GraphEdge, ItemRecord
from storage import normalize_engine_name, open_engine
from storage.rocks_engine import RocksEngine, rocksdict_available


def test_normalize_rocks_alias():
    assert normalize_engine_name("rocks") == "rocksdb"
    assert normalize_engine_name("ROCKSDB") == "rocksdb"
    assert normalize_engine_name("sqlite") == "sqlite"


def test_open_engine_rocks_uses_rocksdb_meta_dir(tmp_path: Path):
    if not rocksdict_available():
        pytest.skip("rocksdict not installed")
    eng = open_engine("rocks", tmp_path / "meta")
    try:
        assert (tmp_path / "meta" / "rocksdb" / "db").is_dir()
        assert eng.status_summary()["engine"] == "rocksdb"
        assert eng.status_summary()["backend"] == "rocksdict"
    finally:
        eng.close()


def test_open_engine_rocksdb_requires_extra(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "storage.rocks_engine.rocksdict_available",
        lambda: False,
    )
    with pytest.raises(RuntimeError, match="zhvault\\[rocksdb\\]"):
        open_engine("rocksdb", tmp_path / "meta")


@pytest.mark.rocksdb
@pytest.mark.skipif(not rocksdict_available(), reason="rocksdict not installed")
def test_rocks_engine_roundtrip(tmp_path: Path):
    eng = RocksEngine(tmp_path / "rocksdb")
    try:
        eng.set_cookie({"z_c0": "tok"})
        eng.set_checkpoint(Checkpoint(source="collection", source_id="1", offset=3))
        eng.upsert_item(ItemRecord(key="answer:1", item_type="answer", zhihu_id="1", title="t"))
        eng.link_membership("answer:1", "collections", "9")
        eng.set_asset_path("https://x/a.png", "assets/aa.png", source_url="https://x/a.png")
        eng.replace_item_assets("answer:1", ["https://x/a.png"])
        eng.upsert_graph_edge(
            GraphEdge(
                from_id="user:a",
                to_id="user:b",
                kind="follows",
                origin="manual",
                seen_at="2026-01-01T00:00:00Z",
            )
        )
        assert eng.get_cookie()["z_c0"] == "tok"
        assert eng.get_checkpoint("collection", "1").offset == 3
        assert eng.get_item("answer:1").title == "t"
        assert eng.list_membership()[0]["owner_id"] == "9"
        assert eng.get_asset_path("https://x/a.png") == "assets/aa.png"
        assert eng.list_item_assets("answer:1") == ["https://x/a.png"]
        assert eng.list_graph_edges()[0].origin == "manual"
        summary = eng.status_summary()
        assert summary["engine"] == "rocksdb"
        assert summary["items"] == 1
        assert summary["cookie_present"] is True
    finally:
        eng.close()


@pytest.mark.rocksdb
@pytest.mark.skipif(not rocksdict_available(), reason="rocksdict not installed")
def test_rocks_migrates_json_stub(tmp_path: Path):
    stub_dir = tmp_path / "rocksdb" / "rocks"
    stub_dir.mkdir(parents=True)
    (stub_dir / "state.json").write_text(
        '{"cookie":{"z_c0":"from-stub"},"checkpoints":{},"items":{"answer:9":'
        '{"key":"answer:9","item_type":"answer","zhihu_id":"9","title":"old"}},'
        '"membership":[],"assets":{},"item_assets":{},"failed_items":[],"graph_edges":{}}',
        encoding="utf-8",
    )
    eng = RocksEngine(tmp_path / "rocksdb")
    try:
        assert eng.get_cookie()["z_c0"] == "from-stub"
        assert eng.get_item("answer:9").title == "old"
        assert not (tmp_path / "rocksdb" / "db" / "state.json").exists()
    finally:
        eng.close()


def test_rocksdict_extra_listed():
    # Sanity: package name used in error / docs
    assert importlib.util.find_spec("storage.rocks_engine") is not None
