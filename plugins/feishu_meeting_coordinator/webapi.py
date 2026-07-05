from __future__ import annotations

import hashlib
import hmac
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter

from fastapi import HTTPException, Request

from agents.auth_session import request_context_from_request
from agents.auth_db import list_feishu_bot_configs
from . import gateway as meeting_coordinator_gateway
from . import store as meeting_coordinator_store
from .webapi_service import (
    MeetingCoordinatorWebApiCalendarClient,
    MeetingCoordinatorWebApiCronClient,
    meeting_coordinator_delivery_client_from_context,
)

router = APIRouter(tags=["webapi-gateway"])

ROUTE_POLICY_MAP = {
    ("POST", "/callbacks/feishu/meeting-coordinator/reply"): "public",
    ("GET", "/system/meeting-coordinator/monitors"): "authenticated",
    ("GET", "/system/meeting-coordinator/negotiations"): "authenticated",
    ("GET", "/system/meeting-coordinator/negotiations/{negotiation_id}"): "authenticated",
    ("POST", "/system/meeting-coordinator/negotiations/{negotiation_id}/run"): "authenticated",
    ("POST", "/system/meeting-coordinator/negotiations/{negotiation_id}/reply"): "authenticated",
    ("POST", "/system/meeting-coordinator/negotiations/{negotiation_id}/finalize"): "authenticated",
    ("POST", "/system/meeting-coordinator/negotiations/{negotiation_id}/cancel"): "authenticated",
    (
        "POST",
        "/plugins/meeting-coordinator/negotiations/{negotiation_id}/requester-decision",
    ): "authenticated",
    ("GET", "/system/meeting-coordinator/settings"): "authenticated",
    ("PUT", "/system/meeting-coordinator/settings"): "authenticated",
    ("POST", "/system/meeting-coordinator/delivery-tasks/retry"): "authenticated",
    (
        "POST",
        "/system/meeting-coordinator/delivery-tasks/{delivery_task_id}/requeue",
    ): "authenticated",
}

ROUTE_AUTHZ_CLASS_MAP = {}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _text(value: Any) -> str:
    return str(value or "").strip()


def _nested_text(payload: dict[str, Any], *path: str) -> str:
    current: Any = payload
    for key in path:
        if not isinstance(current, dict):
            return ""
        current = current.get(key)
    return _text(current)


def _feishu_callback_app_id(payload: dict[str, Any]) -> str:
    return (
        _nested_text(payload, "header", "app_id")
        or _nested_text(payload, "event", "app_id")
        or _text(payload.get("app_id"))
    )


def _feishu_callback_sender_open_id(payload: dict[str, Any]) -> str:
    return (
        _nested_text(payload, "event", "sender", "sender_id", "open_id")
        or _nested_text(payload, "event", "sender", "open_id")
        or _nested_text(payload, "sender", "sender_id", "open_id")
        or _text(payload.get("sender_open_id"))
    )


def _feishu_callback_message(payload: dict[str, Any]) -> dict[str, Any]:
    message = payload.get("message")
    if isinstance(message, dict):
        return message
    event = payload.get("event")
    event_message = event.get("message") if isinstance(event, dict) else None
    return event_message if isinstance(event_message, dict) else {}


def _feishu_callback_raw_text(payload: dict[str, Any]) -> str:
    message = _feishu_callback_message(payload)
    raw = message.get("content") or payload.get("raw_text") or payload.get("text") or ""
    if isinstance(raw, dict):
        raw = raw.get("text") or ""
    return str(raw).replace("\x00", "").strip()[:4000]


def _feishu_workspace_config_for_app_id(app_id: str) -> dict[str, Any] | None:
    for config in list_feishu_bot_configs():
        if _text(config.get("app_id")) != app_id:
            continue
        workspace_id = _text(
            config.get("owner_workspace_id") or config.get("workspace_id")
        )
        if workspace_id:
            return {**config, "workspace_id": workspace_id}
    return None


