from __future__ import annotations

import json
import hashlib
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Protocol

from .store import MeetingCoordinatorStore

_PROMPTS_ROOT = Path(__file__).resolve().parent / "prompts"

_FOLLOWUP_CRON_NAME_PREFIX = "meeting-time-negotiator-followup:"
_FOLLOWUP_CRON_SCRIPT_PREFIX = "meeting-time-negotiator-followup-"


class CronClient(Protocol):
    def ensure_job(
        self,
        *,
        name: str,
        schedule: str,
        profile: str,
        prompt: str,
        skills: list[str],
        deliver: str,
        repeat: int,
        no_agent: bool = False,
        script: str | None = None,
        model: str | None = None,
        provider: str | None = None,
        base_url: str | None = None,
    ) -> str: ...

    def job_exists(self, cron_job_id: str) -> bool: ...

    def agent_runtime_config(self, *, profile: str) -> dict[str, str | None]: ...


def _delete_cron_job(cron: CronClient, cron_job_id: str) -> bool:
    if hasattr(cron, "delete_job"):
        return bool(cron.delete_job(cron_job_id))  # type: ignore[attr-defined]
    if hasattr(cron, "remove_job"):
        return bool(cron.remove_job(cron_job_id))  # type: ignore[attr-defined]
    return False


class DeliveryClient(Protocol):
    def send_creator_escalation(self, task: dict[str, Any]) -> dict[str, Any]: ...


class CalendarUpdateClient(Protocol):
    def update_meeting_time(
        self,
        *,
        event_id: str,
        calendar_id: str,
        start_time: str,
        end_time: str,
        timezone: str,
    ) -> dict[str, Any]: ...


class KanbanClient(Protocol):
    def create_negotiation_task(
        self, *, negotiation: dict[str, Any], body: str
    ) -> str: ...

    def comment(self, task_id: str, *, author: str, body: str) -> int: ...

    def block(self, task_id: str, *, reason: str, kind: str | None = None) -> bool: ...

    def unblock(self, task_id: str) -> bool: ...

    def complete(
        self,
        task_id: str,
        *,
        summary: str,
        metadata: dict[str, Any] | None = None,
    ) -> bool: ...

    def update_task_body(self, task_id: str, *, body: str) -> bool: ...

    def delete(self, task_id: str) -> bool: ...


def _prompt(name: str, **values: str) -> str:
    text = (_PROMPTS_ROOT / name).read_text(encoding="utf-8")
    for key, value in values.items():
        text = text.replace("{{" + key + "}}", str(value))
    return text


def _prompt_language(monitor: dict[str, Any]) -> str:
    try:
        payload = json.loads(str(monitor.get("payload_json") or "{}"))
    except json.JSONDecodeError:
        payload = {}
    try:
        binding = json.loads(str(monitor.get("creator_delivery_binding_json") or "{}"))
    except json.JSONDecodeError:
        binding = {}
    raw = (
        str(
            binding.get("language")
            or binding.get("locale")
            or payload.get("language")
            or payload.get("locale")
            or payload.get("user_language")
            or ""
        )
        .strip()
        .lower()
    )
    if raw.startswith("zh") or raw in {"chinese", "中文"}:
        return "zh"
    text_fields = (
        payload.get("meeting_title"),
        payload.get("title"),
        payload.get("meeting_start_time"),
        payload.get("start_time"),
    )
    if any(
        any("\u4e00" <= char <= "\u9fff" for char in str(value or ""))
        for value in text_fields
    ):
        return "zh"
    return "en"


def _localized_prompt(name: str, language: str, **values: str) -> str:
    if language and language != "en":
        localized = name.removesuffix(".md") + f".{language}.md"
        if (_PROMPTS_ROOT / localized).exists():
            return _prompt(localized, **values)
    return _prompt(name, **values)


def _monitor_payload(monitor: dict[str, Any]) -> dict[str, Any]:
    try:
        payload = json.loads(str(monitor.get("payload_json") or "{}"))
    except json.JSONDecodeError:
        payload = {}
    return payload if isinstance(payload, dict) else {}


def _meeting_title(monitor: dict[str, Any]) -> str:
    payload = _monitor_payload(monitor)
    return str(
        payload.get("meeting_title") or payload.get("title") or monitor.get("event_id")
    )


def _meeting_start_time(monitor: dict[str, Any]) -> str:
    payload = _monitor_payload(monitor)
    return str(payload.get("start_time") or payload.get("meeting_start_time") or "")


def _creator_name(monitor: dict[str, Any]) -> str:
    payload = _monitor_payload(monitor)
    return str(
        payload.get("organizer_name")
        or payload.get("organizer_identity")
        or payload.get("requester_name")
        or payload.get("creator_display_name")
        or payload.get("creator_user_id")
        or monitor.get("creator_user_id")
    )


def _calendar_item_link(monitor: dict[str, Any]) -> str:
    payload = _monitor_payload(monitor)
    return str(
        payload.get("calendar_item_url")
        or payload.get("calendar_url")
        or payload.get("event_url")
        or payload.get("join_url")
        or payload.get("meeting_link")
        or ""
    )


def start_monitor(
    payload: dict[str, Any],
    *,
    store: MeetingCoordinatorStore,
    cron: CronClient,
) -> dict[str, Any]:
    monitor = store.start_monitor(payload)
    cron_id = str(monitor.get("cron_job_id") or "")
    if cron_id and cron.job_exists(cron_id):
        return monitor
    try:
        name = f"meeting-rsvp-monitor:{monitor['monitor_id']}"
        prompt = _prompt(
            "RSVP_MONITOR_JOB.md",
            monitor_id=monitor["monitor_id"],
            workspace_id=monitor["workspace_id"],
            event_id=monitor["event_id"],
            calendar_id=monitor["calendar_id"],
        )
        new_cron_id = cron.ensure_job(
            name=name,
            schedule="every 2m",
            profile="meeting-coordinator",
            prompt=prompt,
            skills=["feishu_meeting_coordinator"],
            deliver="local",
            repeat=0,
            no_agent=True,
            script=f"meeting-rsvp-monitor-{monitor['monitor_id']}.py",
        )
    except Exception as exc:
        detail = str(exc)
        if payload.get("scheduler_failure_terminal") is True:
            return store.mark_monitor_failed(monitor["monitor_id"], detail=detail)
        return store.mark_monitor_start_failed(monitor["monitor_id"], detail=detail)
    return store.attach_cron_job(monitor["monitor_id"], new_cron_id)


def ensure_delivery_retry_cron(*, workspace_id: str, cron: CronClient) -> str:
    return cron.ensure_job(
        name=f"meeting-rsvp-delivery-retry:{workspace_id}",
        schedule="every 2m",
        profile="meeting-coordinator",
        prompt=_prompt("DELIVERY_RETRY_JOB.md", workspace_id=workspace_id),
        skills=["feishu_meeting_coordinator"],
        deliver="local",
        repeat=0,
        no_agent=True,
        script=f"meeting-rsvp-delivery-retry-{workspace_id}.py",
    )


def ensure_negotiation_kanban_task(
    *,
    negotiation_id: str,
    store: MeetingCoordinatorStore,
    kanban: KanbanClient | None = None,
    session_id: str | None = None,
) -> dict[str, Any]:
    from .kanban_client import HermesKanbanClient, negotiation_task_body

    negotiation = store.get_negotiation(negotiation_id)
    existing_task_id = str(negotiation.get("kanban_task_id") or "").strip()
    if existing_task_id:
        _sync_negotiation_kanban_task_body(
            negotiation_id=negotiation_id,
            store=store,
            kanban=kanban,
            session_id=session_id,
        )
        return negotiation
    client = kanban or HermesKanbanClient()
    body = negotiation_task_body(negotiation=negotiation, session_id=session_id)
    task_id = client.create_negotiation_task(negotiation=negotiation, body=body)
    negotiation = store.set_negotiation_kanban_task(
        negotiation_id,
        kanban_task_id=task_id,
    )
    _sync_negotiation_kanban_task_body(
        negotiation_id=negotiation_id,
        store=store,
        kanban=kanban,
        session_id=session_id,
    )
    return negotiation


def _resolve_kanban_client(kanban: KanbanClient | None) -> KanbanClient:
    if kanban is not None:
        return kanban
    from .kanban_client import HermesKanbanClient

    return HermesKanbanClient()


def _sync_negotiation_kanban_task_body(
    *,
    negotiation_id: str,
    store: MeetingCoordinatorStore,
    kanban: KanbanClient | None = None,
    session_id: str | None = None,
) -> bool:
    negotiation = store.get_negotiation(negotiation_id)
    task_id = str(negotiation.get("kanban_task_id") or "").strip()
    if not task_id:
        return False
    try:
        from .kanban_client import negotiation_task_body
        from .dashboard.plugin_api import negotiation_task_metadata

        metadata = negotiation_task_metadata(negotiation, store=store)
    except Exception:
        metadata = None
    client = _resolve_kanban_client(kanban)
    payload_session_id = (
        session_id
        or str(metadata.get("session_id") if isinstance(metadata, dict) else "")
        or str(negotiation.get("session_id") or "").strip()
    )
    try:
        body = negotiation_task_body(
            negotiation=negotiation,
            session_id=payload_session_id,
            metadata=metadata if isinstance(metadata, dict) else None,
        )
        return bool(client.update_task_body(task_id, body=body))
    except Exception:
        return False


def _kanban_comment_and_unblock_for_reply(
    *,
    negotiation: dict[str, Any],
    accepted_message: dict[str, Any],
    payload: dict[str, Any],
    store: MeetingCoordinatorStore,
    kanban: KanbanClient | None,
) -> dict[str, Any]:
    task_id = str(negotiation.get("kanban_task_id") or "").strip()
    if not task_id:
        return {"kanban_comment_id": None, "kanban_unblocked": False}
    client = _resolve_kanban_client(kanban)
    participant_user_id = str(accepted_message["participant_user_id"])
    reply_text = str(payload.get("reply_text") or "").strip()
    intent = str(payload.get("intent") or payload.get("vote") or "").strip()
    comment_body = f"Reply from {participant_user_id}: {reply_text or intent or accepted_message['message_id']}"
    comment_id = client.comment(
        task_id,
        author=participant_user_id,
        body=comment_body,
    )
    store.set_message_kanban_comment(
        str(accepted_message["message_event_id"]),
        kanban_comment_id=str(comment_id),
    )
    unblocked = client.unblock(task_id)
    return {"kanban_comment_id": str(comment_id), "kanban_unblocked": bool(unblocked)}


def _complete_kanban_if_terminal(
    *,
    negotiation_id: str,
    store: MeetingCoordinatorStore,
    kanban: KanbanClient | None,
    summary: str,
) -> bool:
    negotiation = store.get_negotiation(negotiation_id)
    if not _negotiation_is_terminal(negotiation):
        return False
    task_id = str(negotiation.get("kanban_task_id") or "").strip()
    if not task_id:
        return False
    _sync_negotiation_kanban_task_body(
        negotiation_id=negotiation_id,
        store=store,
        kanban=kanban,
    )
    return _resolve_kanban_client(kanban).complete(
        task_id,
        summary=summary,
        metadata={
            "negotiation_id": negotiation_id,
            "status": str(negotiation["status"]),
            "finalize_attempt_id": negotiation.get("finalize_attempt_id"),
        },
    )


def complete_negotiation_kanban_if_terminal(
    *,
    negotiation_id: str,
    store: MeetingCoordinatorStore,
    kanban: KanbanClient | None = None,
    summary: str,
) -> bool:
    return _complete_kanban_if_terminal(
        negotiation_id=negotiation_id,
        store=store,
        kanban=kanban,
        summary=summary,
    )


def repair_delivery_retry_scheduler(
    *,
    workspace_id: str,
    store: MeetingCoordinatorStore,
    cron: CronClient,
) -> bool:
    non_terminal_tasks = store.list_non_terminal_delivery_tasks(
        workspace_id=workspace_id,
        limit=1,
    )
    if not non_terminal_tasks:
        return False
    try:
        ensure_delivery_retry_cron(workspace_id=workspace_id, cron=cron)
    except Exception as exc:
        store.mark_delivery_retry_scheduler_unavailable(
            workspace_id=workspace_id,
            detail=str(exc),
        )
        return False
    return True


