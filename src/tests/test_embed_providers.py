import sys

import pytest

from search.embed import (
    EmbedderError,
    HashEmbeddingProvider,
    open_embedder,
)


def test_open_embedder_hash():
    provider = open_embedder("hash")
    assert isinstance(provider, HashEmbeddingProvider)
    vecs = provider.embed(["hello"])
    assert len(vecs) == 1
    assert len(vecs[0]) == provider.dimensions == 32
    assert provider.model_id == "hash-v1"


def test_open_embedder_local_missing_package(monkeypatch):
    monkeypatch.setitem(sys.modules, "sentence_transformers", None)
    with pytest.raises(EmbedderError, match=r"zhvault\[search-ml\]"):
        open_embedder("local")


def test_open_embedder_http_mocked(monkeypatch):
    captured: dict = {}

    class _Resp:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "data": [
                    {"embedding": [0.1, 0.2]},
                    {"embedding": [0.3, 0.4]},
                ]
            }

    def fake_post(url, json=None, headers=None, **kwargs):
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers
        return _Resp()

    monkeypatch.setattr("requests.post", fake_post)
    provider = open_embedder(
        "http",
        model="text-embedding-3-small",
        api_base="https://api.example.com/v1/",
        api_key="test-key",
    )
    vecs = provider.embed(["hello", "world"])
    assert vecs == [[0.1, 0.2], [0.3, 0.4]]
    assert provider.dimensions == 2
    assert provider.model_id == "text-embedding-3-small"
    assert captured["url"] == "https://api.example.com/v1/embeddings"
    assert captured["json"] == {
        "model": "text-embedding-3-small",
        "input": ["hello", "world"],
    }
    assert captured["headers"]["Authorization"] == "Bearer test-key"


def test_open_embedder_unknown_name():
    with pytest.raises(EmbedderError, match="unknown"):
        open_embedder("nope")
