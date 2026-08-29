import json
from pathlib import Path

from zhihu_backup.models import ItemRecord
from zhihu_backup.search.embed import HashEmbeddingProvider
from zhihu_backup.search.memory_store import MemoryVectorStore
from zhihu_backup.search.types import VectorRecord
from zhihu_backup.storage.sqlite_engine import SqliteEngine


def test_chunk_markdown_splits_long_text():
    from zhihu_backup.search.chunk import chunk_markdown

    short = "hello"
    assert chunk_markdown(short, max_chars=1200) == ["hello"]

    text = "word " * 400  # ~2000 chars
    chunks = chunk_markdown(text, max_chars=1200, overlap=100)
    assert len(chunks) >= 2
    assert all(len(c) <= 1200 for c in chunks)
    assert "".join(chunks).replace(" ", "")  # non-empty pieces


def test_build_index_writes_manifest_and_is_idempotent(tmp_path: Path):
    from zhihu_backup.search.index import build_index

    contents = tmp_path / "contents"
    rel = "collections/me/answer_1_2.md"
    md_path = contents / rel
    md_path.parent.mkdir(parents=True)
    md_path.write_text(
        "---\ntitle: Fixture\n---\n\n# Heading\n\n" + ("lorem ipsum " * 150),
        encoding="utf-8",
    )

    engine = SqliteEngine(tmp_path / "state.sqlite")
    engine.upsert_item(
        ItemRecord(
            key="answer:1:2",
            item_type="answer",
            zhihu_id="2",
            title="Fixture",
            path=rel,
        )
    )
    engine.upsert_item(
        ItemRecord(key="question:1", item_type="question", zhihu_id="1", title="No path")
    )

    vectors = tmp_path / "vectors"
    store = MemoryVectorStore()
    embedder = HashEmbeddingProvider()
    stats = build_index(engine, contents, vectors, store=store, embedder=embedder)

    manifest_path = vectors / "manifest.json"
    assert manifest_path.is_file()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["model_id"] == "hash-v1"
    assert manifest["dimensions"] == 32
    assert manifest["backend"] == "memory"
    assert manifest["chunks"] >= 1
    assert manifest["updated_at"]
    assert stats["chunks"] == manifest["chunks"]

    hits = store.query(embedder.embed(["lorem ipsum"])[0], top_k=5)
    assert hits
    assert hits[0].id.startswith("answer:1:2#")
    assert hits[0].metadata["item_key"] == "answer:1:2"
    assert hits[0].metadata["item_type"] == "answer"
    assert hits[0].metadata["chunk_index"] == 0

    stats2 = build_index(engine, contents, vectors, store=store, embedder=embedder)
    assert stats2["chunks"] == stats["chunks"]
    engine.close()