def create_creator_escalation_task(
    *,
    monitor_id: str,
    attendee_user_id: str,
    reason: str,
    store: MeetingCoordinatorStore,
    cron: CronClient,
    message: str | None = None,
    ensure_retry_cron: bool = True,
) -> dict[str, Any]:
    monitor = store.get_monitor(monitor_id)
    binding = json.loads(monitor["creator_delivery_binding_json"])
    task = store.create_delivery_task(
        monitor_id=monitor_id,
        task_type="creator_escalation",
        target_user_id=monitor["creator_user_id"],
        delivery_binding=binding,
        payload={
            "attendee_user_id": attendee_user_id,
            "reason": reason,
            **({"message": message} if message else {}),
        },
    )
    if ensure_retry_cron:
        try:
            ensure_delivery_retry_cron(workspace_id=monitor["workspace_id"], cron=cron)
        except Exception as exc:
            store.mark_delivery_retry_scheduler_unavailable(
                workspace_id=monitor["workspace_id"],
                detail=str(exc),
            )
    return task


def requeue_delivery_task(
    *,
    delivery_task_id: str,
    reason: str,
    store: MeetingCoordinatorStore,
    cron: CronClient,
) -> dict[str, Any]:
    task = store.requeue_delivery_task(delivery_task_id, reason=reason)
    try:
        ensure_delivery_retry_cron(workspace_id=task["workspace_id"], cron=cron)
    except Exception as exc:
        store.mark_delivery_retry_scheduler_unavailable(
            workspace_id=task["workspace_id"],
            detail=str(exc),
        )
    return task


def _parse_utc(value: str | None) -> datetime | None:
    from agents.temporal_resolution import parse_aware_utc

    return parse_aware_utc(value)


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _followup_due(attendee: dict[str, Any], *, interval_minutes: int) -> bool:
    last_followup = _parse_utc(attendee.get("last_followup_at"))
    if last_followup is None:
        return True
    return _now_utc() - last_followup >= timedelta(minutes=interval_minutes)


def _normalize_feishu_rsvp_status(raw_status: Any) -> str:
    status = str(raw_status or "").strip().lower()
    if status in {"accepted", "accept", "tentative", "maybe"}:
        return "accepted"
    if status in {"declined", "decline", "no"}:
        return "declined"
    if status in {
        "needs_action",
        "needsaction",
        "pending",
        "none",
        "null",
        "unknown",
    }:
        return "needs_action"
    return "needs_action"


def _followup_reminder_needed(participant: dict[str, Any]) -> bool:
    if str(participant.get("role") or "") == "requester":
        return False
    if str(participant.get("delivery_status") or "") == "escalated":
        return False
    return str(participant.get("latest_response_status") or "unknown") in {
        "unknown",
        "asked",
    }


def _snapshot_payload_for_prompt(negotiation: dict[str, Any]) -> dict[str, Any]:
    return {
        "event_id": str(negotiation["event_id"]),
        "creator_user_id": str(negotiation["creator_user_id"]),
        "workspace_id": str(negotiation["workspace_id"]),
        "creator_delivery_binding_json": str(negotiation["creator_delivery_binding_json"]),
        "payload_json": str(negotiation["payload_json"]),
    }


def _followup_cron_job_exists(
    *, cron: CronClient, job_id: str
) -> bool:
    if hasattr(cron, "get_job"):
        try:
            return cron.get_job(job_id) is not None
        except Exception:
            return False
    if hasattr(cron, "job_exists"):
        try:
            return bool(cron.job_exists(job_id))
        except Exception:
            return False
    return True


def _schedule_interval_minutes(schedule: Any) -> int | None:
    if isinstance(schedule, dict):
        if str(schedule.get("kind") or "").strip().lower() == "interval":
            try:
                minutes = int(schedule.get("minutes"))
            except (TypeError, ValueError):
                return None
            return minutes if minutes > 0 else None
        display = str(schedule.get("display") or "").strip()
    else:
        display = str(schedule or "").strip()
    match = re.fullmatch(
        r"every\s+(\d+)\s*(m|min|mins|minute|minutes)",
        display,
        re.IGNORECASE,
    )
    if not match:
        return None
    minutes = int(match.group(1))
    return minutes if minutes > 0 else None


def _cron_followup_interval_minutes(
    monitor: dict[str, Any],
    cron: CronClient | None,
) -> int | None:
    if cron is None or not hasattr(cron, "get_job"):
        return None
    cron_job_id = str(monitor.get("cron_job_id") or "").strip()
    if not cron_job_id:
        return None
    try:
        job = cron.get_job(cron_job_id)  # type: ignore[attr-defined]
    except Exception:
        return None
    if not isinstance(job, dict):
        return None
    return _schedule_interval_minutes(
        job.get("schedule") or job.get("schedule_display")
    )


def _followup_interval_minutes(
    payload: dict[str, Any],
    monitor: dict[str, Any],
    cron: CronClient | None,
) -> int:
    if (
        "followup_interval_minutes" in payload
        and payload.get("followup_interval_minutes") is not None
    ):
        return int(payload.get("followup_interval_minutes") or 0)
    return _cron_followup_interval_minutes(monitor, cron) or 2


def _render_reminder(monitor: dict[str, Any], attendee: dict[str, Any]) -> str:
    return _localized_prompt(
        "FOLLOWUP_MESSAGE.md",
        _prompt_language(monitor),
        attendee_name=str(
            attendee.get("display_name") or attendee.get("attendee_user_id")
        ),
        meeting_title=_meeting_title(monitor),
        start_time=_meeting_start_time(monitor),
        organizer_name=_creator_name(monitor),
        response_status=str(attendee.get("response_status") or "unknown"),
        calendar_item_link=_calendar_item_link(monitor),
    )


def _render_creator_escalation(
    monitor: dict[str, Any],
    attendee: dict[str, Any],
    *,
    reason: str,
) -> str:
    return _localized_prompt(
        "CREATOR_ESCALATION.md",
        _prompt_language(monitor),
        creator_name=_creator_name(monitor),
        attendee_name=str(
            attendee.get("display_name") or attendee.get("attendee_user_id")
        ),
        meeting_title=_meeting_title(monitor),
        reason=reason,
    )


def _render_cancel_suggestion(
    monitor: dict[str, Any], attendees: list[dict[str, Any]]
) -> str:
    attendee_names = ", ".join(
        str(item.get("display_name") or item.get("attendee_user_id"))
        for item in attendees
    )
    return _localized_prompt(
        "CREATOR_CANCEL_SUGGESTION.md",
        _prompt_language(monitor),
        creator_name=_creator_name(monitor),
        attendee_names=attendee_names,
        meeting_title=_meeting_title(monitor),
        start_time=_meeting_start_time(monitor),
    )


def _all_terminal(attendees: list[dict[str, Any]]) -> bool:
    return bool(attendees) and all(
        str(item.get("response_status") or "") in {"accepted", "declined", "tentative"}
        for item in attendees
    )


def _all_exhausted_unanswered(
    attendees: list[dict[str, Any]], *, max_followups: int
) -> bool:
    return bool(attendees) and all(
        str(item.get("response_status") or "") in {"needs_action", "unknown"}
        and int(item.get("followup_count") or 0) >= max_followups
        for item in attendees
    )


def _dismiss_monitor_cron(monitor: dict[str, Any], cron: CronClient | None) -> None:
    cron_job_id = str(monitor.get("cron_job_id") or "")
    if not cron_job_id or cron is None:
        return
    if _delete_cron_job(cron, cron_job_id):
        return
    if hasattr(cron, "disable_job"):
        cron.disable_job(cron_job_id)  # type: ignore[attr-defined]


def _cleanup_monitor_owned_kanban_tasks(
    monitor: dict[str, Any],
    *,
    store: MeetingCoordinatorStore,
    kanban: KanbanClient | None,
    reason: str,
) -> list[dict[str, Any]]:
    if str(monitor.get("status") or "") == "negotiating":
        return []
    cleaned: list[dict[str, Any]] = []
    for negotiation in store.list_negotiations_for_monitor(str(monitor["monitor_id"])):
        task_id = str(negotiation.get("kanban_task_id") or "").strip()
        if not task_id:
            continue
        client = _resolve_kanban_client(kanban)
        deleted = bool(client.delete(task_id))
        store.mark_negotiation_kanban_task_cleaned(
            str(negotiation["negotiation_id"]),
            kanban_task_id=task_id,
            reason=reason,
        )
        cleaned.append(
            {
                "negotiation_id": negotiation["negotiation_id"],
                "kanban_task_id": task_id,
                "deleted": deleted,
            }
        )
    return cleaned


def _monitor_is_terminal(monitor: dict[str, Any]) -> bool:
    return str(monitor.get("status") or "") in {
        "complete",
        "negotiating",
        "cancelled",
        "replaced",
        "failed",
    }


def _negotiation_is_terminal(negotiation: dict[str, Any]) -> bool:
    return str(negotiation.get("status") or "") in {
        "consented",
        "requester_decided",
        "cancelled",
        "expired",
        "failed",
    }


def _render_ask_decliner_message(
    negotiation: dict[str, Any],
    decliner: dict[str, Any],
    locale: str,
) -> str:
    from . import messages as _messages

    try:
        payload_json = json.loads(str(negotiation.get("payload_json") or "{}"))
    except json.JSONDecodeError:
        payload_json = {}
    return _messages.render_ask_decliner_alternative_slot(
        attendee_name=str(decliner.get("display_name") or decliner.get("attendee_user_id")),
        meeting_title=str(
            payload_json.get("meeting_title") or payload_json.get("title") or negotiation["event_id"]
        ),
        original_time=f"{negotiation['original_start_time']} - {negotiation['original_end_time']}",
        timezone=str(negotiation.get("timezone") or "UTC"),
        calendar_item_link=str(
            payload_json.get("calendar_item_url")
            or payload_json.get("calendar_url")
            or payload_json.get("event_url")
            or ""
        ),
        language=locale,
    )


def _render_ask_vote_message(
    negotiation: dict[str, Any],
    participant: dict[str, Any],
    slot: dict[str, Any],
    locale: str,
) -> str:
    from . import messages as _messages

    try:
        payload_json = json.loads(str(negotiation.get("payload_json") or "{}"))
    except json.JSONDecodeError:
        payload_json = {}
    return _messages.render_ask_attendee_slot_vote(
        attendee_name=str(
            participant.get("display_name") or participant.get("attendee_user_id")
        ),
        proposed_by_name=str(slot.get("proposed_by_user_id") or ""),
        meeting_title=str(
            payload_json.get("meeting_title")
            or payload_json.get("title")
            or negotiation["event_id"]
        ),
        candidate_slot=f"{slot['start_time']} - {slot['end_time']}",
        calendar_item_link=str(
            payload_json.get("calendar_item_url")
            or payload_json.get("calendar_url")
            or payload_json.get("event_url")
            or ""
        ),
        language=locale,
    )


def _default_locale_for_negotiation(store: dict[str, Any]) -> str:
    try:
        monitor_payload = json.loads(str(store.get("payload_json") or "{}"))
        raw = str(
            monitor_payload.get("language")
            or monitor_payload.get("locale")
            or ""
        ).strip().lower()
        if raw.startswith("zh") or raw == "chinese":
            return "zh"
    except Exception:
        return "en"
    return "en"


def _send_attendee_message(
    send_message: Callable[[list[str], str], str | None] | None,
    attendee_open_ids: list[str],
    message: str,
) -> str | None:
    if send_message is None:
        return None
    try:
        return str(send_message(attendee_open_ids, message) or "")
    except Exception:
        return None


