from unittest.mock import MagicMock

from zhihu_backup.models import ItemRecord, NormalizedItem
from zhihu_backup.pipeline import Pipeline
from zhihu_backup.sources import build_sources
from zhihu_backup.sources.base import Source
from zhihu_backup.storage import open_engine
from zhihu_backup.writers.person import PersonWriter


def test_all_excludes_social():
    client = MagicMock()
    client.get_json.return_value = {"url_token": "me", "id": "me"}
    names = {s.name for s in build_sources(client, source="all", collection_ids=[])}
    assert "following" not in names
    assert "followers" not in names


def test_social_includes_both():
    client = MagicMock()
    client.get_json.return_value = {"url_token": "me", "id": "me"}
    names = [s.name for s in build_sources(client, source="social", collection_ids=[])]
    assert names == ["following", "followers"]


def test_social_prefers_url_token_over_numeric_id():
    client = MagicMock()
    client.get_json.return_value = {"url_token": "me_token", "id": "12345"}
    sources = build_sources(client, source="social", collection_ids=[])
    assert [s.source_id for s in sources] == ["me_token", "me_token"]


def _user_item(*, zhihu_id: str = "friend", center: str = "me_token") -> NormalizedItem:
    return NormalizedItem(
        item_type="user",
        zhihu_id=zhihu_id,
        url=f"https://www.zhihu.com/people/{zhihu_id}",
        title="Friend",
        author="Friend",
        author_badge="hello",
        markdown_body="hello",
        owner_kind="people",
        owner_id=center,
        sources=[f"following:{center}"],
        modified=None,
    )


class _NamedSource(Source):
    def __init__(self, name: str, source_id: str = "me_token"):
        self.name = name
        self.source_id = source_id

    def total(self):
        return None

    def iter_items(self, offset: int = 0, limit: int = 20):
        yield offset, []


def test_person_writer_flat_people_path(tmp_path):
    writer = PersonWriter(tmp_path / "contents")
    item = _user_item()
    path = writer.write(item, item.markdown_body)
    assert path == tmp_path / "contents" / "people" / "friend.md"
    text = path.read_text(encoding="utf-8")
    assert "type: user" in text
    assert "url_token: friend" in text
    assert "headline: hello" in text


def test_process_person_creates_and_upserts_following_edge(tmp_path):
    engine = open_engine("sqlite", tmp_path / "meta")
    pipe = Pipeline(engine, tmp_path / "contents", tmp_path / "assets")
    item = _user_item()
    action = pipe.process_item(item, source=_NamedSource("following"))
    assert action == "created"
    rec = engine.get_item(item.key)
    assert rec is not None
    assert rec.path.endswith("people/friend.md")
    edges = engine.list_graph_edges()
    assert len(edges) == 1
    assert edges[0].from_id == "user:me_token"
    assert edges[0].to_id == "user:friend"
    assert edges[0].kind == "follows"
    assert edges[0].origin == "api"
    engine.close()


def test_process_person_skip_still_upserts_edge(tmp_path):
    engine = open_engine("sqlite", tmp_path / "meta")
    pipe = Pipeline(engine, tmp_path / "contents", tmp_path / "assets")
    item = _user_item()
    engine.upsert_item(
        ItemRecord(key=item.key, item_type="user", zhihu_id=item.zhihu_id, title="Friend")
    )
    action = pipe.process_item(item, source=_NamedSource("following"))
    assert action == "skipped"
    edges = engine.list_graph_edges()
    assert len(edges) == 1
    assert edges[0].from_id == "user:me_token"
    assert edges[0].to_id == "user:friend"
    assert edges[0].origin == "api"
    engine.close()


def test_process_person_followers_edge_is_reverse(tmp_path):
    engine = open_engine("sqlite", tmp_path / "meta")
    pipe = Pipeline(engine, tmp_path / "contents", tmp_path / "assets")
    item = _user_item()
    item.sources = ["followers:me_token"]
    action = pipe.process_item(item, source=_NamedSource("followers"))
    assert action == "created"
    edges = engine.list_graph_edges()
    assert edges[0].from_id == "user:friend"
    assert edges[0].to_id == "user:me_token"
    engine.close()


def test_should_skip_user_when_existing(tmp_path):
    engine = open_engine("sqlite", tmp_path / "meta")
    pipe = Pipeline(engine, tmp_path / "contents", tmp_path / "assets")
    item = _user_item()
    assert pipe.should_skip(item) is False
    engine.upsert_item(
        ItemRecord(key=item.key, item_type="user", zhihu_id=item.zhihu_id)
    )
    assert pipe.should_skip(item) is True
    pipe.full = True
    assert pipe.should_skip(item) is False
    engine.close()
