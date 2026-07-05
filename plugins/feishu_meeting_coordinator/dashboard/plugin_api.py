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


def negotiation_task_metadata(
    record: dict[str, Any],
    store: Any | None = None,
) -> dict[str, Any]:
    from feishu_meeting_coordinator import store as meeting_coordinator_store

    active_store = store or meeting_coordinator_store.MeetingCoordinatorStore()
    payload = _payload(record)
    record_negotiation_id = str(record["negotiation_id"])
    metadata = {
        "task_type": TASK_TYPE,
        "negotiation_id": record_negotiation_id,
        "workspace_id": str(record["workspace_id"]),
        "kanban_task_id": record.get("kanban_task_id"),
        "status": str(record["status"]),
        "meeting_title": str(payload.get("meeting_title") or payload.get("title") or record["event_id"]),
        "event_id": str(record["event_id"]),
        "event_revision_id": str(record["event_revision_id"]),
        "session_id": str(payload.get("session_id") or record.get("session_id") or "").strip(),
    }

    negotiation_id = record_negotiation_id
    participants = active_store.list_negotiation_participants(negotiation_id)
    required_participants = [
        item
        for item in participants
        if int(item.get("required_for_consent") or 0) == 1
        and _to_text(item.get("attendee_user_id"))
    ]
    required_ids = {str(item["attendee_user_id"]) for item in required_participants}
    metadata["required_attendee_count"] = len(required_ids)
    missing_required = [item for item in required_participants]
    missing_attendee_names = _to_names(missing_required)
    declined_attendee_user_id = _to_text(record.get("declined_attendee_user_id"))
    if declined_attendee_user_id:
        declined_attendee_name = declined_attendee_user_id
        for item in participants:
            if str(item.get("attendee_user_id")) == declined_attendee_user_id:
                declined_attendee_name = _to_text(
                    item.get("display_name"),
                    declined_attendee_user_id,
                )
                break
        metadata["declined_attendee_name"] = declined_attendee_name
    slots = active_store.list_candidate_slots(negotiation_id)
    if slots:
        visible_slots = [
            slot for slot in slots if str(slot.get("status") or "") != "superseded"
        ]
        if not visible_slots:
            visible_slots = slots
        latest_slot = visible_slots[-1]
        slot_id = _to_text(latest_slot.get("slot_id"))
        metadata["best_slot_id"] = slot_id
        metadata["best_slot"] = (
            f"{_to_text(latest_slot.get('start_time'))} - {_to_text(latest_slot.get('end_time'))}"
        )
        metadata["best_slot_timezone"] = _to_text(latest_slot.get("timezone"), "UTC")
        votes = (
            active_store.list_votes_for_slot(
                negotiation_id=negotiation_id,
                slot_id=slot_id,
            )
            if slot_id
            else []
        )
        vote_yes_ids = {
            str(item.get("attendee_user_id"))
            for item in votes
            if str(item.get("vote") or "") == "yes"
        }
        vote_yes_ids.add(_to_text(latest_slot.get("proposed_by_user_id")))
        still_missing = [
            str(item.get("attendee_user_id"))
            for item in required_participants
            if str(item.get("attendee_user_id")) not in vote_yes_ids
        ]
        missing_attendee_names = _to_names(
            [item for item in required_participants if item["attendee_user_id"] in still_missing]
        )
    metadata["followup_cron_status"] = _to_text(
        record.get("followup_cron_status"),
        "not_created",
    )
    metadata["followup_cron_last_tick_at"] = _to_text(
        record.get("followup_cron_last_tick_at")
    )
    metadata["next_followup_at"] = _to_text(record.get("next_followup_at"))
    metadata["followup_cron_failure_count"] = _to_int(
        record.get("followup_cron_failure_count"), 0
    )
    metadata["missing_required_attendee_names"] = missing_attendee_names
    metadata["missing_required_attendee_count"] = len(missing_attendee_names)
    return metadata


def _operation_record(record: dict[str, Any], store: Any | None = None) -> dict[str, Any]:
    metadata = negotiation_task_metadata(record, store=store)
    return {
        **record,
        "task_type": TASK_TYPE,
        "metadata": metadata,
        "kanban_deep_link": "/kanban",
    }


def _to_text(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip()
    return text if text else fallback


def _to_int(value: Any, fallback: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _to_names(values: list[dict[str, Any]]) -> list[str]:
    names: list[str] = []
    for item in values:
        name = _to_text(item.get("display_name"), _to_text(item.get("attendee_user_id")))
        if name not in names:
            names.append(name)
    return names


def _enrich_negotiation_metadata(
    record: dict[str, Any],
    store: Any | None = None,
) -> dict[str, Any]:
    return _operation_record(record, store=store)


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
        "negotiations": [
            _enrich_negotiation_metadata(record, store=active_store)
            for record in negotiations
        ],
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
        "negotiation": _enrich_negotiation_metadata(negotiation, store=active_store),
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