def _run_negotiation_case_tick(
    *,
    negotiation_id: str,
    store: MeetingCoordinatorStore,
    send_message: Callable[[list[str], str], str | None] | None,
) -> dict[str, Any]:
    negotiation = store.get_negotiation(negotiation_id)
    if _negotiation_is_terminal(negotiation):
        return {
            "negotiation_id": negotiation_id,
            "status": negotiation["status"],
            "terminal": True,
            "worked": True,
            "message": "case_terminal",
        }

    locale = _default_locale_for_negotiation(negotiation)

    if negotiation["status"] != "pending_decliner_input":
        if negotiation["status"] != "collecting_votes":
            return {
                "negotiation_id": negotiation_id,
                "status": negotiation["status"],
                "terminal": False,
                "worked": False,
                "prompt_sent": False,
                "reason": "unsupported_state",
            }
        slots = store.list_candidate_slots(negotiation_id)
        if not slots:
            return {
                "negotiation_id": negotiation_id,
                "status": negotiation["status"],
                "terminal": False,
                "worked": False,
                "vote_prompts_sent": 0,
                "vote_prompts_deduplicated": 0,
                "reason": "missing_candidate_slot",
            }
        slot = slots[-1]
        participants = store.list_negotiation_participants(negotiation_id)
        prompts_sent = 0
        deduped = 0
        for participant in participants:
            attendee_id = str(participant["attendee_user_id"])
            if attendee_id == str(slot["proposed_by_user_id"]):
                continue
            if int(participant.get("required_for_consent") or 0) != 1:
                continue
            target_id = str(participant.get("message_user_id") or attendee_id)
            if not target_id:
                continue
            message = _render_ask_vote_message(
                negotiation=negotiation,
                participant=participant,
                slot=slot,
                locale=locale,
            )
            reserved = store.reserve_outbound_message(
                negotiation_id=negotiation_id,
                message_type="ask_attendee_vote",
                participant_user_id=attendee_id,
                slot_id=str(slot["slot_id"]),
                round_number=int(slot["round_number"]),
                payload={"text": message, "target_id": target_id},
            )
            if not reserved["reserved"]:
                deduped += 1
                continue
            provider_message_id = _send_attendee_message(
                send_message,
                [target_id],
                message,
            )
            if provider_message_id:
                store.mark_outbound_message_sent(
                    message_event_id=reserved["message"]["message_event_id"],
                    provider_message_id=provider_message_id,
                )
            store.update_negotiation_participant_response(
                negotiation_id=negotiation_id,
                attendee_user_id=attendee_id,
                latest_response_status="asked",
                latest_slot_id=str(slot["slot_id"]),
                contacted=True,
                responded=False,
            )
            prompts_sent += 1
        return {
            "negotiation_id": negotiation_id,
            "status": negotiation["status"],
            "terminal": False,
            "worked": True,
            "vote_prompts_sent": prompts_sent,
            "vote_prompts_deduplicated": deduped,
        }

    decliners = [
        item
        for item in store.list_negotiation_participants(negotiation_id)
        if item["role"] == "decliner"
    ]
    if not decliners:
        return {
            "negotiation_id": negotiation_id,
            "status": negotiation["status"],
            "terminal": False,
            "worked": False,
            "prompt_sent": False,
            "reason": "missing_decliner",
        }
    decliner = decliners[0]
    target_id = str(decliner.get("message_user_id") or decliner.get("attendee_user_id"))
    if not target_id:
        return {
            "negotiation_id": negotiation_id,
            "status": negotiation["status"],
            "terminal": False,
            "worked": False,
            "prompt_sent": False,
            "reason": "missing_open_id",
        }
    message = _render_ask_decliner_message(
        negotiation=negotiation,
        decliner=decliner,
        locale=locale,
    )
    reserved = store.reserve_outbound_message(
        negotiation_id=negotiation_id,
        message_type="ask_decliner_slot",
        participant_user_id=str(decliner["attendee_user_id"]),
        round_number=int(negotiation["current_round"] or 0),
        payload={"text": message, "target_id": target_id},
    )
    if not reserved["reserved"]:
        return {
            "negotiation_id": negotiation_id,
            "status": negotiation["status"],
            "terminal": False,
            "worked": False,
            "prompt_sent": False,
            "deduplicated_message_event_id": reserved["message"]["message_event_id"],
        }
    provider_message_id = _send_attendee_message(
        send_message,
        [target_id],
        message,
    )
    if provider_message_id:
        store.mark_outbound_message_sent(
            message_event_id=reserved["message"]["message_event_id"],
            provider_message_id=provider_message_id,
        )
    return {
        "negotiation_id": negotiation_id,
        "status": negotiation["status"],
        "terminal": False,
        "worked": True,
        "prompt_sent": True,
        "message_event_id": reserved["message"]["message_event_id"],
        "provider_message_id": provider_message_id,
    }


def _followup_cron_name(negotiation_id: str) -> str:
    return f"{_FOLLOWUP_CRON_NAME_PREFIX}{str(negotiation_id).strip()}"


def _record_negotiation_event_safely(
    *,
    store: MeetingCoordinatorStore,
    negotiation_id: str,
    event_type: str,
    actor_type: str,
    actor_id: str,
    payload: dict[str, Any],
    prior_state: str | None = None,
    next_state: str | None = None,
    prior_state_version: int | None = None,
    next_state_version: int | None = None,
) -> None:
    try:
        store.record_negotiation_event(
            negotiation_id=negotiation_id,
            event_type=event_type,
            actor_type=actor_type,
            actor_id=actor_id,
            payload=payload,
            prior_state=prior_state,
            next_state=next_state,
            prior_state_version=prior_state_version,
            next_state_version=next_state_version,
        )
    except Exception:
        pass


def _stop_followup_cron_if_terminal(
    *,
    negotiation_id: str,
    store: MeetingCoordinatorStore,
    cron: CronClient | None,
    kanban: KanbanClient | None = None,
    reason: str,
) -> dict[str, Any]:
    negotiation = store.get_negotiation(negotiation_id)
    if not _negotiation_is_terminal(negotiation):
        return {}
    if cron is None:
        return {}
    return stop_negotiation_followup_cron(
        negotiation_id=negotiation_id,
        store=store,
        cron=cron,
        kanban=kanban,
        reason=reason,
    )


