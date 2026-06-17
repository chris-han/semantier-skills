from __future__ import annotations

import importlib.util
import json
import os
import sys
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import quote


def _ok(key: str, value: Any) -> str:
    return json.dumps({"ok": True, key: value}, ensure_ascii=False, sort_keys=True)


def _error(message: str) -> str:
    return json.dumps({"ok": False, "error": message}, ensure_ascii=False, sort_keys=True)


def _gateway(kwargs: dict[str, Any]):
    gateway = kwargs.get("gateway")
    if gateway is None:
        gateway = _default_gateway()
    return gateway


class _LocalCronClient:
    def __init__(self, hermes_home: str):
        self.hermes_home = Path(hermes_home).expanduser().resolve()

    def _bind(self):
        from runtime_paths import bind_workspace_env

        return bind_workspace_env(self.hermes_home)

    def _workspace_skill_refs(self, skills: list[str]) -> list[str]:
        resolved: list[str] = []
        for skill in skills:
            skill_name = str(skill or "").strip()
            if skill_name != "feishu_meeting_coordinator":
                if skill_name:
                    resolved.append(skill_name)
                continue
            plugin_dir = self.hermes_home / "plugins" / skill_name
            if (plugin_dir / "SKILL.md").exists():
                resolved.append("feishu_meeting_coordinator:feishu-bot-meeting-coordinator")
            else:
                resolved.append(skill_name)
        return resolved

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
    ) -> str:
        with self._bind():
            from cron.jobs import create_job, list_jobs, update_job

            resolved_skills = self._workspace_skill_refs(skills)
            for job in list_jobs(include_disabled=True):
                if str(job.get("name") or "") != name:
                    continue
                job_id = str(job.get("id") or "")
                updates: dict[str, Any] = {}
                if job.get("enabled") is False:
                    updates["enabled"] = True
                if list(job.get("skills") or []) != resolved_skills:
                    updates["skills"] = resolved_skills
                if updates:
                    update_job(job_id, updates)
                return job_id
            job = create_job(
                prompt=prompt,
                schedule=schedule,
                name=name,
                skills=resolved_skills,
                deliver=deliver,
                repeat=repeat,
                profile=profile,
            )
            return str(job["id"])

    def job_exists(self, cron_job_id: str) -> bool:
        with self._bind():
            from cron.jobs import list_jobs

            return any(str(job.get("id") or "") == str(cron_job_id) for job in list_jobs(include_disabled=True))

    def disable_job(self, cron_job_id: str) -> None:
        with self._bind():
            from cron.jobs import update_job

            update_job(cron_job_id, {"enabled": False})


class _DefaultGateway:
    def _cron(self) -> _LocalCronClient:
        hermes_home = _text(_session_metadata().get("hermes_home")) or _session_env("HERMES_SESSION_HERMES_HOME")
        if not hermes_home:
            raise RuntimeError("Semantier gateway binding required")
        return _LocalCronClient(hermes_home)

    def start_monitor(self, payload: dict[str, Any]) -> dict[str, Any]:
        from agents import meeting_coordinator_gateway, meeting_coordinator_store

        return meeting_coordinator_gateway.start_monitor(
            payload,
            store=meeting_coordinator_store.MeetingCoordinatorStore(),
            cron=self._cron(),
        )

    def monitor_tick(self, payload: dict[str, Any]) -> dict[str, Any]:
        from agents import meeting_coordinator_gateway, meeting_coordinator_store

        return meeting_coordinator_gateway.monitor_tick(
            payload,
            store=meeting_coordinator_store.MeetingCoordinatorStore(),
            feishu_client=_FeishuClient(),
            cron=self._cron(),
        )

    def monitor_stop(self, payload: dict[str, Any]) -> dict[str, Any]:
        from agents import meeting_coordinator_gateway, meeting_coordinator_store

        return meeting_coordinator_gateway.monitor_stop(
            payload,
            store=meeting_coordinator_store.MeetingCoordinatorStore(),
            cron=self._cron(),
        )

    def escalation_retry_tick(self, payload: dict[str, Any]) -> dict[str, Any]:
        from agents import meeting_coordinator_gateway, meeting_coordinator_store

        return meeting_coordinator_gateway.escalation_retry_tick(
            payload,
            store=meeting_coordinator_store.MeetingCoordinatorStore(),
            delivery_client=_feishu_helper(),
        )

    def requeue_delivery_task(self, *, delivery_task_id: str, reason: str) -> dict[str, Any]:
        from agents import meeting_coordinator_gateway, meeting_coordinator_store

        return meeting_coordinator_gateway.requeue_delivery_task(
            delivery_task_id=delivery_task_id,
            reason=reason,
            store=meeting_coordinator_store.MeetingCoordinatorStore(),
            cron=self._cron(),
        )


