from __future__ import annotations

import json
from typing import Any


TASK_TYPE = "feishu_meeting_negotiation"


def _payload(record: dict[str, Any]) -> dict[str, Any]:
    try:
        loaded = json.loads(str(record.get("payload_json") or "{}"))
    except json.JSONDecodeError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _negotiation_metadata(record: dict[str, Any]) -> dict[str, Any]:
    payload = _payload(record)
    return {
        "task_type": TASK_TYPE,
        "negotiation_id": str(record["negotiation_id"]),
        "workspace_id": str(record["workspace_id"]),
        "kanban_task_id": record.get("kanban_task_id"),
        "status": str(record["status"]),
        "meeting_title": str(payload.get("meeting_title") or payload.get("title") or record["event_id"]),
        "event_id": str(record["event_id"]),
        "event_revision_id": str(record["event_revision_id"]),
    }


def _operation_record(record: dict[str, Any]) -> dict[str, Any]:
    metadata = _negotiation_metadata(record)
    return {
        **record,
        "task_type": TASK_TYPE,
        "metadata": metadata,
        "kanban_deep_link": "/kanban",
    }


def list_monitors(*, workspace_id: str, limit: int = 50, store: Any | None = None) -> dict[str, Any]:
    from feishu_meeting_coordinator import store as meeting_coordinator_store

    active_store = store or meeting_coordinator_store.MeetingCoordinatorStore()
    return {
        "monitors": active_store.list_operation_monitors(workspace_id=workspace_id, limit=limit),
        "delivery_tasks": active_store.list_operation_delivery_tasks(workspace_id=workspace_id, limit=limit),
        "workspace_state": active_store.get_workspace_state(workspace_id),
    }


def list_negotiations(*, workspace_id: str, limit: int = 50, store: Any | None = None) -> dict[str, Any]:
    from feishu_meeting_coordinator import store as meeting_coordinator_store

    active_store = store or meeting_coordinator_store.MeetingCoordinatorStore()
    negotiations = active_store.list_operation_negotiations(
        workspace_id=workspace_id,
        limit=limit,
    )
    return {
        "negotiations": [_operation_record(record) for record in negotiations],
        "metadata_contract": {
            "task_signal": {"field": "task_type", "value": TASK_TYPE},
            "canonical_location": "body.metadata.task_type",
        },
    }


def negotiation_detail(
    *,
    negotiation_id: str,
    workspace_id: str,
    store: Any | None = None,
) -> dict[str, Any]:
    from feishu_meeting_coordinator import store as meeting_coordinator_store

    active_store = store or meeting_coordinator_store.MeetingCoordinatorStore()
    negotiation = active_store.get_negotiation_for_workspace(
        negotiation_id,
        workspace_id=workspace_id,
    )
    return {
        "negotiation": _operation_record(negotiation),
        "participants": active_store.list_negotiation_participants(negotiation_id),
        "candidate_slots": active_store.list_candidate_slots(negotiation_id),
        "votes": active_store.list_negotiation_votes(negotiation_id),
        "messages": active_store.list_negotiation_messages(negotiation_id),
        "events": active_store.list_negotiation_events(negotiation_id),
    }


def nudge_unblock(*, negotiation_id: str, store: Any, kanban: Any) -> dict[str, Any]:
    negotiation = store.get_negotiation(negotiation_id)
    task_id = str(negotiation.get("kanban_task_id") or "").strip()
    if not task_id:
        raise ValueError("negotiation has no linked Kanban task")
    unblocked = bool(kanban.unblock(task_id))
    return {"negotiation_id": negotiation_id, "kanban_task_id": task_id, "unblocked": unblocked}


def finalize(*, payload: dict[str, Any], store: Any, calendar_client: Any, cron: Any = None) -> dict[str, Any]:
    from feishu_meeting_coordinator import gateway as meeting_coordinator_gateway

    return meeting_coordinator_gateway.finalize_negotiation_case(
        payload,
        store=store,
        calendar_client=calendar_client,
        cron=cron,
    )


def cancel(*, negotiation_id: str, operator_user_id: str, reason: str, store: Any) -> dict[str, Any]:
    owner = f"operator:{operator_user_id or 'unknown'}"
    negotiation = store.get_negotiation(negotiation_id)
    result = store.transition_negotiation_state(
        negotiation_id,
        expected_state=str(negotiation["status"]),
        next_state="cancelled",
        patch={},
        actor_id=owner,
    )
    if not result["ok"]:
        raise RuntimeError(str(result["reason"]))
    return result["record"]


def retry_delivery_now(*, workspace_id: str, store: Any, delivery_client: Any) -> dict[str, Any]:
    from feishu_meeting_coordinator import gateway as meeting_coordinator_gateway

    return meeting_coordinator_gateway.escalation_retry_tick(
        {"workspace_id": workspace_id},
        store=store,
        delivery_client=delivery_client,
    )


def requeue_delivery_task(*, delivery_task_id: str, reason: str, store: Any, cron: Any) -> dict[str, Any]:
    from feishu_meeting_coordinator import gateway as meeting_coordinator_gateway

    return meeting_coordinator_gateway.requeue_delivery_task(
        delivery_task_id=delivery_task_id,
        reason=reason,
        store=store,
        cron=cron,
    )