def _apply_requester_decision(
    *,
    negotiation: dict[str, Any],
    store: MeetingCoordinatorStore,
    action: str,
    participant_user_id: str,
    slot_id: str | None = None,
    kanban: KanbanClient | None = None,
    cron: CronClient | None = None,
) -> dict[str, Any]:
    negotiation_id = str(negotiation["negotiation_id"])
    owner = f"requester:{participant_user_id}"
    prior_state = str(negotiation.get("status") or "")
    if str(negotiation.get("status") or "") != "awaiting_requester_decision":
        raise RuntimeError("not_awaiting_requester_decision")
    if action == "requester_cancel":
        result = store.transition_negotiation_state(
            negotiation_id,
            expected_state=prior_state,
            next_state="cancelled",
            patch={},
            actor_id=owner,
        )
        next_state = (
            str(result["record"]["status"])
            if isinstance(result, dict) and isinstance(result.get("record"), dict)
            else "cancelled"
        )
        _record_negotiation_event_safely(
            store=store,
            negotiation_id=negotiation_id,
            event_type="REQUESTER_DECISION_APPLIED",
            actor_type="requester",
            actor_id=owner,
            prior_state=prior_state,
            next_state=next_state,
            payload={"action": action},
        )
        completed = _complete_kanban_if_terminal(
            negotiation_id=negotiation_id,
            store=store,
            kanban=kanban,
            summary="Requester cancelled the meeting time negotiation.",
        )
        stop_result = _stop_followup_cron_if_terminal(
            negotiation_id=negotiation_id,
            store=store,
            cron=cron,
            kanban=kanban,
            reason="requester_cancel",
        )
        return {
            "requester_decision": action,
            "transition": result,
            "kanban_completed": completed,
            **({"followup_cron_stopped": True, "followup_cron_stop": stop_result}
               if stop_result
               else {}),
        }

    if action == "requester_keep_original":
        result = store.transition_negotiation_state(
            negotiation_id,
            expected_state=prior_state,
            next_state="requester_decided",
            patch={
                "selected_slot_json": json.dumps(
                    {
                        "decision": "keep_original_time",
                        "start_time": negotiation["original_start_time"],
                        "end_time": negotiation["original_end_time"],
                        "timezone": negotiation["timezone"],
                        "calendar_update": False,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
            },
            actor_id=owner,
        )
        next_state = (
            str(result["record"]["status"])
            if isinstance(result, dict) and isinstance(result.get("record"), dict)
            else "requester_decided"
        )
        _record_negotiation_event_safely(
            store=store,
            negotiation_id=negotiation_id,
            event_type="REQUESTER_DECISION_APPLIED",
            actor_type="requester",
            actor_id=owner,
            prior_state=prior_state,
            next_state=next_state,
            payload={"action": action},
        )
        completed = _complete_kanban_if_terminal(
            negotiation_id=negotiation_id,
            store=store,
            kanban=kanban,
            summary="Requester kept the original meeting time.",
        )
        stop_result = _stop_followup_cron_if_terminal(
            negotiation_id=negotiation_id,
            store=store,
            cron=cron,
            kanban=kanban,
            reason="requester_keep_original",
        )
        return {
            "requester_decision": action,
            "transition": result,
            "calendar_update": False,
            "kanban_completed": completed,
            **({"followup_cron_stopped": True, "followup_cron_stop": stop_result}
               if stop_result
               else {}),
        }

    if action == "requester_select_slot":
        if not slot_id:
            raise ValueError("selected_slot_id is required for requester_select_slot")
        slot = store.get_candidate_slot(slot_id)
        result = store.transition_negotiation_state(
            negotiation_id,
            expected_state=prior_state,
            next_state="requester_decided",
            patch={
                "selected_slot_json": json.dumps(
                    {
                        "slot_id": slot_id,
                        "start_time": slot["start_time"],
                        "end_time": slot["end_time"],
                        "timezone": slot["timezone"],
                        "calendar_update": True,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
            },
            actor_id=owner,
        )
        next_state = (
            str(result["record"]["status"])
            if isinstance(result, dict) and isinstance(result.get("record"), dict)
            else "requester_decided"
        )
        _record_negotiation_event_safely(
            store=store,
            negotiation_id=negotiation_id,
            event_type="REQUESTER_DECISION_APPLIED",
            actor_type="requester",
            actor_id=owner,
            prior_state=prior_state,
            next_state=next_state,
            payload={"action": action, "slot_id": slot_id},
        )
        completed = _complete_kanban_if_terminal(
            negotiation_id=negotiation_id,
            store=store,
            kanban=kanban,
            summary="Requester selected a meeting time.",
        )
        stop_result = _stop_followup_cron_if_terminal(
            negotiation_id=negotiation_id,
            store=store,
            cron=cron,
            kanban=kanban,
            reason="requester_select_slot",
        )
        return {
            "requester_decision": action,
            "transition": result,
            "selected_slot_id": slot_id,
            "kanban_completed": completed,
            **({"followup_cron_stopped": True, "followup_cron_stop": stop_result}
               if stop_result
               else {}),
        }

    raise ValueError("invalid_requester_action")


def ensure_negotiation_followup_cron(
    *,
    negotiation_id: str,
    store: MeetingCoordinatorStore,
    cron: CronClient | None,
    schedule: str = "every 2m",
    kanban: KanbanClient | None = None,
) -> dict[str, Any]:
    negotiation = store.get_negotiation(negotiation_id)
    if _negotiation_is_terminal(negotiation):
        if cron is None:
            negotiation = store.set_negotiation_followup_cron_metadata(
                negotiation_id,
                followup_cron_job_id=None,
                followup_cron_status="not_created",
                next_followup_at=None,
            )
            _sync_negotiation_kanban_task_body(
                negotiation_id=negotiation_id,
                store=store,
                kanban=kanban,
            )
            return negotiation
        return stop_negotiation_followup_cron(
            negotiation_id=negotiation_id,
            store=store,
            cron=cron,
            kanban=kanban,
            reason="terminal_negotiation",
        )
    session_id = str(negotiation.get("session_id") or "").strip()
    if not session_id:
        raise RuntimeError("negotiation_session_id_required")
    name = _followup_cron_name(negotiation_id)
    if cron is None:
        negotiation = store.set_negotiation_followup_cron_metadata(
            negotiation_id,
            followup_cron_job_id=None,
            followup_cron_status="not_created",
            next_followup_at=None,
        )
        _sync_negotiation_kanban_task_body(
            negotiation_id=negotiation_id,
            store=store,
            kanban=kanban,
        )
        return negotiation
    prompt = _prompt(
        "NEGOTIATION_FOLLOWUP_TICK.md",
        negotiation_id=negotiation_id,
        workspace_id=str(negotiation["workspace_id"]),
        session_id=session_id,
    )
    cron_job_id = cron.ensure_job(
        name=name,
        schedule=schedule,
        profile="meeting-coordinator",
        prompt=prompt,
        skills=["feishu_meeting_coordinator"],
        deliver="local",
        repeat=0,
        no_agent=True,
        script=f"{_FOLLOWUP_CRON_SCRIPT_PREFIX}{negotiation_id}.py",
    )

    try:
        interval_minutes = 2
        if hasattr(cron, "get_job"):
            job = cron.get_job(cron_job_id)
            if isinstance(job, dict):
                interval_minutes = _schedule_interval_minutes(
                    job.get("schedule") or job.get("schedule_display")
                ) or interval_minutes
        next_followup_at = (
            datetime.now(timezone.utc) + timedelta(minutes=int(interval_minutes))
        ).isoformat().replace("+00:00", "Z")
    except Exception:
        next_followup_at = None

    negotiation = store.set_negotiation_followup_cron_metadata(
        negotiation_id,
        followup_cron_job_id=cron_job_id,
        followup_cron_status="active",
        next_followup_at=next_followup_at,
    )
    _sync_negotiation_kanban_task_body(
        negotiation_id=negotiation_id,
        store=store,
        kanban=kanban,
    )
    return negotiation


def stop_negotiation_followup_cron(
    *,
    negotiation_id: str,
    store: MeetingCoordinatorStore,
    cron: CronClient,
    reason: str = "operator_stop",
    kanban: KanbanClient | None = None,
) -> dict[str, Any]:
    negotiation = store.get_negotiation(negotiation_id)
    cron_job_id = str(negotiation.get("followup_cron_job_id") or "").strip()
    if cron_job_id and cron is not None:
        try:
            removed = _delete_cron_job(cron, cron_job_id)
        except Exception:
            removed = False
        status = "removed" if removed else "disabled"
    else:
        status = "removed"
        removed = False
    result = store.set_negotiation_followup_cron_metadata(
        negotiation_id,
        followup_cron_job_id=None,
        followup_cron_status=status,
    )
    _record_negotiation_event_safely(
        store=store,
        negotiation_id=negotiation_id,
        event_type="FOLLOWUP_CRON_STOPPED",
        actor_type="system",
        actor_id="meeting-time-negotiator",
        payload={
            "followup_cron_job_id": cron_job_id,
            "removed": bool(removed),
            "status": status,
            "reason": reason,
        },
        prior_state=str(negotiation.get("status") or ""),
        next_state=str(result.get("status") or negotiation.get("status") or ""),
    )
    _sync_negotiation_kanban_task_body(
        negotiation_id=negotiation_id,
        store=store,
        kanban=kanban,
    )
    return result | {
        "removed": bool(removed),
        "disabled": status == "disabled",
        "reason": reason,
    }


def negotiation_followup_cron_tick(
    payload: dict[str, Any],
    *,
    store: MeetingCoordinatorStore,
    kanban: KanbanClient | None = None,
    cron: CronClient | None = None,
    feishu_client: Any | None = None,
    lock_ttl_seconds: int = NEGOTIATION_CASE_LOCK_TTL_SECONDS,
) -> dict[str, Any]:
    negotiation_id = str(payload.get("negotiation_id") or "").strip()
    if not negotiation_id:
        raise ValueError("negotiation_id is required")

    owner = str(payload.get("owner") or f"negotiation_followup_cron:{negotiation_id}")
    if not store.acquire_negotiation_case_lock(
        negotiation_id,
        owner=owner,
        lease_ttl_seconds=lock_ttl_seconds,
    ):
        negotiation = store.get_negotiation(negotiation_id)
        return {
            "negotiation_id": negotiation_id,
            "status": negotiation["status"],
            "terminal": False,
            "ticked": False,
            "worked": False,
            "locked": False,
            "reason": "tick_lock_not_acquired",
        }

    try:
        def _default_feishu_client():
            from .tools import _FeishuClient

            return _FeishuClient()

        def _response_status_for_reminder(participant: dict[str, Any]) -> str:
            status = str(participant.get("latest_response_status") or "unknown")
            if status == "accepted_slot":
                return "accepted"
            if status == "declined_slot":
                return "declined"
            return "needs_action"

        def _reminder_payload(participant: dict[str, Any]) -> str:
            try:
                payload_json = json.loads(str(negotiation.get("payload_json") or "{}"))
            except json.JSONDecodeError:
                payload_json = {}
            return _localized_prompt(
                "FOLLOWUP_MESSAGE.md",
                _default_locale_for_negotiation(negotiation),
                attendee_name=str(
                    participant.get("display_name") or participant.get("attendee_user_id")
                ),
                meeting_title=str(
                    payload_json.get("meeting_title")
                    or payload_json.get("title")
                    or negotiation["event_id"]
                ),
                start_time=f"{negotiation['original_start_time']} - {negotiation['original_end_time']}",
                organizer_name=str(
                    payload_json.get("creator_name")
                    or payload_json.get("organizer_name")
                    or negotiation["creator_user_id"]
                ),
                response_status=_response_status_for_reminder(participant),
                calendar_item_link=str(
                    payload_json.get("calendar_item_url")
                    or payload_json.get("calendar_url")
                    or payload_json.get("event_url")
                    or ""
                ),
            )

        def _parse_rsvp_status(raw_status: Any) -> str:
            normalized = _normalize_feishu_rsvp_status(raw_status)
            if normalized == "accepted":
                return "accepted_slot"
            if normalized == "declined":
                return "declined_slot"
            return "unknown"

        negotiation = store.get_negotiation(negotiation_id)
        _record_negotiation_event_safely(
            store=store,
            negotiation_id=negotiation_id,
            event_type="FOLLOWUP_TICK_STARTED",
            actor_type="system",
            actor_id="meeting-time-negotiator",
            prior_state=str(negotiation.get("status") or ""),
            payload={"tick_payload": dict(payload)},
        )

        if _negotiation_is_terminal(negotiation):
            stop: dict[str, Any] = {}
            if cron is not None:
                stop = stop_negotiation_followup_cron(
                    negotiation_id=negotiation_id,
                    store=store,
                    cron=cron,
                    kanban=kanban,
                    reason="terminal_state",
                )
            _sync_negotiation_kanban_task_body(
                negotiation_id=negotiation_id,
                store=store,
                kanban=kanban,
            )
            return {
                "negotiation_id": negotiation_id,
                "status": negotiation["status"],
                "terminal": True,
                "followup_cron_stopped": bool(
                    stop.get("removed")
                    or stop.get("disabled")
                    or stop.get("followup_cron_status") == "removed"
                ),
                "stop_result": stop,
            }

        client = feishu_client or _default_feishu_client()

        cron_stale = False
        cron_job_id = str(negotiation.get("followup_cron_job_id") or "").strip()
        if cron is not None and cron_job_id:
            try:
                cron_stale = not _followup_cron_job_exists(cron=cron, job_id=cron_job_id)
            except Exception:
                cron_stale = True

        raw_snapshots: list[dict[str, Any]] = []
        try:
            attendee_statuses = client.get_attendee_response_statuses(
                calendar_id=negotiation["calendar_id"],
                event_id=negotiation["event_id"],
            )
            if isinstance(attendee_statuses, list):
                for attendee in attendee_statuses:
                    if not isinstance(attendee, dict):
                        continue
                    attendee_user_id = str(attendee.get("user_id") or "").strip()
                    if not attendee_user_id:
                        continue
                    try:
                        updated = store.update_negotiation_participant_response(
                            negotiation_id=negotiation_id,
                            attendee_user_id=attendee_user_id,
                            latest_response_status=_parse_rsvp_status(
                                attendee.get("response_status")
                            ),
                            responded=_normalize_feishu_rsvp_status(
                                attendee.get("response_status")
                            )
                            in {"accepted", "declined"},
                        )
                    except KeyError:
                        continue
                    raw_snapshots.append(
                        {
                            "attendee_user_id": attendee_user_id,
                            "response_status": str(
                                _normalize_feishu_rsvp_status(attendee.get("response_status"))
                            ),
                        }
                    )
                    _record_negotiation_event_safely(
                        store=store,
                        negotiation_id=negotiation_id,
                        event_type="FOLLOWUP_RSVP_SNAPSHOT",
                        actor_type="system",
                        actor_id="meeting-time-negotiator",
                        payload={
                            "attendee_user_id": attendee_user_id,
                            "stored_response_status": str(
                                updated.get("latest_response_status")
                            ),
                        },
                    )
        except Exception as exc:
            store.bump_followup_cron_failure(negotiation_id)
            _record_negotiation_event_safely(
                store=store,
                negotiation_id=negotiation_id,
                event_type="FOLLOWUP_TICK_FAILED",
                actor_type="system",
                actor_id="meeting-time-negotiator",
                payload={"error": str(exc)},
            )
            raise RuntimeError(str(exc)) from exc

        if raw_snapshots:
            _record_negotiation_event_safely(
                store=store,
                negotiation_id=negotiation_id,
                event_type="FOLLOWUP_RSVP_POLLED",
                actor_type="system",
                actor_id="meeting-time-negotiator",
                payload={
                    "negotiation_id": negotiation_id,
                    "snapshot_count": len(raw_snapshots),
                    "snapshot": raw_snapshots,
                },
            )

        def _send_message(attendee_open_ids: list[str], message: str) -> str | None:
            result = client.send_attendee_message(
                attendee_open_ids=attendee_open_ids,
                message=message,
            )
            return str(result.get("message_id")) if isinstance(result, dict) else None

        case_result = _run_negotiation_case_tick(
            negotiation_id=negotiation_id,
            store=store,
            send_message=_send_message,
        )

        interval_minutes = 2
        job_id = str(negotiation.get("followup_cron_job_id") or "").strip()
        if job_id and cron is not None and hasattr(cron, "get_job"):
            try:
                job = cron.get_job(job_id)
                if isinstance(job, dict):
                    interval_minutes = (
                        _schedule_interval_minutes(
                            job.get("schedule") or job.get("schedule_display")
                        )
                        or interval_minutes
                    )
            except Exception:
                interval_minutes = interval_minutes
        if "followup_interval_minutes" in payload and payload.get(
            "followup_interval_minutes"
        ) is not None:
            interval_minutes = int(payload.get("followup_interval_minutes") or 0)
        if interval_minutes < 0:
            interval_minutes = 0

        if "max_followups" in payload and payload.get("max_followups") is not None:
            max_followups = int(payload.get("max_followups") or 0)
        else:
            max_followups = int(
                store.get_workspace_state(str(negotiation["workspace_id"])).get("max_followups")
                or 3
            )

        reminders_sent = 0
        reminders_failed = 0
        for participant in store.list_negotiation_participants(negotiation_id):
            if not _followup_reminder_needed(participant):
                continue
            if int(participant.get("followup_count") or 0) >= max_followups:
                continue
            if not _followup_due(participant, interval_minutes=interval_minutes):
                continue
            attendee_user_id = str(participant["attendee_user_id"])
            target_id = str(participant.get("message_user_id") or attendee_user_id)
            if not target_id:
                continue
            message = _reminder_payload(participant)
            provider_result: Any = {}
            try:
                provider_result = client.send_attendee_message(
                    attendee_open_ids=[target_id],
                    message=message,
                )
                if not isinstance(provider_result, dict):
                    provider_result = {}
            except Exception as exc:
                provider_result = {"failed": [str(exc)]}
            delivered = provider_result.get("delivered") if isinstance(provider_result, dict) else None
            failed = provider_result.get("failed") if isinstance(provider_result, dict) else None
            if delivered:
                store.record_negotiation_followup_attempt(
                    negotiation_id,
                    attendee_user_id=attendee_user_id,
                    status="sent",
                    error_detail=None,
                )
                reminders_sent += 1
                _record_negotiation_event_safely(
                    store=store,
                    negotiation_id=negotiation_id,
                    event_type="FOLLOWUP_REMINDER_SENT",
                    actor_type="system",
                    actor_id="meeting-time-negotiator",
                    payload={
                        "attendee_user_id": attendee_user_id,
                        "target_id": target_id,
                    },
                )
                continue
            store.record_negotiation_followup_attempt(
                negotiation_id,
                attendee_user_id=attendee_user_id,
                status="failed",
                error_detail=json.dumps(failed, ensure_ascii=False, sort_keys=True)
                if failed
                else None,
            )
            reminders_failed += 1
            _record_negotiation_event_safely(
                store=store,
                negotiation_id=negotiation_id,
                event_type="FOLLOWUP_REMINDER_FAILED",
                actor_type="system",
                actor_id="meeting-time-negotiator",
                payload={
                    "attendee_user_id": attendee_user_id,
                    "target_id": target_id,
                },
            )

        now = datetime.now(timezone.utc)
        post_status = "active"
        post_failure_count = None
        if cron_stale:
            post_status = "failed"
            post_failure_count = int(negotiation.get("followup_cron_failure_count") or 0) + 1
        post_tick_kwargs = {
            "followup_cron_last_tick_at": now.isoformat().replace("+00:00", "Z"),
            "followup_cron_status": post_status,
            "next_followup_at": (now + timedelta(minutes=interval_minutes))
            .isoformat()
            .replace("+00:00", "Z"),
        }
        if post_failure_count is not None:
            post_tick_kwargs["followup_cron_failure_count"] = post_failure_count
        post_tick = store.set_negotiation_followup_cron_metadata(
            negotiation_id,
            **post_tick_kwargs,
        )
        if cron_stale and post_status == "failed":
            _record_negotiation_event_safely(
                store=store,
                negotiation_id=negotiation_id,
                event_type="FOLLOWUP_CRON_STALE",
                actor_type="system",
                actor_id="meeting-time-negotiator",
                payload={"followup_cron_job_id": cron_job_id},
            )

        _record_negotiation_event_safely(
            store=store,
            negotiation_id=negotiation_id,
            event_type="FOLLOWUP_TICK_COMPLETED",
            actor_type="system",
            actor_id="meeting-time-negotiator",
            prior_state=str(negotiation.get("status") or ""),
            next_state=str(post_tick.get("status") or negotiation.get("status") or ""),
            payload={
                "followups_sent": reminders_sent,
                "followups_failed": reminders_failed,
                "rsvp_snapshot_count": len(raw_snapshots),
                "cron_stale": bool(cron_stale),
            },
        )

        negotiation = store.get_negotiation(negotiation_id)
        _sync_negotiation_kanban_task_body(
            negotiation_id=negotiation_id,
            store=store,
            kanban=kanban,
        )
        if _negotiation_is_terminal(negotiation) and cron is not None:
            stop_result = stop_negotiation_followup_cron(
                negotiation_id=negotiation_id,
                store=store,
                cron=cron,
                kanban=kanban,
                reason="terminal_state",
            )
            return {
                **case_result,
                "negotiation_id": negotiation_id,
                "status": negotiation["status"],
                "ticked": True,
                "terminal": True,
                "followup_cron_metadata": post_tick,
                "followups_sent": reminders_sent,
                "followups_failed": reminders_failed,
                "cron_stale": bool(cron_stale),
                "followup_cron_stopped": True,
                "stop_result": stop_result,
            }

        return {
            **case_result,
            "negotiation_id": negotiation_id,
            "status": negotiation["status"],
            "ticked": True,
            "followup_cron_metadata": post_tick,
            "followups_sent": reminders_sent,
            "followups_failed": reminders_failed,
            "cron_stale": bool(cron_stale),
        }
    except Exception as exc:
        try:
            store.bump_followup_cron_failure(negotiation_id)
        except Exception:
            pass
        raise RuntimeError(str(exc)) from exc
    finally:
        store.release_negotiation_case_lock(negotiation_id, owner=owner)


def negotiation_case_tick(
    payload: dict[str, Any],
    *,
    store: MeetingCoordinatorStore,
    cron: CronClient | None = None,
    kanban: KanbanClient | None = None,
    send_message: Callable[[list[str], str], str | None] | None = None,
    lock_owner: str | None = None,
    lease_ttl_seconds: int = NEGOTIATION_CASE_LOCK_TTL_SECONDS,
) -> dict[str, Any]:
    negotiation_id = str(payload.get("negotiation_id") or "").strip()
    if not negotiation_id:
        raise ValueError("negotiation_id is required")

    negotiation = store.get_negotiation(negotiation_id)
    if _negotiation_is_terminal(negotiation):
        return {
            "negotiation_id": negotiation_id,
            "status": negotiation["status"],
            "terminal": True,
            "worked": True,
        }

    owner = str(lock_owner or f"negotiation_case_tick:{negotiation_id}")
    if store.acquire_negotiation_case_lock(
        negotiation_id,
        owner=owner,
        lease_ttl_seconds=lease_ttl_seconds,
    ):
        try:
            if send_message is None:
                from .tools import _FeishuClient

                sender = _FeishuClient()

                def _send_message(
                    attendee_open_ids: list[str], message: str
                ) -> str | None:
                    result = sender.send_attendee_message(
                        attendee_open_ids=attendee_open_ids,
                        message=message,
                    )
                    return (
                        str(result.get("message_id"))
                        if isinstance(result, dict)
                        else None
                    )

                send_message = _send_message

            result = _run_negotiation_case_tick(
                negotiation_id=negotiation_id,
                store=store,
                send_message=send_message,
            )
            negotiation = store.get_negotiation(negotiation_id)
            if _negotiation_is_terminal(negotiation):
                _sync_negotiation_kanban_task_body(
                    negotiation_id=negotiation_id,
                    store=store,
                    kanban=kanban,
                )
                return {
                    **result,
                    "terminal": True,
                }
            _sync_negotiation_kanban_task_body(
                negotiation_id=negotiation_id,
                store=store,
                kanban=kanban,
            )
            return {
                **result,
                "terminal": False,
                "worked": bool(result.get("worked", True)),
            }
        finally:
            store.release_negotiation_case_lock(negotiation_id, owner=owner)

    return {
        "negotiation_id": negotiation_id,
        "status": negotiation["status"],
        "terminal": False,
        "worked": False,
        "locked": False,
        "reason": "tick_lock_not_acquired",
    }


def _parse_kanban_task_body(raw_body: Any) -> dict[str, Any]:
    if isinstance(raw_body, dict):
        body = raw_body
    elif isinstance(raw_body, str):
        try:
            loaded = json.loads(raw_body)
        except json.JSONDecodeError as exc:
            raise ValueError("kanban task body must be valid JSON") from exc
        body = loaded if isinstance(loaded, dict) else {}
    else:
        body = {}
    metadata = body.get("metadata")
    if not isinstance(metadata, dict):
        raise ValueError("kanban task body missing metadata")
    if metadata.get("task_type") != "feishu_meeting_negotiation":
        raise ValueError("unsupported kanban task type")
    return body


def _resolve_kanban_worker_boundary(
    *,
    workspace_id: str,
    session_id: str,
    user_id: str | None = None,
) -> Any:
    from gateway.execution_boundary import (
        ExecutionBoundaryRequest,
        GovernedExecutionBoundaryRequired,
        resolve_execution_boundary,
    )

    boundary = resolve_execution_boundary(
        ExecutionBoundaryRequest(
            source="feishu_meeting_kanban_worker",
            session_id=session_id,
            user_id=user_id,
            workspace_id=workspace_id,
            metadata={
                "transport": "kanban_worker",
                "trusted_internal_boundary": True,
            },
            headers={
                "X-Hermes-Execution-Boundary-Trust": "semantier-internal",
            },
        )
    )
    if boundary is None:
        raise GovernedExecutionBoundaryRequired(
            "Execution boundary required for Feishu meeting Kanban worker"
        )
    policy = getattr(boundary, "policy", None)
    if bool(getattr(policy, "provider_fallback_enabled", False)):
        raise GovernedExecutionBoundaryRequired(
            "Feishu meeting Kanban worker requires provider fallback disabled"
        )
    return boundary


def _session_id_from_payload_json(raw_payload: Any) -> str:
    try:
        payload = json.loads(str(raw_payload or "{}"))
    except json.JSONDecodeError:
        return ""
    if not isinstance(payload, dict):
        return ""
    return str(payload.get("session_id") or "").strip()


def negotiation_kanban_worker_tick(
    payload: dict[str, Any],
    *,
    store: MeetingCoordinatorStore,
    kanban: KanbanClient,
    cron: CronClient | None = None,
    boundary_resolver: Any | None = None,
    tick_runner: Any | None = None,
) -> dict[str, Any]:
    task_id = str(payload.get("kanban_task_id") or payload.get("task_id") or "").strip()
    if not task_id:
        raise ValueError("kanban_task_id is required")
    body = _parse_kanban_task_body(payload.get("task_body") or payload.get("body"))
    metadata = body["metadata"]
    negotiation_id = str(
        metadata.get("negotiation_id") or payload.get("negotiation_id") or ""
    ).strip()
    workspace_id = str(metadata.get("workspace_id") or "").strip()
    session_id = str(
        metadata.get("session_id") or payload.get("session_id") or ""
    ).strip()
    if not negotiation_id:
        raise ValueError("kanban task metadata missing negotiation_id")
    if not workspace_id:
        raise ValueError("kanban task metadata missing workspace_id")
    negotiation = store.get_negotiation(negotiation_id)
    if str(negotiation["workspace_id"]) != workspace_id:
        raise PermissionError("kanban task workspace does not match negotiation")
    if not session_id:
        raise ValueError("kanban task metadata missing session_id")

    resolver = boundary_resolver or _resolve_kanban_worker_boundary
    boundary = resolver(
        workspace_id=workspace_id,
        session_id=session_id,
        user_id=str(payload.get("user_id") or "") or None,
    )
    policy = getattr(boundary, "policy", None)
    if bool(getattr(policy, "provider_fallback_enabled", False)):
        raise RuntimeError("kanban worker boundary provider fallback must be disabled")

    if str(negotiation.get("kanban_task_id") or "") not in {"", task_id}:
        raise PermissionError("kanban task does not match negotiation")
    if not str(negotiation.get("kanban_task_id") or ""):
        negotiation = store.set_negotiation_kanban_task(
            negotiation_id,
            kanban_task_id=task_id,
        )

    worker_owner = f"kanban:{task_id}"
    expired = store.expire_negotiation_if_due(
        negotiation_id,
        owner=worker_owner,
        now_utc=datetime.now(timezone.utc),
    )
    if expired.get("expired"):
        negotiation = expired["record"]
        tick_result = {
            "negotiation_id": negotiation_id,
            "status": negotiation["status"],
            "terminal": True,
            "expired": True,
        }
    elif not _negotiation_is_terminal(negotiation):
        runner = tick_runner or negotiation_case_tick
        tick_payload = {
            "negotiation_id": negotiation_id,
        }
        tick_result = runner(
            tick_payload,
            store=store,
            cron=cron,
            kanban=kanban,
        )
        negotiation = store.get_negotiation(negotiation_id)
    else:
        tick_result = {
            "negotiation_id": negotiation_id,
            "status": negotiation["status"],
            "terminal": True,
        }

    if _negotiation_is_terminal(negotiation):
        _sync_negotiation_kanban_task_body(
            negotiation_id=negotiation_id,
            store=store,
            kanban=kanban,
        )
        completed = kanban.complete(
            task_id,
            summary=f"Meeting negotiation {negotiation['status']}.",
            metadata={
                "negotiation_id": negotiation_id,
                "status": str(negotiation["status"]),
                "finalize_attempt_id": negotiation.get("finalize_attempt_id"),
            },
        )
        return {
            "negotiation_id": negotiation_id,
            "kanban_task_id": task_id,
            "status": negotiation["status"],
            "terminal": True,
            "kanban_completed": bool(completed),
            "tick_result": tick_result,
        }

    _sync_negotiation_kanban_task_body(
        negotiation_id=negotiation_id,
        store=store,
        kanban=kanban,
    )
    blocked = kanban.block(
        task_id,
        reason=f"Waiting for meeting negotiation reply; status={negotiation['status']}",
        kind="waiting_for_reply",
    )
    return {
        "negotiation_id": negotiation_id,
        "kanban_task_id": task_id,
        "status": negotiation["status"],
        "terminal": False,
        "kanban_blocked": bool(blocked),
        "tick_result": tick_result,
    }


def _utc_iso(value: str) -> str:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("slot timestamps must be timezone-aware")
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _reply_slot_payload(payload: dict[str, Any]) -> dict[str, str] | None:
    slot = payload.get("proposed_slot")
    if isinstance(slot, dict):
        start_time = slot.get("start_time")
        end_time = slot.get("end_time")
        timezone_name = str(slot.get("timezone") or payload.get("timezone") or "UTC")
        source_text = str(slot.get("source_text") or payload.get("reply_text") or "")
    else:
        start_time = payload.get("start_time")
        end_time = payload.get("end_time")
        timezone_name = str(payload.get("timezone") or "UTC")
        source_text = str(payload.get("reply_text") or "")
    if not start_time or not end_time:
        return None
    return {
        "start_time": _utc_iso(str(start_time)),
        "end_time": _utc_iso(str(end_time)),
        "timezone": timezone_name,
        "source_text": source_text,
    }


def submit_negotiation_reply(
    payload: dict[str, Any],
    *,
    store: MeetingCoordinatorStore,
    kanban: KanbanClient | None = None,
) -> dict[str, Any]:
    if (
        payload.get("callback_origin") is True
        and not str(payload.get("negotiation_id") or "").strip()
    ):
        return _submit_negotiation_callback_reply(payload, store=store, kanban=kanban)

    negotiation_id = str(payload.get("negotiation_id") or "").strip()
    participant_user_id = str(payload.get("participant_user_id") or "").strip()
    message_id = str(payload.get("message_id") or "").strip()
    if not negotiation_id:
        raise ValueError("negotiation_id is required")
    if not participant_user_id:
        raise ValueError("participant_user_id is required")
    if not message_id:
        raise ValueError("message_id is required")
    negotiation = store.get_negotiation(negotiation_id)
    if _negotiation_is_terminal(negotiation):
        store.record_inbound_reply_rejected(
            negotiation_id=negotiation_id,
            participant_user_id=participant_user_id,
            message_id=message_id,
            reason="terminal_negotiation",
        )
        raise ValueError("terminal_negotiation")
    if negotiation["status"] not in {
        "pending_decliner_input",
        "collecting_votes",
        "awaiting_requester_decision",
    }:
        store.record_inbound_reply_rejected(
            negotiation_id=negotiation_id,
            participant_user_id=participant_user_id,
            message_id=message_id,
            reason="non_reply_accepting_state",
        )
        raise ValueError("non_reply_accepting_state")
    participants = store.list_negotiation_participants(negotiation_id)
    participant_by_id = {str(item["attendee_user_id"]): item for item in participants}
    if participant_user_id not in participant_by_id:
        store.record_inbound_reply_rejected(
            negotiation_id=negotiation_id,
            participant_user_id=participant_user_id,
            message_id=message_id,
            reason="unknown_sender",
        )
        raise PermissionError("unknown_sender")
    accepted = store.record_inbound_reply_accepted(
        negotiation_id=negotiation_id,
        participant_user_id=participant_user_id,
        message_id=message_id,
        message_type="freeform_reply",
        payload={
            "reply_text": str(payload.get("reply_text") or ""),
            "intent": str(payload.get("intent") or payload.get("vote") or ""),
        },
    )
    kanban_wakeup = _kanban_comment_and_unblock_for_reply(
        negotiation=negotiation,
        accepted_message=accepted,
        payload=payload,
        store=store,
        kanban=kanban,
    )

    def reply_result(**values: Any) -> dict[str, Any]:
        _sync_negotiation_kanban_task_body(
            negotiation_id=negotiation_id,
            store=store,
            kanban=kanban,
        )
        return {"accepted": True, **values, **kanban_wakeup}

    intent = str(payload.get("intent") or "").strip().lower()
    vote_value = str(payload.get("vote") or "").strip().lower()
    if intent in {"vote_yes", "yes", "accept", "accepted"}:
        vote_value = "yes"
    elif intent in {"vote_no", "no", "decline", "declined"}:
        vote_value = "no"
    elif intent in {"propose_slots", "propose_alternative", "alternative"}:
        vote_value = "propose_alternative" if payload.get("slot_id") else ""

    slot_payload = _reply_slot_payload(payload)
    if negotiation["status"] == "pending_decliner_input":
        if slot_payload is None:
            return reply_result(
                message_event_id=accepted["message_event_id"],
                clarification_required=True,
                reason="missing_normalized_slot",
            )
        slot = store.add_candidate_slot(
            negotiation_id,
            proposed_by_user_id=participant_user_id,
            round_number=max(1, int(negotiation["current_round"] or 0) + 1),
            start_time=slot_payload["start_time"],
            end_time=slot_payload["end_time"],
            timezone_name=slot_payload["timezone"],
            source_text=slot_payload["source_text"],
        )
        store.update_negotiation_participant_response(
            negotiation_id=negotiation_id,
            attendee_user_id=participant_user_id,
            latest_response_status="proposed_slot",
            latest_slot_id=slot["slot_id"],
        )
        owner = f"system:reply:{message_id}"
        store.transition_negotiation_state(
            negotiation_id,
            expected_state=str(negotiation["status"]),
            next_state="collecting_votes",
            patch={"current_round": int(slot["round_number"])},
            actor_id=owner,
        )
        return reply_result(
            message_event_id=accepted["message_event_id"],
            slot=slot,
            next_state="collecting_votes",
        )

    if negotiation["status"] == "awaiting_requester_decision":
        if participant_user_id != negotiation["creator_user_id"]:
            raise PermissionError("requester_decision_required")
        action = intent
        if intent in {"keep_original", "keep_original_time"}:
            action = "requester_keep_original"
        elif intent in {"select_slot", "select_time"}:
            action = "requester_select_slot"
        slot_id = str(
            payload.get("slot_id") or payload.get("selected_slot_id") or ""
        ).strip()
        decision = _apply_requester_decision(
            negotiation=negotiation,
            store=store,
            action=action,
            participant_user_id=participant_user_id,
            slot_id=slot_id,
            kanban=kanban,
        )
        return reply_result(
            message_event_id=accepted["message_event_id"],
            **decision,
        )

    slot_id = str(payload.get("slot_id") or "").strip()
    alternative_slot_id: str | None = None
    if vote_value == "propose_alternative" or (
        vote_value == "no" and slot_payload is not None
    ):
        if slot_payload is None:
            return reply_result(
                message_event_id=accepted["message_event_id"],
                clarification_required=True,
                reason="missing_alternative_slot",
            )
        next_round = int(negotiation["current_round"] or 0) + 1
        if next_round > int(negotiation["max_rounds"] or 1):
            owner = f"system:reply:{message_id}"
            store.transition_negotiation_state(
                negotiation_id,
                expected_state=str(negotiation["status"]),
                next_state="awaiting_requester_decision",
                patch={},
                actor_id=owner,
            )
            return reply_result(next_state="awaiting_requester_decision")
        alt_slot = store.add_candidate_slot(
            negotiation_id,
            proposed_by_user_id=participant_user_id,
            round_number=next_round,
            start_time=slot_payload["start_time"],
            end_time=slot_payload["end_time"],
            timezone_name=slot_payload["timezone"],
            source_text=slot_payload["source_text"],
        )
        alternative_slot_id = str(alt_slot["slot_id"])
        slot_id = slot_id or alternative_slot_id
        store.update_negotiation_participant_response(
            negotiation_id=negotiation_id,
            attendee_user_id=participant_user_id,
            latest_response_status="proposed_slot",
            latest_slot_id=alternative_slot_id,
        )
        owner = f"system:reply:{message_id}"
        store.transition_negotiation_state(
            negotiation_id,
            expected_state=str(negotiation["status"]),
            next_state="collecting_votes",
            patch={"current_round": next_round},
            actor_id=owner,
        )
        return reply_result(
            message_event_id=accepted["message_event_id"],
            alternative_slot=alt_slot,
            next_state="collecting_votes",
        )

    if vote_value not in {"yes", "no"} or not slot_id:
        return reply_result(
            message_event_id=accepted["message_event_id"],
            clarification_required=True,
            reason="missing_vote_or_slot",
        )
    vote = store.record_vote(
        negotiation_id=negotiation_id,
        slot_id=slot_id,
        attendee_user_id=participant_user_id,
        vote=vote_value,
        alternative_slot_id=alternative_slot_id,
        note=str(payload.get("reply_text") or "") or None,
    )
    store.update_negotiation_participant_response(
        negotiation_id=negotiation_id,
        attendee_user_id=participant_user_id,
        latest_response_status="accepted_slot"
        if vote_value == "yes"
        else "declined_slot",
        latest_slot_id=slot_id,
    )
    if vote_value == "yes" and store.required_participants_have_yes(
        negotiation_id=negotiation_id,
        slot_id=slot_id,
    ):
        selected_slot = store.get_candidate_slot(slot_id)
        owner = f"system:reply:{message_id}"
        store.transition_negotiation_state(
            negotiation_id,
            expected_state=str(negotiation["status"]),
            next_state="consented",
            patch={
                "selected_slot_json": json.dumps(
                    {
                        "slot_id": slot_id,
                        "start_time": selected_slot["start_time"],
                        "end_time": selected_slot["end_time"],
                        "timezone": selected_slot["timezone"],
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
            },
            actor_id=owner,
        )
        completed = _complete_kanban_if_terminal(
            negotiation_id=negotiation_id,
            store=store,
            kanban=kanban,
            summary="All required participants consented to a meeting time.",
        )
        return reply_result(
            vote=vote, next_state="consented", kanban_completed=completed
        )
    return reply_result(vote=vote, next_state="collecting_votes")


def apply_requester_decision(
    payload: dict[str, Any],
    *,
    store: MeetingCoordinatorStore,
    kanban: KanbanClient | None = None,
    cron: CronClient | None = None,
) -> dict[str, Any]:
    negotiation_id = str(payload.get("negotiation_id") or "").strip()
    action = str(payload.get("action") or "").strip()
    requested_by_user_id = str(payload.get("requested_by_user_id") or "").strip()
    if not negotiation_id:
        raise ValueError("negotiation_id is required")
    if not action:
        raise ValueError("action is required")
    if not requested_by_user_id:
        raise ValueError("requested_by_user_id is required")
    negotiation = store.get_negotiation(negotiation_id)
    slot_id = str(payload.get("slot_id") or payload.get("selected_slot_id") or "").strip()
    if action == "requester_cancel":
        return _apply_requester_decision(
            negotiation=negotiation,
            store=store,
            action=action,
            participant_user_id=requested_by_user_id,
            slot_id=slot_id,
            kanban=kanban,
            cron=cron,
        )
    if action in {"requester_keep_original", "keep_original"}:
        return _apply_requester_decision(
            negotiation=negotiation,
            store=store,
            action="requester_keep_original",
            participant_user_id=requested_by_user_id,
            slot_id=slot_id,
            kanban=kanban,
            cron=cron,
        )
    if action in {"requester_select_slot", "requester_select_time", "select_slot"}:
        return _apply_requester_decision(
            negotiation=negotiation,
            store=store,
            action="requester_select_slot",
            participant_user_id=requested_by_user_id,
            slot_id=slot_id,
            kanban=kanban,
            cron=cron,
        )
    raise ValueError("invalid_requester_action")


def _submit_negotiation_callback_reply(
    payload: dict[str, Any],
    *,
    store: MeetingCoordinatorStore,
    kanban: KanbanClient | None = None,
) -> dict[str, Any]:
    if payload.get("callback_signature_valid") is not True:
        return {"status": "rejected", "reason": "invalid_signature"}
    root_message_id = str(
        payload.get("root_message_id")
        or payload.get("thread_id")
        or payload.get("outbound_provider_message_id")
        or ""
    ).strip()
    provider_message_id = str(payload.get("provider_message_id") or "").strip()
    sender_open_id = str(payload.get("sender_open_id") or "").strip()
    workspace_id = str(payload.get("workspace_id") or "").strip()
    if not root_message_id:
        return {"status": "not_correlated", "reason": "missing_root_message_id"}
    if not provider_message_id:
        return {"status": "rejected", "reason": "missing_provider_message_id"}
    if not sender_open_id:
        return {"status": "rejected", "reason": "unknown_sender"}
    try:
        outbound = store.get_outbound_negotiation_message_by_provider_id(
            provider_message_id=root_message_id
        )
    except KeyError:
        return {"status": "not_correlated", "reason": "outbound_not_found"}
    negotiation = store.get_negotiation(str(outbound["negotiation_id"]))
    participant_user_id = str(outbound["participant_user_id"])
    if workspace_id and str(negotiation["workspace_id"]) != workspace_id:
        store.record_inbound_reply_rejected(
            negotiation_id=str(negotiation["negotiation_id"]),
            participant_user_id=sender_open_id,
            message_id=provider_message_id,
            reason="wrong_workspace",
        )
        return {"status": "rejected", "reason": "wrong_workspace"}
    participants = store.list_negotiation_participants(
        str(negotiation["negotiation_id"])
    )
    participant = next(
        (
            item
            for item in participants
            if str(item["attendee_user_id"]) == participant_user_id
        ),
        None,
    )
    allowed_sender_ids = {
        participant_user_id,
        str(participant.get("message_user_id") or "") if participant else "",
    }
    if sender_open_id not in allowed_sender_ids:
        store.record_inbound_reply_rejected(
            negotiation_id=str(negotiation["negotiation_id"]),
            participant_user_id=sender_open_id,
            message_id=provider_message_id,
            reason="uncorrelated_message",
        )
        return {"status": "rejected", "reason": "uncorrelated_message"}
    result = submit_negotiation_reply(
        {
            **payload,
            "negotiation_id": str(negotiation["negotiation_id"]),
            "participant_user_id": participant_user_id,
            "message_id": provider_message_id,
            "reply_text": str(
                payload.get("raw_text") or payload.get("reply_text") or ""
            ),
            "outbound_message_event_id": str(outbound["message_event_id"]),
        },
        store=store,
        kanban=kanban,
    )
    return {"status": "accepted", **result}


def finalize_negotiation_case(
    payload: dict[str, Any],
    *,
    store: MeetingCoordinatorStore,
    calendar_client: CalendarUpdateClient,
    cron: CronClient | None = None,
    kanban: KanbanClient | None = None,
    lock_ttl_seconds: int = NEGOTIATION_CASE_LOCK_TTL_SECONDS,
) -> dict[str, Any]:
    negotiation_id = str(payload.get("negotiation_id") or "").strip()
    selected_slot_id = str(payload.get("selected_slot_id") or "").strip()
    decision_source = str(payload.get("decision_source") or "").strip()
    requested_by_user_id = str(payload.get("requested_by_user_id") or "").strip()
    if not negotiation_id:
        raise ValueError("negotiation_id is required")
    if decision_source not in {"consent", "requester_final_decision"}:
        raise ValueError("invalid decision_source")
    if not requested_by_user_id:
        raise ValueError("requested_by_user_id is required")
    if payload.get("requester_confirmation") is not True:
        raise PermissionError("requester_confirmation_required")

    negotiation = store.get_negotiation(negotiation_id)
    owner = f"requester:{requested_by_user_id}"
    if not store.acquire_negotiation_case_lock(
        negotiation_id,
        owner=owner,
        lease_ttl_seconds=lock_ttl_seconds,
    ):
        return {
            "attempt": None,
            "calendar_update_called": False,
            "locked": False,
            "reason": "tick_lock_not_acquired",
        }

    _record_negotiation_event_safely(
        store=store,
        negotiation_id=negotiation_id,
        event_type="FINALIZE_STARTED",
        actor_type="requester",
        actor_id=owner,
        payload={"decision_source": decision_source, "selected_slot_id": selected_slot_id},
    )

    try:
        def _finalize_return(values: dict[str, Any]) -> dict[str, Any]:
            _sync_negotiation_kanban_task_body(
                negotiation_id=negotiation_id,
                store=store,
                kanban=kanban,
            )
            return values

        keep_original = False
        slot: dict[str, Any] = {}
        selected_slot_payload: dict[str, Any] = {}
        if decision_source == "requester_final_decision":
            try:
                selected_slot_payload = json.loads(
                    str(negotiation.get("selected_slot_json") or "{}")
                )
                if not isinstance(selected_slot_payload, dict):
                    selected_slot_payload = {}
            except json.JSONDecodeError:
                selected_slot_payload = {}
            keep_original = str(selected_slot_payload.get("calendar_update") or "").strip().lower() in {
                "false",
                "0",
                "no",
            }
            if keep_original:
                selected_slot_id = selected_slot_id or f"requester_keep_original:{negotiation_id}"
                slot = {
                    "slot_id": selected_slot_id,
                    "start_time": str(negotiation["original_start_time"]),
                    "end_time": str(negotiation["original_end_time"]),
                    "timezone": str(negotiation["timezone"]),
                }
            else:
                if not selected_slot_id:
                    selected_slot_id = str(selected_slot_payload.get("slot_id") or "").strip()
                if not selected_slot_id:
                    raise ValueError("selected_slot_id is required")
                slot = store.get_candidate_slot(selected_slot_id)
                if str(slot.get("negotiation_id") or "") != negotiation_id:
                    raise ValueError("selected slot does not belong to negotiation")
        else:
            if not selected_slot_id:
                raise ValueError("selected_slot_id is required")
            slot = store.get_candidate_slot(selected_slot_id)
            if str(slot.get("negotiation_id") or "") != negotiation_id:
                raise ValueError("selected slot does not belong to negotiation")

        if not keep_original:
            store.verify_negotiation_finalization(
                negotiation_id=negotiation_id,
                selected_slot_id=selected_slot_id,
                decision_source=decision_source,
                requested_by_user_id=requested_by_user_id,
            )

        update_payload = {
            "event_id": negotiation["event_id"],
            "calendar_id": negotiation["calendar_id"],
            "start_time": slot["start_time"],
            "end_time": slot["end_time"],
            "timezone": slot["timezone"],
        }
        attempt = store.create_finalize_attempt(
            negotiation_id=negotiation_id,
            selected_slot_id=selected_slot_id,
            decision_source=decision_source,
            requested_by_user_id=requested_by_user_id,
            calendar_update_payload=update_payload,
        )
        store.set_negotiation_finalize_attempt(
            negotiation_id, attempt["finalize_attempt_id"]
        )
        if attempt["status"] == "calendar_update_succeeded":
            finalization = {
                "attempt": attempt,
                "calendar_update_called": False,
                "idempotent": True,
            }
            stop_result = _stop_followup_cron_if_terminal(
                negotiation_id=negotiation_id,
                store=store,
                cron=cron,
                kanban=kanban,
                reason="finalize_idempotent",
            )
            if stop_result:
                finalization["followup_cron_stopped"] = True
                finalization["followup_cron_stop"] = stop_result
            return _finalize_return(finalization)

        if attempt["status"] == "calendar_update_started":
            return _finalize_return({
                "attempt": attempt,
                "calendar_update_called": False,
                "manual_reconciliation_required": True,
            })

        if attempt["status"] == "calendar_update_failed_retryable":
            now = datetime.now(timezone.utc)
            if not store.finalize_attempt_retry_due(
                attempt["finalize_attempt_id"], now_utc=now
            ):
                return _finalize_return({
                    "attempt": attempt,
                    "calendar_update_called": False,
                    "retry_not_due": True,
                })

        if attempt["status"] == "calendar_update_failed_permanent":
            stop_result = _stop_followup_cron_if_terminal(
                negotiation_id=negotiation_id,
                store=store,
                cron=cron,
                kanban=kanban,
                reason="finalize_failed_permanent",
            )
            return _finalize_return({
                "attempt": attempt,
                "calendar_update_called": False,
                "permanent_failure": True,
                **({"followup_cron_stopped": bool(stop_result), "followup_cron_stop": stop_result}
                   if stop_result
                   else {}),
            })

        if keep_original:
            succeeded = store.mark_finalize_attempt_succeeded(
                attempt["finalize_attempt_id"],
                result={"calendar_update_skipped": True},
            )
            stop_result = _stop_followup_cron_if_terminal(
                negotiation_id=negotiation_id,
                store=store,
                cron=cron,
                kanban=kanban,
                reason="requester_keep_original",
            )
            completed = _complete_kanban_if_terminal(
                negotiation_id=negotiation_id,
                store=store,
                kanban=kanban,
                summary="Meeting time negotiation finalized by requester while skipping calendar update.",
            )
            return _finalize_return({
                "attempt": succeeded,
                "calendar_update_called": False,
                "calendar_update_skipped": True,
                "kanban_completed": completed,
                **({"followup_cron_stopped": True, "followup_cron_stop": stop_result}
                   if stop_result
                   else {}),
            })

        if hasattr(calendar_client, "get_event_revision_id"):
            current_revision = calendar_client.get_event_revision_id(  # type: ignore[attr-defined]
                event_id=negotiation["event_id"],
                calendar_id=negotiation["calendar_id"],
            )
            if str(current_revision or "") != str(negotiation["event_revision_id"]):
                failed = store.mark_finalize_attempt_failed(
                    attempt["finalize_attempt_id"],
                    retryable=False,
                    detail={
                        "failure_reason": "stale_meeting_revision",
                        "current_event_revision_id": current_revision,
                        "expected_event_revision_id": negotiation["event_revision_id"],
                    },
                )
                store.mark_negotiation_finalization_failed(
                    negotiation_id,
                    failure_reason="stale_meeting_revision",
                    finalize_status="failed_permanent",
                )
                stop_result = _stop_followup_cron_if_terminal(
                    negotiation_id=negotiation_id,
                    store=store,
                    cron=cron,
                    kanban=kanban,
                    reason="finalize_stale_revision",
                )
                completed = _complete_kanban_if_terminal(
                    negotiation_id=negotiation_id,
                    store=store,
                    kanban=kanban,
                    summary="Meeting time finalization failed because the calendar revision was stale.",
                )
                return _finalize_return({
                    "attempt": failed,
                    "calendar_update_called": False,
                    "stale_meeting_revision": True,
                    "kanban_completed": completed,
                    **({"followup_cron_stopped": bool(stop_result), "followup_cron_stop": stop_result}
                       if stop_result
                       else {}),
                })

        started = store.mark_finalize_attempt_started(attempt["finalize_attempt_id"])
        try:
            result = calendar_client.update_meeting_time(**update_payload)
        except Exception as exc:
            failed = store.mark_finalize_attempt_failed(
                attempt["finalize_attempt_id"],
                retryable=True,
                detail={"error": str(exc)},
                next_retry_at=datetime.now(timezone.utc) + timedelta(minutes=2),
            )
            return _finalize_return({
                "attempt": failed,
                "calendar_update_called": True,
                "error": str(exc),
            })

        succeeded = store.mark_finalize_attempt_succeeded(
            started["finalize_attempt_id"],
            result=result,
        )
        followup_monitor: dict[str, Any] | None = None
        try:
            negotiation_payload = json.loads(str(negotiation.get("payload_json") or "{}"))
        except json.JSONDecodeError:
            negotiation_payload = {}
        start_followup_monitor = bool(
            payload.get("start_rsvp_monitor_after_update")
            or negotiation_payload.get("start_rsvp_monitor_after_update")
        )
        if start_followup_monitor:
            if cron is None:
                raise RuntimeError("cron is required to start follow-up RSVP monitor")
            next_revision = str(
                result.get("event_revision_id")
                or result.get("revision")
                or result.get("new_revision")
                or ""
            ).strip()
            if not next_revision:
                digest = hashlib.sha256(
                    json.dumps(
                        [
                            "meeting_time_followup_revision:v1",
                            negotiation_id,
                            succeeded["finalize_attempt_id"],
                            slot["start_time"],
                            slot["end_time"],
                        ],
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode("utf-8")
                ).hexdigest()[:24]
                next_revision = f"rev_{digest}"
            attendees = [
                {
                    "user_id": str(participant["attendee_user_id"]),
                    "message_user_id": participant.get("message_user_id"),
                    "display_name": participant.get("display_name"),
                }
                for participant in store.list_negotiation_participants(negotiation_id)
                if str(participant.get("role") or "") != "requester"
            ]
            monitor_payload = {
                **negotiation_payload,
                "workspace_id": negotiation["workspace_id"],
                "creator_user_id": negotiation["creator_user_id"],
                "event_id": negotiation["event_id"],
                "event_revision_id": next_revision,
                "calendar_id": negotiation["calendar_id"],
                "creator_delivery_binding": json.loads(
                    str(negotiation["creator_delivery_binding_json"] or "{}")
                ),
                "start_time": slot["start_time"],
                "end_time": slot["end_time"],
                "timezone": slot["timezone"],
                "attendees": attendees,
                "source_negotiation_id": negotiation_id,
                "source_finalize_attempt_id": succeeded["finalize_attempt_id"],
            }
            followup_monitor = start_monitor(
                monitor_payload,
                store=store,
                cron=cron,
            )

        stop_result = _stop_followup_cron_if_terminal(
            negotiation_id=negotiation_id,
            store=store,
            cron=cron,
            kanban=kanban,
            reason="finalize_with_calendar_update",
        )
        completed = _complete_kanban_if_terminal(
            negotiation_id=negotiation_id,
            store=store,
            kanban=kanban,
            summary="Meeting time negotiation finalized and calendar update succeeded.",
        )
        result_payload = {
            "attempt": succeeded,
            "calendar_update_called": True,
            "result": result,
            "kanban_completed": completed,
            **({"followup_monitor": followup_monitor} if followup_monitor else {}),
            "followup_cron_stopped": bool(stop_result),
            "followup_cron_stop": stop_result,
        }
        _record_negotiation_event_safely(
            store=store,
            negotiation_id=negotiation_id,
            event_type="FINALIZE_COMPLETED",
            actor_type="requester",
            actor_id=owner,
            payload={"decision_source": decision_source},
            next_state=str(store.get_negotiation(negotiation_id).get("status")),
        )
        return _finalize_return(result_payload)
    finally:
        store.release_negotiation_case_lock(negotiation_id, owner=owner)


def _deliver_creator_task(
    task: dict[str, Any],
    *,
    store: MeetingCoordinatorStore,
    delivery_client: DeliveryClient | None,
) -> bool:
    if delivery_client is None:
        return False
    try:
        delivery_client.send_creator_escalation(task)
    except Exception as exc:
        store.mark_delivery_task_attempt_failed(
            task["delivery_task_id"],
            retryable=True,
            detail=str(exc),
        )
        return False
    store.mark_delivery_task_sent(
        task["delivery_task_id"],
        detail="creator escalation sent",
    )
    store.mark_escalations_for_delivery_task(
        task["delivery_task_id"],
        status="sent",
    )
    return True


def _complete_all_exhausted_unanswered(
    monitor: dict[str, Any],
    attendees: list[dict[str, Any]],
    *,
    store: MeetingCoordinatorStore,
    cron: CronClient | None,
    delivery_client: DeliveryClient | None,
    kanban: KanbanClient | None = None,
) -> dict[str, Any]:
    reason = "all_attendees_followup_limit_reached"
    message = _render_cancel_suggestion(monitor, attendees)
    task = store.create_delivery_task(
        monitor_id=monitor["monitor_id"],
        task_type="creator_escalation",
        target_user_id=monitor["creator_user_id"],
        delivery_binding=json.loads(monitor["creator_delivery_binding_json"]),
        payload={
            "attendee_user_ids": [str(item["attendee_user_id"]) for item in attendees],
            "reason": reason,
            "message": message,
        },
    )
    delivered = _deliver_creator_task(
        task,
        store=store,
        delivery_client=delivery_client,
    )
    if not delivered and cron is not None:
        try:
            ensure_delivery_retry_cron(workspace_id=monitor["workspace_id"], cron=cron)
        except Exception as exc:
            store.mark_delivery_retry_scheduler_unavailable(
                workspace_id=monitor["workspace_id"],
                detail=str(exc),
            )
    for attendee in attendees:
        if str(attendee.get("delivery_status") or "") != "escalated":
            store.mark_attendee_escalated(
                monitor["monitor_id"],
                attendee_user_id=str(attendee["attendee_user_id"]),
                creator_user_id=monitor["creator_user_id"],
                reason=reason,
                delivery_task_id=task["delivery_task_id"],
                status="sent" if delivered else "pending",
            )
    completed = store.mark_monitor_complete(monitor["monitor_id"])
    cleaned = _cleanup_monitor_owned_kanban_tasks(
        completed,
        store=store,
        kanban=kanban,
        reason="monitor_complete_all_exhausted",
    )
    _dismiss_monitor_cron(completed, cron)
    return {
        "monitor_id": monitor["monitor_id"],
        "status": "complete",
        "all_responded": False,
        "all_exhausted": True,
        "suggest_cancel": True,
        "pending_attendees": [str(item["attendee_user_id"]) for item in attendees],
        "followups_sent": 0,
        "escalations_sent": 1,
        "creator_notification_sent": delivered,
        "kanban_cleanup": cleaned,
    }


def monitor_tick(
    payload: dict[str, Any],
    *,
    store: MeetingCoordinatorStore,
    feishu_client: Any,
    cron: CronClient | None = None,
    delivery_client: DeliveryClient | None = None,
    kanban: KanbanClient | None = None,
) -> dict[str, Any]:
    monitor = store.get_monitor(str(payload["monitor_id"]))
    if _monitor_is_terminal(monitor):
        cleaned = _cleanup_monitor_owned_kanban_tasks(
            monitor,
            store=store,
            kanban=kanban,
            reason="monitor_already_terminal",
        )
        _dismiss_monitor_cron(monitor, cron)
        return {
            "monitor_id": monitor["monitor_id"],
            "status": str(monitor.get("status") or "complete"),
            "terminal": True,
            "pending_attendees": [],
            "followups_sent": 0,
            "escalations_sent": 0,
            "kanban_cleanup": cleaned,
        }
    interval_minutes = _followup_interval_minutes(payload, monitor, cron)
    if "max_followups" in payload and payload.get("max_followups") is not None:
        max_followups = int(payload.get("max_followups") or 0)
    else:
        state = store.get_workspace_state(str(monitor["workspace_id"]))
        max_followups = int(state.get("max_followups") or 3)
    live_status = feishu_client.get_attendee_response_statuses(
        calendar_id=monitor["calendar_id"],
        event_id=monitor["event_id"],
    )
    store.update_attendee_statuses(monitor["monitor_id"], live_status)
    negotiation_ids: list[str] = []
    negotiation_kanban_errors: list[str] = []
    for attendee in store.list_new_declined_attendees_requiring_negotiation(
        monitor["monitor_id"]
    ):
        negotiation = store.create_or_get_negotiation_case(
            monitor_id=monitor["monitor_id"],
            event_revision_id=monitor["event_revision_id"],
            trigger_attendee_user_id=str(attendee["attendee_user_id"]),
        )
        negotiation_ids.append(str(negotiation["negotiation_id"]))
        try:
            negotiation = ensure_negotiation_kanban_task(
                negotiation_id=str(negotiation["negotiation_id"]),
                store=store,
                kanban=kanban,
                session_id=_session_id_from_payload_json(monitor.get("payload_json"))
                or None,
            )
            try:
                ensure_negotiation_followup_cron(
                    negotiation_id=str(negotiation["negotiation_id"]),
                    store=store,
                    cron=cron,
                    kanban=kanban,
                )
            except Exception as exc:
                negotiation_kanban_errors.append(str(exc))
            store.mark_monitor_negotiating(
                monitor["monitor_id"],
                negotiation_id=str(negotiation["negotiation_id"]),
            )
        except Exception as exc:
            negotiation_kanban_errors.append(str(exc))
    if negotiation_ids and not negotiation_kanban_errors:
        negotiating = store.mark_monitor_negotiating(
            monitor["monitor_id"],
            negotiation_id=negotiation_ids[0],
        )
        if cron is not None:
            _dismiss_monitor_cron(negotiating, cron)
        kanban_task_ids = []
        for negotiation_id in sorted(set(negotiation_ids)):
            task_id = str(
                store.get_negotiation(negotiation_id).get("kanban_task_id") or ""
            )
            if task_id:
                kanban_task_ids.append(task_id)
        result = {
            "monitor_id": monitor["monitor_id"],
            "status": "negotiating",
            "negotiation_ids": sorted(set(negotiation_ids)),
            "kanban_task_ids": kanban_task_ids,
            "all_responded": False,
            "all_exhausted": False,
            "pending_attendees": [],
            "followups_sent": 0,
            "escalations_sent": 0,
        }
        return result
    if negotiation_ids and negotiation_kanban_errors:
        cleaned = _cleanup_monitor_owned_kanban_tasks(
            monitor,
            store=store,
            kanban=kanban,
            reason="negotiation_handoff_failed",
        )
        return {
            "monitor_id": monitor["monitor_id"],
            "status": "negotiation_handoff_failed",
            "negotiation_ids": sorted(set(negotiation_ids)),
            "negotiation_kanban_errors": negotiation_kanban_errors,
            "all_responded": False,
            "all_exhausted": False,
            "pending_attendees": [],
            "followups_sent": 0,
            "escalations_sent": 0,
            "kanban_cleanup": cleaned,
        }
    attendees = store.list_attendees(monitor["monitor_id"])
    if _all_terminal(attendees):
        completed = store.mark_monitor_complete(monitor["monitor_id"])
        cleaned = _cleanup_monitor_owned_kanban_tasks(
            completed,
            store=store,
            kanban=kanban,
            reason="monitor_complete_all_responded",
        )
        _dismiss_monitor_cron(completed, cron)
        return {
            "monitor_id": monitor["monitor_id"],
            "status": "complete",
            "all_responded": True,
            "all_exhausted": False,
            "pending_attendees": [],
            "followups_sent": 0,
            "escalations_sent": 0,
            "kanban_cleanup": cleaned,
        }

    if _all_exhausted_unanswered(attendees, max_followups=max_followups):
        return _complete_all_exhausted_unanswered(
            monitor,
            attendees,
            store=store,
            cron=cron,
            delivery_client=delivery_client,
            kanban=kanban,
        )

    pending = store.list_pending_followup_attendees(monitor["monitor_id"])

    if not pending:
        completed = store.mark_monitor_complete(monitor["monitor_id"])
        cleaned = _cleanup_monitor_owned_kanban_tasks(
            completed,
            store=store,
            kanban=kanban,
            reason="monitor_complete_no_pending_attendees",
        )
        _dismiss_monitor_cron(completed, cron)
        return {
            "monitor_id": monitor["monitor_id"],
            "status": "complete",
            "all_responded": _all_terminal(attendees),
            "all_exhausted": False,
            "pending_attendees": [],
            "followups_sent": 0,
            "escalations_sent": 0,
            "kanban_cleanup": cleaned,
        }

    followups_sent = 0
    escalations_sent = 0
    for attendee in pending:
        attendee_user_id = str(attendee["attendee_user_id"])
        if int(attendee["followup_count"] or 0) >= max_followups:
            message = _render_creator_escalation(
                monitor,
                attendee,
                reason="followup_limit_reached",
            )
            if cron is not None:
                task = create_creator_escalation_task(
                    monitor_id=monitor["monitor_id"],
                    attendee_user_id=attendee_user_id,
                    reason="followup_limit_reached",
                    store=store,
                    cron=cron,
                    message=message,
                    ensure_retry_cron=False,
                )
            else:
                task = store.create_delivery_task(
                    monitor_id=monitor["monitor_id"],
                    task_type="creator_escalation",
                    target_user_id=monitor["creator_user_id"],
                    delivery_binding=json.loads(
                        monitor["creator_delivery_binding_json"]
                    ),
                    payload={
                        "attendee_user_id": attendee_user_id,
                        "reason": "followup_limit_reached",
                        "message": message,
                    },
                )
            delivered = _deliver_creator_task(
                task,
                store=store,
                delivery_client=delivery_client,
            )
            if not delivered and cron is not None:
                try:
                    ensure_delivery_retry_cron(
                        workspace_id=monitor["workspace_id"], cron=cron
                    )
                except Exception as exc:
                    store.mark_delivery_retry_scheduler_unavailable(
                        workspace_id=monitor["workspace_id"],
                        detail=str(exc),
                    )
            store.mark_attendee_escalated(
                monitor["monitor_id"],
                attendee_user_id=attendee_user_id,
                creator_user_id=monitor["creator_user_id"],
                reason="followup_limit_reached",
                delivery_task_id=task["delivery_task_id"],
                status="sent" if delivered else "pending",
            )
            escalations_sent += 1
            continue

        if not _followup_due(attendee, interval_minutes=interval_minutes):
            continue

        target_id = str(attendee.get("message_user_id") or attendee_user_id)
        result = feishu_client.send_attendee_message(
            attendee_open_ids=[target_id],
            message=_render_reminder(monitor, attendee),
        )
        delivered = result.get("delivered") or []
        failed = result.get("failed") or []
        if delivered:
            store.record_followup_attempt(
                monitor["monitor_id"],
                attendee_user_id=attendee_user_id,
                channel="feishu",
                target_id=target_id,
                status="sent",
                message_id=None,
                error_detail=None,
            )
            followups_sent += 1
        elif failed:
            store.record_followup_attempt(
                monitor["monitor_id"],
                attendee_user_id=attendee_user_id,
                channel="feishu",
                target_id=target_id,
                status="failed",
                message_id=None,
                error_detail=json.dumps(failed, ensure_ascii=False, sort_keys=True),
            )

    refreshed_attendees = store.list_attendees(monitor["monitor_id"])
    if (
        followups_sent > 0
        and escalations_sent == 0
        and _all_exhausted_unanswered(
            refreshed_attendees,
            max_followups=max_followups,
        )
    ):
        result = _complete_all_exhausted_unanswered(
            monitor,
            refreshed_attendees,
            store=store,
            cron=cron,
            delivery_client=delivery_client,
        )
        result["followups_sent"] = followups_sent
        return result

    remaining = store.list_pending_followup_attendees(monitor["monitor_id"])
    return {
        "monitor_id": monitor["monitor_id"],
        "status": "active",
        "all_responded": False,
        "all_exhausted": False,
        "pending_attendees": [str(item["attendee_user_id"]) for item in remaining],
        "followups_sent": followups_sent,
        "escalations_sent": escalations_sent,
    }


def monitor_stop(
    payload: dict[str, Any],
    *,
    store: MeetingCoordinatorStore,
    cron: CronClient,
    kanban: KanbanClient | None = None,
) -> dict[str, Any]:
    monitor_id = str(payload["monitor_id"])
    monitor = store.get_monitor(monitor_id)
    _dismiss_monitor_cron(monitor, cron)
    reason = str(payload.get("reason") or "operator stop")
    cancelled = store.mark_monitor_cancelled(monitor_id, detail=reason)
    cleaned = _cleanup_monitor_owned_kanban_tasks(
        cancelled,
        store=store,
        kanban=kanban,
        reason=f"monitor_stop:{reason}",
    )
    return {
        "monitor_id": monitor_id,
        "stopped": True,
        "status": cancelled["status"],
        "kanban_cleanup": cleaned,
    }


def escalation_retry_tick(
    payload: dict[str, Any],
    *,
    store: MeetingCoordinatorStore,
    delivery_client: Any,
) -> dict[str, Any]:
    workspace_id = str(payload["workspace_id"])
    due_tasks = store.list_due_delivery_tasks(
        workspace_id=workspace_id,
        limit=int(payload.get("limit") or 20),
    )
    sent = 0
    failed_retryable = 0
    failed_permanent = 0
    for task in due_tasks:
        try:
            delivery_client.send_creator_escalation(task)
        except Exception as exc:
            store.mark_delivery_task_attempt_failed(
                task["delivery_task_id"],
                retryable=True,
                detail=str(exc),
            )
            failed_retryable += 1
            continue
        store.mark_delivery_task_sent(
            task["delivery_task_id"],
            detail="creator escalation sent",
        )
        store.mark_escalations_for_delivery_task(
            task["delivery_task_id"],
            status="sent",
        )
        sent += 1
    remaining = store.list_non_terminal_delivery_tasks(
        workspace_id=workspace_id,
        limit=1_000_000,
    )
    return {
        "workspace_id": workspace_id,
        "processed": len(due_tasks),
        "sent": sent,
        "failed_retryable": failed_retryable,
        "failed_permanent": failed_permanent,
        "remaining_non_terminal": len(remaining),
    }