def _verify_feishu_callback_signature(
    request: Request,
    *,
    raw_body: bytes,
    config: dict[str, Any],
) -> bool:
    signature = _text(request.headers.get("x-feishu-signature"))
    timestamp = _text(request.headers.get("x-feishu-request-timestamp"))
    nonce = _text(request.headers.get("x-feishu-request-nonce"))
    app_secret = _text(config.get("app_secret"))
    if not signature or not timestamp or not nonce or not app_secret:
        return False
    signed = timestamp.encode("utf-8") + b"." + nonce.encode("utf-8") + b"." + raw_body
    expected = hmac.new(app_secret.encode("utf-8"), signed, hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature, expected)


def _require_negotiation_operator(negotiation: dict, *, user_id: str | None) -> None:
    if str(negotiation.get("creator_user_id") or "") != str(user_id or ""):
        raise HTTPException(status_code=403, detail="requester_or_operator_required")


@router.post("/callbacks/feishu/meeting-coordinator/reply")
async def feishu_meeting_coordinator_reply_callback(request: Request):
    raw_body = await request.body()
    try:
        body = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="invalid_json") from exc
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="invalid_json")
    app_id = _feishu_callback_app_id(body)
    if not app_id:
        raise HTTPException(status_code=400, detail="missing_app_id")
    config = _feishu_workspace_config_for_app_id(app_id)
    if config is None:
        raise HTTPException(status_code=403, detail="unknown_tenant")
    if not _verify_feishu_callback_signature(request, raw_body=raw_body, config=config):
        raise HTTPException(status_code=403, detail="invalid_signature")
    message = _feishu_callback_message(body)
    envelope = {
        "callback_origin": True,
        "workspace_id": str(config["workspace_id"]),
        "feishu_app_id": app_id,
        "callback_signature_valid": True,
        "sender_open_id": _feishu_callback_sender_open_id(body),
        "provider_message_id": _text(
            message.get("message_id") or body.get("provider_message_id")
        ),
        "thread_id": _text(message.get("thread_id") or body.get("thread_id")),
        "root_message_id": _text(
            message.get("root_id")
            or message.get("parent_id")
            or body.get("root_message_id")
        ),
        "received_at_utc": _utc_now_iso(),
        "raw_text": _feishu_callback_raw_text(body),
        "payload": {
            "event_type": _nested_text(body, "header", "event_type")
            or _text(body.get("type")),
            "message_type": _text(message.get("message_type")),
        },
    }
    try:
        result = meeting_coordinator_gateway.submit_negotiation_reply(
            envelope,
            store=meeting_coordinator_store.MeetingCoordinatorStore(),
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=403, detail="uncorrelated_message") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if isinstance(result, dict) and result.get("status") in {
        "not_correlated",
        "rejected",
    }:
        raise HTTPException(
            status_code=403,
            detail=result.get("reason", "uncorrelated_message"),
        )
    return {"ok": True, "result": result}


@router.get("/system/meeting-coordinator/monitors")
async def system_meeting_coordinator_monitors(request: Request):
    ctx = request_context_from_request(request)
    if not ctx.authenticated:
        raise HTTPException(status_code=401, detail="authentication required")
    store = meeting_coordinator_store.MeetingCoordinatorStore()
    meeting_coordinator_gateway.repair_delivery_retry_scheduler(
        workspace_id=ctx.workspace_id,
        store=store,
        cron=MeetingCoordinatorWebApiCronClient(ctx),
    )
    return {
        "ok": True,
        "monitors": store.list_operation_monitors(
            workspace_id=ctx.workspace_id,
            limit=100,
        ),
        "deliveryTasks": store.list_operation_delivery_tasks(
            workspace_id=ctx.workspace_id,
            limit=100,
        ),
        "scheduler": store.get_workspace_state(ctx.workspace_id),
    }


@router.get("/system/meeting-coordinator/negotiations")
async def system_meeting_coordinator_negotiations(request: Request):
    ctx = request_context_from_request(request)
    if not ctx.authenticated:
        raise HTTPException(status_code=401, detail="authentication required")
    store = meeting_coordinator_store.MeetingCoordinatorStore()
    return {
        "ok": True,
        "negotiations": store.list_operation_negotiations(
            workspace_id=ctx.workspace_id,
            limit=100,
        ),
    }


