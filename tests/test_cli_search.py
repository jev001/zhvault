import json
from pathlib import Path

from cli import build_parser, main, resolve_embed_provider
from models import GraphEdge, ItemRecord
from storage import open_engine

PHRASE = "zebra quaternion backup fixture"
HASH_FLAGS = ["--embed-provider", "hash"]


def _seed_item(tmp_path: Path, *, with_edge: bool = False) -> None:
    contents = tmp_path / "contents"
    rel = "collections/me/answer_1_2.md"
    md_path = contents / rel
    md_path.parent.mkdir(parents=True)
    md_path.write_text(
        f"---\ntitle: Fixture\n---\n\n# Heading\n\n{PHRASE} and some more text.\n\n"
        + ("padding for index threshold " * 3),
        encoding="utf-8",
    )
    eng = open_engine("sqlite", tmp_path / "meta")
    try:
        eng.upsert_item(
            ItemRecord(
                key="answer:1:2",
                item_type="answer",
                zhihu_id="2",
                title="Fixture",
                path=rel,
            )
        )
        if with_edge:
            eng.upsert_graph_edge(
                GraphEdge(
                    from_id="answer:1:2",
                    to_id="user:alice",
                    kind="follows",
                    origin="manual",
                    seen_at="2026-01-01T00:00:00Z",
                )
            )
    finally:
        eng.close()


def test_parser_search_index():
    p = build_parser()
    args = p.parse_args(["search", "index", "--vector-backend", "memory", *HASH_FLAGS])
    assert args.func.__name__ == "cmd_search_index"
    assert args.vector_backend == "memory"
    assert args.embed_provider == "hash"


def test_parser_search_semantic():
    p = build_parser()
    args = p.parse_args(
        [
            "search",
            "semantic",
            "hello world",
            "--top-k",
            "5",
            "--vector-backend",
            "memory",
            *HASH_FLAGS,
            "--expand-graph",
            "2",
            "--kind",
            "follows",
        ]
    )
    assert args.func.__name__ == "cmd_search_semantic"
    assert args.query == "hello world"
    assert args.top_k == 5
    assert args.vector_backend == "memory"
    assert args.embed_provider == "hash"
    assert args.expand_graph == 2
    assert args.kind == ["follows"]


def test_resolve_embed_provider_explicit():
    assert resolve_embed_provider("hash") == "hash"
    assert resolve_embed_provider("http") == "http"


def test_search_index_cli_json(tmp_path, capsys):
    _seed_item(tmp_path)
    rc = main(
        [
            "search",
            "index",
            "--vector-backend",
            "memory",
            *HASH_FLAGS,
            "--json",
            "--data-dir",
            str(tmp_path),
        ]
    )
    assert rc == 0
    out = json.loads(capsys.readouterr().out.strip())
    assert out["event"] == "summary"
    assert out["backend"] == "memory"
    assert out["chunks"] >= 1
    assert out["items"] >= 1
    manifest = tmp_path / "meta" / "sqlite" / "vectors" / "manifest.json"
    assert manifest.is_file()
    data = json.loads(manifest.read_text(encoding="utf-8"))
    assert data["backend"] == "memory"
    assert data["chunks"] == out["chunks"]


def test_search_semantic_cli_json(tmp_path, capsys):
    _seed_item(tmp_path)
    rc = main(
        [
            "search",
            "index",
            "--vector-backend",
            "memory",
            *HASH_FLAGS,
            "--json",
            "--data-dir",
            str(tmp_path),
        ]
    )
    assert rc == 0
    capsys.readouterr()
    rc = main(
        [
            "search",
            "semantic",
            PHRASE,
            "--vector-backend",
            "memory",
            *HASH_FLAGS,
            "--top-k",
            "5",
            "--json",
            "--data-dir",
            str(tmp_path),
        ]
    )
    assert rc == 0
    out = json.loads(capsys.readouterr().out.strip())
    hits = out["hits"] if isinstance(out, dict) else out
    assert hits
    assert hits[0]["item_key"] == "answer:1:2"
    assert "score" in hits[0]
    assert "neighbors" not in hits[0]


def test_search_semantic_expand_graph(tmp_path, capsys):
    _seed_item(tmp_path, with_edge=True)
    rc = main(
        [
            "search",
            "index",
            "--vector-backend",
            "memory",
            *HASH_FLAGS,
            "--json",
            "--data-dir",
            str(tmp_path),
        ]
    )
    assert rc == 0
    capsys.readouterr()
    rc = main(
        [
            "search",
            "semantic",
            PHRASE,
            "--vector-backend",
            "memory",
            *HASH_FLAGS,
            "--expand-graph",
            "1",
            "--kind",
            "follows",
            "--json",
            "--data-dir",
            str(tmp_path),
        ]
    )
    assert rc == 0
    out = json.loads(capsys.readouterr().out.strip())
    hits = out["hits"] if isinstance(out, dict) else out
    assert hits
    neighbors = hits[0]["neighbors"]
    ids = {n["id"] if isinstance(n, dict) else n for n in neighbors}
    assert "user:alice" in ids


def test_search_index_fails_without_embed_provider_when_st_missing(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr("cli.common.sentence_transformers_importable", lambda: False)
    monkeypatch.setattr("cli.common.chroma_importable", lambda: True)
    rc = main(["search", "index", "--vector-backend", "memory", "--json", "--data-dir", str(tmp_path)])
    assert rc != 0
    err = capsys.readouterr()
    payload = json.loads(err.out.strip())
    text = json.dumps(payload)
    assert "search-ml" in text or "embed-provider" in text


def test_search_index_fails_without_backend_when_chroma_missing(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr("cli.common.chroma_importable", lambda: False)
    rc = main(["search", "index", "--json", "--data-dir", str(tmp_path), *HASH_FLAGS])
    assert rc != 0
    err = capsys.readouterr()
    payload = json.loads(err.out.strip() or err.err.strip().splitlines()[-1])
    text = json.dumps(payload)
    assert "chroma" in text.lower() or "install" in text.lower()
    assert "zhihu-backup[chroma]" in text or "pip install" in text


def test_search_semantic_no_index_fails(tmp_path, capsys):
    rc = main(
        [
            "search",
            "semantic",
            PHRASE,
            "--vector-backend",
            "memory",
            *HASH_FLAGS,
            "--json",
            "--data-dir",
            str(tmp_path),
        ]
    )
    assert rc != 0
    out = json.loads(capsys.readouterr().out.strip())
    assert out["event"] == "error"
    assert "search index" in out["error"].lower()


def test_search_semantic_backend_mismatch_fails(tmp_path, capsys):
    _seed_item(tmp_path)
    rc = main(
        [
            "search",
            "index",
            "--vector-backend",
            "memory",
            *HASH_FLAGS,
            "--json",
            "--data-dir",
            str(tmp_path),
        ]
    )
    assert rc == 0
    capsys.readouterr()

    manifest = tmp_path / "meta" / "sqlite" / "vectors" / "manifest.json"
    data = json.loads(manifest.read_text(encoding="utf-8"))
    data["backend"] = "chroma"
    manifest.write_text(json.dumps(data), encoding="utf-8")

    rc = main(
        [
            "search",
            "semantic",
            PHRASE,
            "--vector-backend",
            "memory",
            *HASH_FLAGS,
            "--json",
            "--data-dir",
            str(tmp_path),
        ]
    )
    assert rc != 0
    out = json.loads(capsys.readouterr().out.strip())
    assert out["event"] == "error"
    assert "backend mismatch" in out["error"].lower()