def _default_gateway() -> _DefaultGateway:
    return _DefaultGateway()


class _FeishuClient:
    def get_attendee_response_statuses(self, *, calendar_id: str, event_id: str) -> list[dict[str, Any]]:
        result = _feishu_helper().list_attendee_status(
            event_id=event_id,
            calendar_id=calendar_id,
            requester_open_id=_feishu_chat_initiator_open_id() or None,
            page_size=100,
        )
        attendees = result.get("attendees") if isinstance(result, dict) else None
        return list(attendees or [])

    def send_attendee_message(self, *, attendee_open_ids: list[str], message: str) -> dict[str, Any]:
        return _feishu_helper().send_attendee_message(
            attendee_open_ids=attendee_open_ids,
            message=message,
        )


@lru_cache(maxsize=1)
def _feishu_helper():
    helper_path = Path(__file__).with_name("scripts") / "feishu_bot_api.py"
    spec = importlib.util.spec_from_file_location(
        "feishu_meeting_coordinator_feishu_bot_api",
        helper_path,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load Feishu helper script: {helper_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _helper_call(func_name: str, *args: Any, **kwargs: Any) -> str:
    try:
        result = getattr(_feishu_helper(), func_name)(*args, **kwargs)
    except Exception as exc:
        payload = getattr(exc, "payload", None)
        if isinstance(payload, dict) and payload:
            return json.dumps(
                {"ok": False, "error": str(exc), "payload": payload},
                ensure_ascii=False,
                sort_keys=True,
            )
        return _error(str(exc))
    return _ok("result", result)


def _helper_error(exc: Exception) -> str:
    payload = getattr(exc, "payload", None)
    if isinstance(payload, dict) and payload:
        return json.dumps(
            {"ok": False, "error": str(exc), "payload": payload},
            ensure_ascii=False,
            sort_keys=True,
        )
    return _error(str(exc))


def _payload(args: Any) -> dict[str, Any]:
    if args is None:
        return {}
    if not isinstance(args, dict):
        raise RuntimeError("tool args must be a JSON object")
    return dict(args)


def _list_arg(payload: dict[str, Any], *names: str) -> list[Any]:
    for name in names:
        value = payload.get(name)
        if value is None:
            continue
        if isinstance(value, list):
            return value
        if isinstance(value, str):
            text = value.strip()
            if text.startswith("["):
                try:
                    parsed = json.loads(text)
                except json.JSONDecodeError:
                    parsed = None
                if isinstance(parsed, list):
                    return parsed
        return [value]
    return []


def _search_text(value: Any) -> str:
    if isinstance(value, dict):
        for key in ("query", "name", "display_name", "email", "open_id", "user_id"):
            text = _text(value.get(key))
            if text:
                return text
        return ""
    return _text(value)


def _contact_search_queries(payload: dict[str, Any]) -> list[str]:
    queries: list[str] = []
    seen: set[str] = set()
    requester_open_id = _text(_requester_open_id(payload))

    for value in [_search_text(payload.get("query")), *_list_arg(payload, "queries", "query_list")]:
        query = _search_text(value)
        key = query.casefold()
        if query and query != requester_open_id and key not in seen:
            queries.append(query)
            seen.add(key)

    for value in _list_arg(payload, "attendees", "attendee", "participants", "participant"):
        query = _search_text(value)
        key = query.casefold()
        if query and query != requester_open_id and key not in seen:
            queries.append(query)
            seen.add(key)

    return queries


def _text(value: Any) -> str:
    return str(value or "").strip()


def _session_env(name: str) -> str:
    try:
        from gateway.session_context import get_session_env
    except Exception:
        return os.getenv(name, "")
    return get_session_env(name, "")


def _session_metadata() -> dict[str, Any]:
    hermes_home = _session_env("HERMES_SESSION_HERMES_HOME")
    session_id = _session_env("HERMES_SESSION_ID")
    metadata: dict[str, Any] = {
        "platform": _session_env("HERMES_SESSION_PLATFORM"),
        "session_id": session_id,
        "session_key": _session_env("HERMES_SESSION_KEY"),
        "chat_id": _session_env("HERMES_SESSION_CHAT_ID"),
        "thread_id": _session_env("HERMES_SESSION_THREAD_ID") or None,
        "origin_user_id": _session_env("HERMES_SESSION_USER_ID"),
        "workspace_id": _session_env("HERMES_SESSION_WORKSPACE_OWNER_ID"),
        "hermes_home": hermes_home,
    }
    if not hermes_home or not session_id:
        return metadata
    session_file = (
        Path(hermes_home)
        / "sessions"
        / f"session_{quote(session_id, safe='')}.json"
    )
    try:
        payload = json.loads(session_file.read_text(encoding="utf-8"))
    except Exception:
        return metadata
    if isinstance(payload, dict):
        metadata.update({key: value for key, value in payload.items() if value is not None})
    return metadata


def _current_session_origin_user_id() -> str:
    return _text(_session_metadata().get("origin_user_id"))


def _feishu_chat_initiator_open_id() -> str:
    platform = _session_env("HERMES_SESSION_PLATFORM").casefold()
    if platform != "feishu":
        return ""

    origin_user_id = _current_session_origin_user_id()
    if origin_user_id.startswith("ou_"):
        return origin_user_id

    session_user_id = _text(_session_env("HERMES_SESSION_USER_ID"))
    if session_user_id.startswith("ou_"):
        return session_user_id
    return ""


def _requester_open_id(payload: dict[str, Any]) -> Any:
    return _feishu_chat_initiator_open_id() or payload.get("requester_open_id")


def _attendees_without_requester(attendees: list[Any], requester_open_id: Any) -> list[Any]:
    requester = _text(requester_open_id)
    if not requester:
        return attendees
    return [attendee for attendee in attendees if _search_text(attendee) != requester]


def _workspace_id_from_session(metadata: dict[str, Any]) -> str:
    workspace_id = _text(metadata.get("workspace_id") or metadata.get("workspace_owner_id"))
    if workspace_id:
        return workspace_id
    session_id = _text(metadata.get("session_id"))
    if ":" in session_id:
        return session_id.split(":", 1)[0]
    return ""


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _creator_delivery_binding(metadata: dict[str, Any], creator_user_id: str) -> dict[str, Any]:
    workspace_id = _workspace_id_from_session(metadata)
    return {
        "workspace_owner_id": workspace_id,
        "creator_user_id": creator_user_id,
        "platform": _text(metadata.get("platform")) or "feishu",
        "chat_id": _text(metadata.get("chat_id")),
        "thread_id": metadata.get("thread_id") or None,
        "session_id": _text(metadata.get("session_id")),
        "session_key": _text(metadata.get("session_key")),
        "hermes_home": _text(metadata.get("hermes_home")),
        "delivery_adapter_key": metadata.get("delivery_adapter_key"),
        "source": "feishu_session",
        "captured_at": _utc_now_iso(),
    }


def _monitor_attendees_from_values(values: list[Any], requester_open_id: str) -> list[dict[str, Any]]:
    attendees: list[dict[str, Any]] = []
    seen: set[str] = set()
    for value in values:
        if isinstance(value, dict):
            user_id = _text(value.get("user_id") or value.get("open_id") or value.get("attendee_user_id"))
            message_user_id = _text(value.get("message_user_id") or user_id)
            display_name = _text(value.get("display_name") or value.get("name") or user_id)
        else:
            user_id = _text(value)
            message_user_id = user_id
            display_name = user_id
        if not user_id or user_id == requester_open_id or user_id in seen:
            continue
        seen.add(user_id)
        attendees.append(
            {
                "user_id": user_id,
                "message_user_id": message_user_id,
                "display_name": display_name,
            }
        )
    return attendees


def _live_monitor_attendees(payload: dict[str, Any], requester_open_id: str) -> list[dict[str, Any]]:
    event_id = _text(payload.get("event_id"))
    if not event_id:
        return []
    try:
        status = _feishu_helper().list_attendee_status(
            event_id=event_id,
            calendar_id=payload.get("calendar_id"),
            requester_open_id=requester_open_id,
            page_size=100,
        )
    except Exception:
        return []
    attendees = status.get("attendees") if isinstance(status, dict) else None
    if not isinstance(attendees, list):
        return []
    values = [
        item
        for item in attendees
        if isinstance(item, dict)
        and not item.get("is_organizer")
        and _text(item.get("user_id") or item.get("open_id")) != requester_open_id
    ]
    return _monitor_attendees_from_values(values, requester_open_id)


def _prepare_monitor_payload(payload: dict[str, Any]) -> dict[str, Any]:
    metadata = _session_metadata()
    requester_open_id = _text(_requester_open_id(payload) or metadata.get("origin_user_id"))
    workspace_id = _text(payload.get("workspace_id")) or _workspace_id_from_session(metadata)
    if not workspace_id:
        raise RuntimeError("workspace_id is required for RSVP monitor start")
    if not requester_open_id:
        raise RuntimeError("creator_user_id is required for RSVP monitor start")

    attendees = _monitor_attendees_from_values(
        _list_arg(
            payload,
            "attendees",
            "attendee",
            "participants",
            "participant",
            "attendee_open_ids",
            "attendee_open_id",
        ),
        requester_open_id,
    )
    if not attendees:
        attendees = _live_monitor_attendees(payload, requester_open_id)
    if not attendees:
        raise RuntimeError("at least one non-requester attendee is required for RSVP monitor")

    prepared = dict(payload)
    prepared["workspace_id"] = workspace_id
    prepared["creator_user_id"] = _text(payload.get("creator_user_id")) or requester_open_id
    prepared["platform"] = _text(payload.get("platform")) or "feishu"
    prepared["event_revision_id"] = _text(payload.get("event_revision_id")) or _text(payload.get("event_id"))
    prepared["creator_delivery_binding"] = payload.get("creator_delivery_binding") or _creator_delivery_binding(
        metadata,
        prepared["creator_user_id"],
    )
    prepared["attendees"] = attendees
    if payload.get("meeting_start_time") is None and payload.get("start_time") is not None:
        prepared["meeting_start_time"] = payload.get("start_time")
    if payload.get("meeting_end_time") is None and payload.get("end_time") is not None:
        prepared["meeting_end_time"] = payload.get("end_time")
    return prepared


def feishu_contacts_search(args, **kwargs):
    payload = _payload(args)
    queries = _contact_search_queries(payload)
    if len(queries) > 1:
        limit = int(payload.get("limit") or 10)
        results: list[dict[str, Any]] = []
        errors: list[dict[str, str]] = []
        helper = _feishu_helper()
        for query in queries:
            try:
                result = helper.search_contacts(query, limit=limit)
            except Exception as exc:
                error = {"query": query, "error": str(exc)}
                errors.append(error)
                results.append({"query": query, "ok": False, "error": str(exc)})
                continue
            results.append({"query": query, "ok": True, "result": result})
        return json.dumps(
            {
                "ok": not errors,
                "result": {"queries": queries, "results": results},
                **({"errors": errors} if errors else {}),
            },
            ensure_ascii=False,
            sort_keys=True,
        )

    query = queries[0] if queries else ""
    return _helper_call(
        "search_contacts",
        query,
        limit=int(payload.get("limit") or 10),
    )


def feishu_chats_search(args, **kwargs):
    payload = _payload(args)
    return _helper_call(
        "search_chats",
        str(payload.get("query") or ""),
        limit=int(payload.get("limit") or 10),
    )


def feishu_chat_members_get(args, **kwargs):
    payload = _payload(args)
    return _helper_call(
        "get_chat_members",
        str(payload.get("chat_id") or ""),
        member_id_type=str(payload.get("member_id_type") or "open_id"),
    )


def feishu_meeting_create(args, **kwargs):
    payload = _payload(args)
    if payload.get("is_recurrent_meeting") is True:
        return _error("recurrent meetings are not supported by the v0.1 RSVP monitor flow")
    requester_open_id = _requester_open_id(payload)
    attendees = _attendees_without_requester(
        _list_arg(
            payload,
            "attendees",
            "attendee",
            "participants",
            "participant",
            "attendee_open_ids",
            "attendee_open_id",
        ),
        requester_open_id,
    )
    if not attendees:
        return _error("at least one non-requester attendee is required")
    try:
        result = _feishu_helper().create_meeting(
            title=str(payload.get("title") or ""),
            start_time=str(payload.get("start_time") or ""),
            end_time=str(payload.get("end_time") or ""),
            attendees=attendees,
            timezone=str(payload.get("timezone") or "Asia/Shanghai"),
            description=payload.get("description"),
            location=payload.get("location"),
            idempotency_key=payload.get("idempotency_key"),
            requester_open_id=requester_open_id,
            requester_calendar_id=payload.get("requester_calendar_id"),
        )
    except Exception as exc:
        return _helper_error(exc)

    if isinstance(result, dict) and payload.get("start_rsvp_monitor") is not False:
        monitor_result = _start_rsvp_monitor_for_created_meeting(
            payload=payload,
            meeting=result,
            attendees=attendees,
            requester_open_id=_text(requester_open_id),
            kwargs=kwargs,
        )
        result = dict(result)
        result["rsvp_monitor"] = monitor_result
        if not monitor_result.get("ok"):
            warnings = list(result.get("warnings") or [])
            warnings.append(f"RSVP monitor was not started: {monitor_result.get('error')}")
            result["warnings"] = warnings

    return _ok("result", result)


def _start_rsvp_monitor_for_created_meeting(
    *,
    payload: dict[str, Any],
    meeting: dict[str, Any],
    attendees: list[Any],
    requester_open_id: str,
    kwargs: dict[str, Any],
) -> dict[str, Any]:
    event_id = _text(meeting.get("event_id"))
    calendar_id = _text(meeting.get("calendar_id"))
    if not event_id or not calendar_id:
        return {"ok": False, "error": "event_id and calendar_id are required to start RSVP monitor"}
    try:
        monitor_payload = _prepare_monitor_payload(
            {
                "event_id": event_id,
                "event_revision_id": _text(meeting.get("event_revision_id")) or event_id,
                "calendar_id": calendar_id,
                "attendees": attendees,
                "requester_open_id": requester_open_id,
                "meeting_title": payload.get("title"),
                "meeting_start_time": payload.get("start_time"),
                "meeting_end_time": payload.get("end_time"),
                "timezone": payload.get("timezone") or "Asia/Shanghai",
            }
        )
        monitor = _gateway(kwargs).start_monitor(monitor_payload)
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    return {"ok": True, "monitor": monitor}


def feishu_meeting_negotiation_start(args, **kwargs):
    payload = _payload(args)
    return _helper_call(
        "start_negotiation",
        title=str(payload.get("title") or ""),
        requester_open_id=str(payload.get("requester_open_id") or ""),
        attendee_open_ids=[
            str(item) for item in _list_arg(payload, "attendee_open_ids", "attendee_open_id")
        ],
        candidate_slots=[
            str(item) for item in _list_arg(payload, "candidate_slots", "candidate_slot")
        ],
        duration_minutes=int(payload.get("duration_minutes") or 0),
        timezone=str(payload.get("timezone") or "Asia/Shanghai"),
        max_rounds=int(payload.get("max_rounds") or 3),
    )


def feishu_meeting_negotiation_next_round_prompts(args, **kwargs):
    payload = _payload(args)
    return _helper_call(
        "next_round_prompts",
        payload.get("state") or payload.get("state_payload") or {},
    )


def feishu_meeting_negotiation_submit_response(args, **kwargs):
    payload = _payload(args)
    return _helper_call(
        "submit_attendee_response",
        payload.get("state") or payload.get("state_payload") or {},
        attendee_open_id=str(payload.get("attendee_open_id") or ""),
        accepted_slots=[str(item) for item in _list_arg(payload, "accepted_slots", "accepted_slot")],
        declined_slots=[str(item) for item in _list_arg(payload, "declined_slots", "declined_slot")],
        note=payload.get("note"),
    )


def feishu_meeting_negotiation_finalize(args, **kwargs):
    payload = _payload(args)
    return _helper_call(
        "finalize_negotiation_and_create_meeting",
        payload.get("state") or payload.get("state_payload") or {},
        description=payload.get("description"),
        location=payload.get("location"),
    )


def feishu_meeting_attendee_status_list(args, **kwargs):
    payload = _payload(args)
    return _helper_call(
        "list_attendee_status",
        event_id=str(payload.get("event_id") or ""),
        calendar_id=payload.get("calendar_id"),
        requester_open_id=payload.get("requester_open_id"),
        page_size=int(payload.get("page_size") or 50),
    )


def feishu_final_invitations_send(args, **kwargs):
    payload = _payload(args)
    return _helper_call(
        "send_final_invitations",
        attendee_open_ids=[
            str(item) for item in _list_arg(payload, "attendee_open_ids", "attendee_open_id")
        ],
        title=str(payload.get("title") or ""),
        start_time=str(payload.get("start_time") or ""),
        end_time=str(payload.get("end_time") or ""),
        timezone=str(payload.get("timezone") or "Asia/Shanghai"),
        meeting_link=payload.get("meeting_link"),
    )


def feishu_attendee_message_send(args, **kwargs):
    payload = _payload(args)
    return _helper_call(
        "send_attendee_message",
        attendee_open_ids=[str(item) for item in _list_arg(payload, "attendee_open_ids", "attendee_open_id")],
        message=str(payload.get("message") or ""),
    )


def feishu_meeting_new_time_propose(args, **kwargs):
    payload = _payload(args)
    return _helper_call(
        "propose_new_time",
        attendee_open_ids=[str(item) for item in _list_arg(payload, "attendee_open_ids", "attendee_open_id")],
        title=str(payload.get("title") or ""),
        candidate_slots=[str(item) for item in _list_arg(payload, "candidate_slots", "candidate_slot")],
        timezone=str(payload.get("timezone") or "Asia/Shanghai"),
        event_id=payload.get("event_id"),
        current_time=payload.get("current_time"),
        note=payload.get("note"),
    )


def feishu_meeting_time_update(args, **kwargs):
    payload = _payload(args)
    return _helper_call(
        "update_meeting_time",
        event_id=str(payload.get("event_id") or ""),
        calendar_id=str(payload.get("calendar_id") or ""),
        start_time=str(payload.get("start_time") or ""),
        end_time=str(payload.get("end_time") or ""),
        timezone=str(payload.get("timezone") or "Asia/Shanghai"),
    )


def feishu_meeting_monitor_start(args, **kwargs):
    try:
        payload = dict(args or {})
        if kwargs.get("gateway") is None:
            payload = _prepare_monitor_payload(payload)
        monitor = _gateway(kwargs).start_monitor(payload)
    except Exception as exc:
        return _error(str(exc))
    return _ok("monitor", monitor)


def feishu_meeting_monitor_tick(args, **kwargs):
    try:
        result = _gateway(kwargs).monitor_tick(dict(args or {}))
    except Exception as exc:
        return _error(str(exc))
    return _ok("result", result)


def feishu_meeting_monitor_stop(args, **kwargs):
    try:
        result = _gateway(kwargs).monitor_stop(dict(args or {}))
    except Exception as exc:
        return _error(str(exc))
    return _ok("result", result)


def feishu_meeting_escalation_retry_tick(args, **kwargs):
    try:
        result = _gateway(kwargs).escalation_retry_tick(dict(args or {}))
    except Exception as exc:
        return _error(str(exc))
    return _ok("result", result)


def feishu_meeting_delivery_task_requeue(args, **kwargs):
    payload = dict(args or {})
    delivery_task_id = str(payload.get("delivery_task_id") or "").strip()
    reason = str(payload.get("reason") or "operator requested requeue").strip()
    if not delivery_task_id:
        return _error("delivery_task_id is required")
    try:
        task = _gateway(kwargs).requeue_delivery_task(
            delivery_task_id=delivery_task_id,
            reason=reason,
        )
    except Exception as exc:
        return _error(str(exc))
    return _ok("delivery_task", task)