@router.get("/system/meeting-coordinator/negotiations/{negotiation_id}")
async def system_meeting_coordinator_negotiation_detail(
    negotiation_id: str,
    request: Request,
):
    ctx = request_context_from_request(request)
    if not ctx.authenticated:
        raise HTTPException(status_code=401, detail="authentication required")
    store = meeting_coordinator_store.MeetingCoordinatorStore()
    try:
        negotiation = store.get_negotiation_for_workspace(
            negotiation_id,
            workspace_id=ctx.workspace_id,
        )
    except KeyError as exc:
        raise HTTPException(
            status_code=404, detail="not_found_or_wrong_workspace"
        ) from exc
    return {
        "ok": True,
        "negotiation": negotiation,
        "participants": store.list_negotiation_participants(negotiation_id),
        "candidate_slots": store.list_candidate_slots(negotiation_id),
        "votes": store.list_negotiation_votes(negotiation_id),
        "messages": store.list_negotiation_messages(negotiation_id),
        "finalize_attempts": store.list_finalize_attempts(negotiation_id),
        "events": store.list_negotiation_events(negotiation_id),
    }


@router.post("/system/meeting-coordinator/negotiations/{negotiation_id}/run")
async def system_meeting_coordinator_negotiation_run(
    negotiation_id: str,
    request: Request,
):
    ctx = request_context_from_request(request)
    if not ctx.authenticated:
        raise HTTPException(status_code=401, detail="authentication required")
    store = meeting_coordinator_store.MeetingCoordinatorStore()
    try:
        negotiation_record = store.get_negotiation_for_workspace(
            negotiation_id,
            workspace_id=ctx.workspace_id,
        )
    except KeyError as exc:
        raise HTTPException(
            status_code=404, detail="not_found_or_wrong_workspace"
        ) from exc
    _require_negotiation_operator(negotiation_record, user_id=ctx.user_id)
    try:
        negotiation = meeting_coordinator_gateway.ensure_negotiation_kanban_task(
            negotiation_id=negotiation_id,
            store=store,
            kanban=None,
        )
    except Exception as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"ok": True, "negotiation": negotiation}


@router.post("/system/meeting-coordinator/negotiations/{negotiation_id}/reply")
async def system_meeting_coordinator_negotiation_reply(
    negotiation_id: str,
    request: Request,
):
    ctx = request_context_from_request(request)
    if not ctx.authenticated:
        raise HTTPException(status_code=401, detail="authentication required")
    body = await request.json()
    participant_user_id = str(
        body.get("participant_user_id") or ctx.user_id or ""
    ).strip()
    store = meeting_coordinator_store.MeetingCoordinatorStore()
    try:
        negotiation = store.get_negotiation_for_workspace(
            negotiation_id,
            workspace_id=ctx.workspace_id,
        )
    except KeyError as exc:
        raise HTTPException(
            status_code=404, detail="not_found_or_wrong_workspace"
        ) from exc
    if negotiation["status"] not in {
        "pending_decliner_input",
        "collecting_votes",
        "awaiting_requester_decision",
    }:
        store.record_inbound_reply_rejected(
            negotiation_id=negotiation_id,
            participant_user_id=participant_user_id or "unknown",
            message_id=str(body.get("message_id") or ""),
            reason="non_reply_accepting_state",
        )
        raise HTTPException(status_code=409, detail="non_reply_accepting_state")
    participants = store.list_negotiation_participants(negotiation_id)
    if participant_user_id not in {
        str(item["attendee_user_id"]) for item in participants
    }:
        store.record_inbound_reply_rejected(
            negotiation_id=negotiation_id,
            participant_user_id=participant_user_id or "unknown",
            message_id=str(body.get("message_id") or ""),
            reason="unknown_sender",
        )
        raise HTTPException(status_code=403, detail="not_authorized")
    callback_origin = bool(
        body.get("callback_origin") or "callback_signature_valid" in body
    )
    outbound_message_event_id = str(body.get("outbound_message_event_id") or "").strip()
    message_id = str(body.get("message_id") or "").strip()
    if callback_origin and body.get("callback_signature_valid") is not True:
        store.record_inbound_reply_rejected(
            negotiation_id=negotiation_id,
            participant_user_id=participant_user_id,
            message_id=message_id,
            reason="invalid_signature",
        )
        raise HTTPException(status_code=403, detail="invalid_signature")
    if callback_origin:
        try:
            outbound = store.get_negotiation_message(outbound_message_event_id)
        except KeyError as exc:
            store.record_inbound_reply_rejected(
                negotiation_id=negotiation_id,
                participant_user_id=participant_user_id,
                message_id=message_id,
                reason="uncorrelated_message",
            )
            raise HTTPException(status_code=403, detail="uncorrelated_message") from exc
        if (
            outbound["negotiation_id"] != negotiation_id
            or outbound["participant_user_id"] != participant_user_id
            or outbound["direction"] != "outbound"
        ):
            store.record_inbound_reply_rejected(
                negotiation_id=negotiation_id,
                participant_user_id=participant_user_id,
                message_id=message_id,
                reason="uncorrelated_message",
            )
            raise HTTPException(status_code=403, detail="uncorrelated_message")
        result = meeting_coordinator_gateway.submit_negotiation_reply(
            {
                **body,
                "negotiation_id": negotiation_id,
                "participant_user_id": participant_user_id,
                "message_id": message_id,
            },
            store=store,
        )
        return {
            "ok": True,
            "result": result,
        }
    try:
        result = meeting_coordinator_gateway.submit_negotiation_reply(
            {
                **body,
                "negotiation_id": negotiation_id,
                "participant_user_id": participant_user_id,
                "message_id": message_id,
            },
            store=store,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"ok": True, "result": result}


