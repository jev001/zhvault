import json

from zhihu_backup.cli import build_parser, main
from zhihu_backup.models import ItemRecord
from zhihu_backup.storage import open_engine


def test_require_max_depth_one():
    from zhihu_backup.cli import require_max_depth_mvp

    assert require_max_depth_mvp(1) is None
    err = require_max_depth_mvp(2)
    assert err and "not implemented" in err.lower()


def test_backup_max_depth_two_exits_nonzero(tmp_path, capsys):
    rc = main(["backup", "--max-depth", "2", "--json", "--data-dir", str(tmp_path)])
    assert rc == 2
    out = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert out["event"] == "error"
    assert "not implemented" in out["error"].lower()


def test_parser_max_depth_default_on_backup_and_resume():
    p = build_parser()
    assert p.parse_args(["backup"]).max_depth == 1
    assert p.parse_args(["resume"]).max_depth == 1


def test_parser_graph_nested_like_auth():
    p = build_parser()
    rb = p.parse_args(["graph", "rebuild"])
    assert rb.func.__name__ == "cmd_graph_rebuild"
    add = p.parse_args(["graph", "edge", "add", "--from", "user:a", "--to", "user:b"])
    assert add.func.__name__ == "cmd_graph_edge_add"
    assert add.from_id == "user:a"
    assert add.to_id == "user:b"
    assert add.kind == "follows"
    rem = p.parse_args(
        ["graph", "edge", "remove", "--from", "user:a", "--to", "user:b", "--kind", "asked"]
    )
    assert rem.func.__name__ == "cmd_graph_edge_remove"
    assert rem.kind == "asked"


def test_graph_rebuild_offline_no_cookies(tmp_path, capsys):
    meta = tmp_path / "meta"
    meta.mkdir()
    eng = open_engine("sqlite", meta)
    try:
        eng.upsert_item(
            ItemRecord(key="question:10", item_type="question", zhihu_id="10", title="Q")
        )
    finally:
        eng.close()

    rc = main(["graph", "rebuild", "--data-dir", str(tmp_path), "--json"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert out["event"] == "summary"
    assert out["nodes"] >= 1
    graph_path = tmp_path / "meta" / "sqlite" / "graph.json"
    assert graph_path.exists()
    payload = json.loads(graph_path.read_text(encoding="utf-8"))
    assert payload["ego"] is None


def test_graph_rebuild_me_failure_stays_offline(tmp_path, monkeypatch):
    meta = tmp_path / "meta"
    meta.mkdir()
    eng = open_engine("sqlite", meta)
    try:
        eng.set_cookie({"z_c0": "x"})
    finally:
        eng.close()

    class BoomClient:
        def __init__(self, *args, **kwargs):
            pass

        def get_json(self, url):
            raise PermissionError("auth failed HTTP 403")

    monkeypatch.setattr("zhihu_backup.cli.ZhihuClient", BoomClient)
    rc = main(["graph", "rebuild", "--data-dir", str(tmp_path), "--json"])
    assert rc == 0
    payload = json.loads(
        (tmp_path / "meta" / "sqlite" / "graph.json").read_text(encoding="utf-8")
    )
    assert payload["ego"] is None


def test_graph_rebuild_uses_me_when_cookies_ok(tmp_path, monkeypatch):
    meta = tmp_path / "meta"
    meta.mkdir()
    eng = open_engine("sqlite", meta)
    try:
        eng.set_cookie({"z_c0": "x"})
    finally:
        eng.close()

    class OkClient:
        def __init__(self, *args, **kwargs):
            pass

        def get_json(self, url):
            assert "api/v4/me" in url
            return {"url_token": "me_token", "id": "123"}

    monkeypatch.setattr("zhihu_backup.cli.ZhihuClient", OkClient)
    rc = main(["graph", "rebuild", "--data-dir", str(tmp_path), "--json"])
    assert rc == 0
    payload = json.loads(
        (tmp_path / "meta" / "sqlite" / "graph.json").read_text(encoding="utf-8")
    )
    assert payload["ego"] == "me_token"


def test_graph_edge_add_and_remove(tmp_path):
    rc = main(
        [
            "graph",
            "edge",
            "add",
            "--from",
            "user:a",
            "--to",
            "user:b",
            "--data-dir",
            str(tmp_path),
            "--json",
        ]
    )
    assert rc == 0
    eng = open_engine("sqlite", tmp_path / "meta")
    try:
        edges = eng.list_graph_edges()
        assert len(edges) == 1
        assert edges[0].from_id == "user:a"
        assert edges[0].to_id == "user:b"
        assert edges[0].kind == "follows"
        assert edges[0].origin == "manual"
    finally:
        eng.close()

    rc = main(
        [
            "graph",
            "edge",
            "remove",
            "--from",
            "user:a",
            "--to",
            "user:b",
            "--data-dir",
            str(tmp_path),
            "--json",
        ]
    )
    assert rc == 0
    eng = open_engine("sqlite", tmp_path / "meta")
    try:
        assert eng.list_graph_edges() == []
    finally:
        eng.close()