def test_build_index_model_mismatch_clears_then_reindexes(tmp_path: Path):
    from zhihu_backup.search.index import build_index

    contents = tmp_path / "contents"
    rel = "pins/me/pin_9.md"
    md_path = contents / rel
    md_path.parent.mkdir(parents=True)
    md_path.write_text(
        "fresh body for reindex\n\n" + ("padding text " * 20),
        encoding="utf-8",
    )

    engine = SqliteEngine(tmp_path / "state.sqlite")
    engine.upsert_item(
        ItemRecord(key="pin:9", item_type="pin", zhihu_id="9", title="P", path=rel)
    )

    vectors = tmp_path / "vectors"
    vectors.mkdir()
    (vectors / "manifest.json").write_text(
        json.dumps(
            {
                "model_id": "old-model",
                "dimensions": 8,
                "backend": "memory",
                "updated_at": "2020-01-01T00:00:00Z",
                "chunks": 1,
            }
        ),
        encoding="utf-8",
    )

    store = MemoryVectorStore()
    store.upsert(
        [VectorRecord(id="stale#0", vector=[0.0] * 32, document="stale")]
    )
    embedder = HashEmbeddingProvider()
    stats = build_index(engine, contents, vectors, store=store, embedder=embedder)

    hits = store.query(embedder.embed(["fresh body"])[0], top_k=20)
    assert all(h.id != "stale#0" for h in hits)
    assert any(h.id.startswith("pin:9#") for h in hits)
    manifest = json.loads((vectors / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["model_id"] == "hash-v1"
    assert manifest["dimensions"] == 32
    assert manifest["chunks"] == stats["chunks"]
    engine.close()


def test_build_index_purges_stale_chunks_when_item_removed(tmp_path: Path):
    from zhihu_backup.search.index import build_index

    contents = tmp_path / "contents"
    rel_keep = "collections/me/answer_1_2.md"
    rel_drop = "collections/me/answer_3_4.md"
    for rel in (rel_keep, rel_drop):
        md_path = contents / rel
        md_path.parent.mkdir(parents=True, exist_ok=True)
        md_path.write_text(
            f"---\ntitle: {rel}\n---\n\n# Heading\n\n" + ("lorem ipsum " * 150),
            encoding="utf-8",
        )

    engine = SqliteEngine(tmp_path / "state.sqlite")
    engine.upsert_item(
        ItemRecord(key="answer:1:2", item_type="answer", zhihu_id="2", title="Keep", path=rel_keep)
    )
    engine.upsert_item(
        ItemRecord(key="answer:3:4", item_type="answer", zhihu_id="4", title="Drop", path=rel_drop)
    )

    vectors = tmp_path / "vectors"
    store = MemoryVectorStore()
    embedder = HashEmbeddingProvider()
    build_index(engine, contents, vectors, store=store, embedder=embedder)
    assert any(h.metadata.get("item_key") == "answer:3:4" for h in store.query(embedder.embed(["lorem"])[0], top_k=50))

    engine.upsert_item(
        ItemRecord(key="answer:3:4", item_type="answer", zhihu_id="4", title="Drop", path=None)
    )
    build_index(engine, contents, vectors, store=store, embedder=embedder)

    hits = store.query(embedder.embed(["lorem"])[0], top_k=50)
    item_keys = {h.metadata.get("item_key") for h in hits}
    assert "answer:3:4" not in item_keys
    assert "answer:1:2" in item_keys
    engine.close()


def test_build_index_purges_stale_chunks_when_fewer_chunks(tmp_path: Path):
    from zhihu_backup.search.index import build_index

    contents = tmp_path / "contents"
    rel = "collections/me/answer_1_2.md"
    md_path = contents / rel
    md_path.parent.mkdir(parents=True)
    long_body = "# Heading\n\n" + ("word " * 400)
    md_path.write_text(f"---\ntitle: Fixture\n---\n\n{long_body}", encoding="utf-8")

    engine = SqliteEngine(tmp_path / "state.sqlite")
    engine.upsert_item(
        ItemRecord(key="answer:1:2", item_type="answer", zhihu_id="2", title="Fixture", path=rel)
    )

    vectors = tmp_path / "vectors"
    store = MemoryVectorStore()
    embedder = HashEmbeddingProvider()
    stats1 = build_index(engine, contents, vectors, store=store, embedder=embedder)
    assert stats1["chunks"] >= 2
    assert any(h.id.startswith("answer:1:2#1") for h in store.query(embedder.embed(["word"])[0], top_k=50))

    short_body = "# Heading\n\n" + ("word " * 30)
    md_path.write_text(f"---\ntitle: Fixture\n---\n\n{short_body}", encoding="utf-8")
    stats2 = build_index(engine, contents, vectors, store=store, embedder=embedder)
    assert stats2["chunks"] == 1

    hits = store.query(embedder.embed(["word"])[0], top_k=50)
    assert all(not h.id.startswith("answer:1:2#1") for h in hits)
    assert hits[0].id == "answer:1:2#0"
    engine.close()