@router.post("/system/meeting-coordinator/negotiations/{negotiation_id}/finalize")
async def system_meeting_coordinator_negotiation_finalize(
    negotiation_id: str,
    request: Request,
):
    ctx = request_context_from_request(request)
    if not ctx.authenticated:
        raise HTTPException(status_code=401, detail="authentication required")
    body = await request.json()
    if body.get("requester_confirmation") is not True:
        raise HTTPException(status_code=403, detail="requester_confirmation_required")
    store = meeting_coordinator_store.MeetingCoordinatorStore()
    try:
        negotiation_record = store.get_negotiation_for_workspace(
            negotiation_id,
            workspace_id=ctx.workspace_id,
        )
        _require_negotiation_operator(negotiation_record, user_id=ctx.user_id)
        result = meeting_coordinator_gateway.finalize_negotiation_case(
            {
                **body,
                "negotiation_id": negotiation_id,
                "requested_by_user_id": str(ctx.user_id or ""),
            },
            store=store,
            calendar_client=MeetingCoordinatorWebApiCalendarClient(ctx),
            cron=MeetingCoordinatorWebApiCronClient(ctx),
        )
    except KeyError as exc:
        raise HTTPException(
            status_code=404, detail="not_found_or_wrong_workspace"
        ) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"ok": True, "result": result, "finalize_attempt": result["attempt"]}


@router.post("/system/meeting-coordinator/negotiations/{negotiation_id}/cancel")
async def system_meeting_coordinator_negotiation_cancel(
    negotiation_id: str,
    request: Request,
):
    ctx = request_context_from_request(request)
    if not ctx.authenticated:
        raise HTTPException(status_code=401, detail="authentication required")
    store = meeting_coordinator_store.MeetingCoordinatorStore()
    try:
        negotiation_record = store.get_negotiation_for_workspace(
            negotiation_id,
            workspace_id=ctx.workspace_id,
        )
    except KeyError as exc:
        raise HTTPException(
            status_code=404, detail="not_found_or_wrong_workspace"
        ) from exc
    _require_negotiation_operator(negotiation_record, user_id=ctx.user_id)
    owner = f"operator:{ctx.user_id or 'unknown'}"
    result = store.transition_negotiation_state(
        negotiation_id,
        expected_state=str(negotiation_record["status"]),
        next_state="cancelled",
        patch={},
        actor_id=owner,
    )
    if not result["ok"]:
        raise HTTPException(status_code=409, detail=str(result["reason"]))
    meeting_coordinator_gateway.complete_negotiation_kanban_if_terminal(
        negotiation_id=negotiation_id,
        store=store,
        kanban=None,
        summary="Operator cancelled the meeting time negotiation.",
    )
    return {"ok": True, "negotiation": result["record"]}


