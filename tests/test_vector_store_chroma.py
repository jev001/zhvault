import importlib.util
import sys
from pathlib import Path

import pytest

from search.store import VectorBackendError, open_vector_store
from search.types import VectorRecord


def test_open_chroma_missing_package_install_hint(monkeypatch, tmp_path: Path):
    monkeypatch.setitem(sys.modules, "chromadb", None)
    with pytest.raises(VectorBackendError, match=r"pip install") as excinfo:
        open_vector_store("chroma", tmp_path)
    assert "zhvault[chroma]" in str(excinfo.value)


@pytest.mark.chroma
@pytest.mark.skipif(
    importlib.util.find_spec("chromadb") is None,
    reason="chromadb not installed",
)
def test_chroma_upsert_query_round_trip(tmp_path: Path):
    store = open_vector_store("chroma", tmp_path)
    assert store.name == "chroma"
    v_near = [1.0, 0.0, 0.0]
    v_far = [0.0, 1.0, 0.0]
    store.upsert(
        [
            VectorRecord(id="near", vector=v_near, document="near doc"),
            VectorRecord(id="far", vector=v_far, document="far doc"),
        ]
    )
    hits = store.query(v_near, top_k=1)
    assert len(hits) == 1
    assert hits[0].id == "near"
    assert hits[0].document == "near doc"
    assert (tmp_path / "chroma").exists()
