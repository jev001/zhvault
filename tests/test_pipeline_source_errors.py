from __future__ import annotations

from pathlib import Path
from typing import Iterator, Optional

from zhihu_backup.models import NormalizedItem, RunStats
from zhihu_backup.pipeline import Pipeline
from zhihu_backup.sources.base import Source
from zhihu_backup.storage import open_engine


class _AuthFailSource(Source):
    name = "asked_question"

    def __init__(self):
        self.source_id = "u1"

    def total(self) -> Optional[int]:
        return None

    def iter_items(self, offset: int = 0, limit: int = 20) -> Iterator[tuple[int, list[NormalizedItem]]]:
        raise PermissionError("auth failed HTTP 403 for https://example/questions")


class _OkEmptySource(Source):
    name = "vote"

    def __init__(self):
        self.source_id = "u1"
        self.called = False

    def total(self) -> Optional[int]:
        return 0

    def iter_items(self, offset: int = 0, limit: int = 20) -> Iterator[tuple[int, list[NormalizedItem]]]:
        self.called = True
        yield 0, []


def test_run_continues_after_source_permission_error(tmp_path: Path):
    engine = open_engine("sqlite", tmp_path / "meta")
    events: list[dict] = []
    pipe = Pipeline(
        engine,
        tmp_path / "contents",
        tmp_path / "assets",
        on_event=events.append,
    )
    bad = _AuthFailSource()
    good = _OkEmptySource()
    stats = pipe.run([bad, good], resume=False)
    assert good.called is True
    assert stats.source_errors == 1
    assert isinstance(stats, RunStats)
    err_events = [e for e in events if e.get("event") == "source_error"]
    assert len(err_events) == 1
    assert err_events[0]["code"] == "auth"
    assert err_events[0]["source"] == "asked_question"
    done = [e for e in events if e.get("event") == "source_done" and e.get("source") == "vote"]
    assert len(done) == 1
    engine.close()