@router.post(
    "/plugins/meeting-coordinator/negotiations/{negotiation_id}/requester-decision"
)
async def plugins_meeting_coordinator_negotiation_requester_decision(
    negotiation_id: str,
    request: Request,
):
    ctx = request_context_from_request(request)
    if not ctx.authenticated:
        raise HTTPException(status_code=401, detail="authentication required")
    body = await request.json()
    action = str(body.get("action") or "").strip()
    if not action:
        raise HTTPException(status_code=400, detail="action is required")
    store = meeting_coordinator_store.MeetingCoordinatorStore()
    try:
        negotiation_record = store.get_negotiation_for_workspace(
            negotiation_id,
            workspace_id=ctx.workspace_id,
        )
    except KeyError as exc:
        raise HTTPException(
            status_code=404, detail="not_found_or_wrong_workspace"
        ) from exc
    _require_negotiation_operator(negotiation_record, user_id=ctx.user_id)
    if action == "requester_select_slot" and not (
        str(body.get("slot_id") or body.get("selected_slot_id") or "").strip()
    ):
        raise HTTPException(
            status_code=400, detail="selected_slot_id is required for requester_select_slot"
        )
    try:
        result = meeting_coordinator_gateway.apply_requester_decision(
            {
                **body,
                "negotiation_id": negotiation_id,
                "requested_by_user_id": str(ctx.user_id or ""),
            },
            store=store,
            cron=MeetingCoordinatorWebApiCronClient(ctx),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return {"ok": True, "result": result}


@router.get("/system/meeting-coordinator/settings")
async def system_meeting_coordinator_settings(request: Request):
    ctx = request_context_from_request(request)
    if not ctx.authenticated:
        raise HTTPException(status_code=401, detail="authentication required")
    state = meeting_coordinator_store.MeetingCoordinatorStore().get_workspace_state(
        ctx.workspace_id
    )
    return {
        "ok": True,
        "settings": {
            "max_followups": int(state.get("max_followups") or 3),
        },
    }


@router.put("/system/meeting-coordinator/settings")
async def system_meeting_coordinator_settings_update(request: Request):
    ctx = request_context_from_request(request)
    if not ctx.authenticated:
        raise HTTPException(status_code=401, detail="authentication required")
    body = await request.json()
    try:
        max_followups = int(body.get("max_followups"))
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=400, detail="max_followups must be an integer"
        ) from exc
    try:
        state = meeting_coordinator_store.MeetingCoordinatorStore().update_workspace_settings(
            ctx.workspace_id,
            max_followups=max_followups,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "ok": True,
        "settings": {
            "max_followups": int(state.get("max_followups") or 3),
        },
    }


@router.post("/system/meeting-coordinator/delivery-tasks/retry")
async def system_meeting_coordinator_delivery_retry(request: Request):
    ctx = request_context_from_request(request)
    if not ctx.authenticated:
        raise HTTPException(status_code=401, detail="authentication required")
    result = meeting_coordinator_gateway.escalation_retry_tick(
        {"workspace_id": ctx.workspace_id},
        store=meeting_coordinator_store.MeetingCoordinatorStore(),
        delivery_client=meeting_coordinator_delivery_client_from_context(ctx),
    )
    return {"ok": True, **result}


@router.post("/system/meeting-coordinator/delivery-tasks/{delivery_task_id}/requeue")
async def system_meeting_coordinator_delivery_task_requeue(
    delivery_task_id: str,
    request: Request,
):
    ctx = request_context_from_request(request)
    if not ctx.authenticated:
        raise HTTPException(status_code=401, detail="authentication required")
    body = await request.json()
    reason = str(body.get("reason") or "").strip()
    if not reason:
        raise HTTPException(status_code=400, detail="reason is required")
    task = meeting_coordinator_gateway.requeue_delivery_task(
        delivery_task_id=delivery_task_id,
        reason=reason,
        store=meeting_coordinator_store.MeetingCoordinatorStore(),
        cron=MeetingCoordinatorWebApiCronClient(ctx),
    )
    return {"ok": True, "delivery_task": task}
