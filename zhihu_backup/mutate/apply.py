"""Apply account mutate plans with stacked danger gates."""

from __future__ import annotations

import logging
from typing import Any, Optional

from zhihu_backup.http_client import ZhihuClient
from zhihu_backup.mutate import endpoints
from zhihu_backup.mutate.plan import recompute_fingerprint, rebuild_plan_from_inventory

log = logging.getLogger("zhihu_backup.mutate.apply")

CONFIRM_TOKEN = "APPLY"


class ApplyGateError(ValueError):
    """Refused before any write."""


def check_apply_gates(
    *,
    i_understand_danger: bool,
    confirm: Optional[str],
) -> None:
    if not i_understand_danger:
        raise ApplyGateError("refusing apply: missing --i-understand-danger")
    if confirm != CONFIRM_TOKEN:
        raise ApplyGateError(f"refusing apply: --confirm must be exactly {CONFIRM_TOKEN!r}")


def verify_fingerprint(
    plan: dict[str, Any],
    *,
    open_engine_fn,
    client: Optional[ZhihuClient] = None,
    skip_rebuild: bool = False,
) -> None:
    """Ensure plan fingerprint still matches inventory (or embedded actions if skip_rebuild)."""
    stored = str(plan.get("fingerprint") or "")
    if skip_rebuild:
        recomputed = recompute_fingerprint(plan)
        if recomputed != stored:
            raise ApplyGateError("refusing apply: plan fingerprint mismatch (actions tampered)")
        return
    try:
        fresh = rebuild_plan_from_inventory(plan, open_engine_fn=open_engine_fn, client=client)
    except Exception as e:
        raise ApplyGateError(f"refusing apply: cannot rebuild inventory for fingerprint: {e}") from e
    if str(fresh.get("fingerprint")) != stored:
        raise ApplyGateError("refusing apply: stale plan fingerprint (inventory changed; re-run account plan)")


def _dispatch_one(client: ZhihuClient, action: dict[str, Any], created: dict[str, str]) -> None:
    op = action.get("op")
    if op == "follow_user":
        client.request_json("POST", endpoints.follow_user_url(str(action["url_token"])))
        return
    if op == "unfollow_user":
        client.request_json("DELETE", endpoints.follow_user_url(str(action["url_token"])))
        return
    if op == "follow_question":
        client.request_json("POST", endpoints.follow_question_url(str(action["question_id"])))
        return
    if op == "unfollow_question":
        client.request_json("DELETE", endpoints.follow_question_url(str(action["question_id"])))
        return
    if op == "collect_add":
        cid = action.get("collection_id")
        title = action.get("create_title")
        if not cid and title:
            if title not in created:
                resp = client.request_json(
                    "POST",
                    endpoints.create_collection_url(),
                    json_body={"title": title},
                )
                new_id = str(resp.get("id") or (resp.get("favlist") or {}).get("id") or "")
                if not new_id:
                    raise RuntimeError(f"create collection returned no id: {resp}")
                created[title] = new_id
            cid = created[title]
        if not cid:
            raise RuntimeError("collect_add missing collection_id/create_title")
        client.request_json(
            "POST",
            endpoints.collection_contents_url(str(cid)),
            params={
                "content_id": str(action["content_id"]),
                "content_type": str(action["content_type"]),
            },
            json_body={},
        )
        return
    if op == "collect_remove":
        client.request_json(
            "DELETE",
            endpoints.collection_content_item_url(
                str(action["collection_id"]),
                str(action["content_id"]),
            ),
            params={"content_type": str(action["content_type"])},
        )
        return
    raise RuntimeError(f"unknown op {op!r}")


def apply_plan(
    plan: dict[str, Any],
    client: ZhihuClient,
    *,
    i_understand_danger: bool,
    confirm: Optional[str],
    open_engine_fn,
    skip_rebuild: bool = False,
) -> dict[str, Any]:
    check_apply_gates(i_understand_danger=i_understand_danger, confirm=confirm)
    verify_fingerprint(plan, open_engine_fn=open_engine_fn, client=None, skip_rebuild=skip_rebuild)

    me = {}
    try:
        me = client.get_json(endpoints.ME_URL)
    except Exception as e:
        log.warning("could not fetch /me before apply: %s", e)
    actor = str(me.get("url_token") or me.get("id") or plan.get("actor_hint") or "unknown")
    counts = plan.get("counts") or {}
    log.warning(
        "DANGER: account apply as %s — writes_executed=true counts=%s",
        actor,
        counts,
    )

    created: dict[str, str] = {}
    ok = 0
    failed: list[dict[str, Any]] = []
    for action in plan.get("actions") or []:
        try:
            _dispatch_one(client, action, created)
            ok += 1
        except Exception as e:
            failed.append({"action": action, "error": str(e)})
            log.error("apply action failed %s: %s", action, e)

    return {
        "event": "apply_summary",
        "writes_executed": True,
        "actor": actor,
        "ok": ok,
        "failed": failed,
        "failed_count": len(failed),
        "created_collections": created,
        "mode": plan.get("mode"),
        "fingerprint": plan.get("fingerprint"),
    }
