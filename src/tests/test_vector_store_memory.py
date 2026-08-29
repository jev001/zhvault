from pathlib import Path

import pytest

from search.embed import HashEmbeddingProvider
from search.memory_store import MemoryVectorStore
from search.store import open_vector_store
from search.types import VectorRecord


def test_memory_upsert_query_nearest():
    store = MemoryVectorStore()
    v_near = [1.0, 0.0, 0.0]
    v_far = [0.0, 1.0, 0.0]
    store.upsert(
        [
            VectorRecord(id="near", vector=v_near, document="near doc"),
            VectorRecord(id="far", vector=v_far, document="far doc"),
        ]
    )
    hits = store.query(v_near, top_k=2)
    assert len(hits) == 2
    assert hits[0].id == "near"
    assert hits[0].score > hits[1].score
    assert hits[0].document == "near doc"


def test_memory_query_where_metadata():
    store = MemoryVectorStore()
    store.upsert(
        [
            VectorRecord(
                id="a",
                vector=[1.0, 0.0],
                metadata={"item_type": "answer"},
            ),
            VectorRecord(
                id="b",
                vector=[0.9, 0.1],
                metadata={"item_type": "question"},
            ),
        ]
    )
    hits = store.query([1.0, 0.0], top_k=10, where={"item_type": "question"})
    assert len(hits) == 1
    assert hits[0].id == "b"


def test_memory_delete_and_clear():
    store = MemoryVectorStore()
    v = [1.0, 0.0]
    store.upsert([VectorRecord(id="x", vector=v), VectorRecord(id="y", vector=[0.0, 1.0])])
    store.delete(["x"])
    hits = store.query(v, top_k=10)
    assert [h.id for h in hits] == ["y"]
    store.clear()
    assert store.query(v, top_k=10) == []


def test_memory_upsert_idempotent():
    store = MemoryVectorStore()
    v1 = [1.0, 0.0]
    v2 = [0.0, 1.0]
    store.upsert([VectorRecord(id="same", vector=v1, document="first")])
    store.upsert([VectorRecord(id="same", vector=v2, document="second")])
    hits = store.query(v2, top_k=1)
    assert hits[0].id == "same"
    assert hits[0].document == "second"


def test_open_vector_store_memory(tmp_path: Path):
    store = open_vector_store("memory", tmp_path)
    assert store.name == "memory"
    assert isinstance(store, MemoryVectorStore)


def test_open_vector_store_unknown_backend(tmp_path: Path):
    with pytest.raises(ValueError, match="memory"):
        open_vector_store("nope", tmp_path)


def test_hash_embedding_provider_deterministic():
    provider = HashEmbeddingProvider()
    assert provider.model_id == "hash-v1"
    assert provider.dimensions == 32
    a = provider.embed(["hello world"])[0]
    b = provider.embed(["hello world"])[0]
    c = provider.embed(["other text"])[0]
    assert a == b
    assert a != c
    assert len(a) == 32
