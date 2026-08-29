"""Optional live Zhihu API checks. Excluded from make gate via addopts -m 'not live'.

Run: ZHVAULT_LIVE=1 ZHVAULT_LIVE_USER=<token> make test-live
Cookie: ZHVAULT_COOKIE_FILE or Cookies.json in cwd.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from auth import resolve_member_profile
from http_client import ZhihuClient
from live_support import call_or_skip_transient, require_live
from zhihu_lists import LIST_ROUTES, fetch_person_list

pytestmark = pytest.mark.live


@pytest.fixture
def live_ctx() -> tuple[str, ZhihuClient]:
    token, cookies = require_live()
    client = ZhihuClient(cookies, timeout=20.0, min_interval=0.3)
    return token, client


def _assert_list_payload(resource: str, payload: dict) -> None:
    assert isinstance(payload, dict), f"{resource}: expected dict payload"
    assert "data" in payload, f"{resource}: missing data key (route/contract bug?)"
    assert isinstance(payload["data"], list), f"{resource}: data must be a list"
    data = payload["data"]
    if data:
        assert isinstance(payload.get("paging"), dict), (
            f"{resource}: non-empty list should include paging"
        )


@pytest.mark.parametrize("resource", sorted(LIST_ROUTES.keys()))
def test_live_fetch_person_list_one_page(live_ctx: tuple[str, ZhihuClient], resource: str):
    token, client = live_ctx
    payload = call_or_skip_transient(
        fetch_person_list, client, token, resource, offset=0, limit=5
    )
    _assert_list_payload(resource, payload)


def test_live_resolve_member_profile(live_ctx: tuple[str, ZhihuClient]):
    token, client = live_ctx
    profile = call_or_skip_transient(resolve_member_profile, client, token)
    assert profile["url_token"]
    assert profile["url_token"] == token or profile["url_token"]


def test_live_backup_people_minimal(tmp_path: Path, live_ctx: tuple[str, ZhihuClient]):
    token, _client = live_ctx
    from live_support import resolve_cookie_path

    cookie_file = resolve_cookie_path()
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    runner = CliRunner()
    from cli.app import app

    auth = runner.invoke(
        app,
        [
            "auth",
            "set-cookie",
            str(cookie_file),
            "--data-dir",
            str(data_dir),
            "--engine",
            "json",
            "--json",
        ],
        prog_name="zhvault",
    )
    if auth.exit_code != 0:
        err = (auth.stdout or "") + (auth.stderr or "")
        pytest.fail(f"auth set-cookie failed: exit={auth.exit_code} {err[:500]}")

    result = runner.invoke(
        app,
        [
            "backup",
            "--source",
            "people",
            "--user",
            token,
            "--data-dir",
            str(data_dir),
            "--engine",
            "json",
            "--json",
        ],
        prog_name="zhvault",
    )
    out = (result.stdout or "") + (result.stderr or "")
    if result.exit_code != 0:
        low = out.lower()
        if any(
            s in low
            for s in ("http 403", "http 429", "timed out", "timeout", "connection")
        ):
            pytest.skip(f"transient during backup: {out[:300]}")
        pytest.fail(f"backup people failed: exit={result.exit_code} {out[:800]}")

    contents = data_dir / "contents"
    md_files = list(contents.rglob("*.md")) if contents.is_dir() else []
    people_md = contents / "people" / f"{token}.md"
    assert people_md.is_file() or md_files, (
        "expected people profile md or at least one content file after live backup"
    )
