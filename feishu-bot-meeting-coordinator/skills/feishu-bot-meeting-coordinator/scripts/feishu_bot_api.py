"""Feishu Bot Meeting Coordinator Helper Script.

ARCHITECTURE CONTRACT (Semantier Deterministic File Ops + Per-Task Sandboxing)
================================================================================

This script is a **materialized helper** for the feishu-bot-meeting-coordinator skill.

How it works:
1. When the skill is invoked, the /agent wrapper layer detects it needs this script.
2. The wrapper **materializes** this file from:
   agent/src/skills/app-infra/productivity/feishu-bot-meeting-coordinator/scripts/feishu_bot_api.py
3. The wrapper copies it to the task sandbox at:
   .scripts/feishu-bot-meeting-coordinator/scripts/feishu_bot_api.py
4. The task execution references ONLY the sandboxed path (relative).
5. When the task completes, the wrapper cleans up the materialized copy.

KEY INVARIANTS:
- This script is discovered/copied by the wrapper layer, NOT by prompts or manual invocation.
- Do NOT hardcode absolute system paths in this file.
- Do NOT assume a fixed location on disk; the script may be materialized anywhere in the sandbox.
- DO use relative paths or environment discovery (e.g., finding agent/.env via traversal).

USAGE:
    # Always invoked from the task sandbox as:
    python .scripts/feishu-bot-meeting-coordinator/scripts/feishu_bot_api.py <command> [args]

    # Example:
    python .scripts/feishu-bot-meeting-coordinator/scripts/feishu_bot_api.py \
      search-chats --query "管理层群"

CREDENTIAL LOADING:
    This script first respects already-exported environment variables, then tries
    runtime-owned .env files such as $HERMES_HOME/.env or
    $SEMANTIER_LOCAL_STATE_DIR/.env, and finally falls back to nearby .env files
    when running from a checked-out repo. Do NOT store hardcoded API keys or
    paths in this file.
"""

from __future__ import annotations

import argparse
import json
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from lark_oapi import Client, LogLevel
from lark_oapi.api.calendar.v4 import (
    CalendarEventAttendeeBuilder,
    CalendarEventBuilder,
    CreateCalendarEventAttendeeRequestBodyBuilder,
    CreateCalendarEventAttendeeRequestBuilder,
    CreateCalendarEventRequestBuilder,
    EventLocationBuilder,
    EventOrganizerBuilder,
    PrimaryCalendarRequestBuilder,
    PrimarysCalendarRequestBuilder,
    PrimarysCalendarRequestBodyBuilder,
    TimeInfoBuilder,
    VchatBuilder,
)
from lark_oapi.api.contact.v3 import (
    BatchGetIdUserRequestBodyBuilder,
    BatchGetIdUserRequestBuilder,
    FindByDepartmentUserRequestBuilder,
)
from lark_oapi.api.im.v1 import (
    CreateMessageRequestBodyBuilder,
    CreateMessageRequestBuilder,
    GetChatMembersRequestBuilder,
    ListChatRequestBuilder,
)
from lark_oapi.core.exception import ObtainAccessTokenException

DEFAULT_TIMEZONE = "Asia/Shanghai"
DEFAULT_ORGANIZER_IDENTITY = "semantier"
DEFAULT_CONTACT_SCOPE = "contacts-added-to-bot"
DEFAULT_NEGOTIATION_ROUNDS = 3


_client_instance: Client | None = None


def _load_env_file(path: Path) -> None:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return

    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key or key in os.environ:
            continue
        if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
            value = value[1:-1]
        elif " #" in value:
            value = value.split(" #", 1)[0].rstrip()
        os.environ[key] = value


def _bootstrap_env() -> None:
    if (os.getenv("FEISHU_APP_ID") or "").strip() and (os.getenv("FEISHU_APP_SECRET") or "").strip():
        return

    script_path = Path(__file__).resolve()
    candidate_env_paths: list[Path] = []

    for env_var in ("HERMES_HOME", "SEMANTIER_LOCAL_STATE_DIR"):
        raw_root = (os.getenv(env_var) or "").strip()
        if not raw_root:
            continue
        candidate_env_paths.append(Path(raw_root).expanduser().resolve() / ".env")

    for parent in [script_path, *script_path.parents]:
        candidate_env_paths.append(parent / ".env")
        if parent.name == "agent" and parent.is_dir():
            candidate_env_paths.append(parent / ".env")
            break

    seen_paths: set[Path] = set()
    for candidate in candidate_env_paths:
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        if resolved in seen_paths or not resolved.is_file():
            continue
        seen_paths.add(resolved)
        _load_env_file(resolved)
        if (os.getenv("FEISHU_APP_ID") or "").strip() and (os.getenv("FEISHU_APP_SECRET") or "").strip():
            return


_bootstrap_env()


class FeishuSkillError(RuntimeError):
    def __init__(self, message: str, *, payload: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.payload = payload or {}


@dataclass
class AttendeeNegotiationState:
    attendee_open_id: str
    display_name: str
    accepted_slots: set[str] = field(default_factory=set)
    declined_slots: set[str] = field(default_factory=set)
    rounds_responded: set[int] = field(default_factory=set)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "attendee_open_id": self.attendee_open_id,
            "display_name": self.display_name,
            "accepted_slots": sorted(self.accepted_slots),
            "declined_slots": sorted(self.declined_slots),
            "rounds_responded": sorted(self.rounds_responded),
            "notes": list(self.notes),
        }


@dataclass
class MeetingNegotiationState:
    negotiation_id: str
    title: str
    requester_open_id: str
    timezone: str
    duration_minutes: int
    max_rounds: int
    current_round: int
    candidate_slots: list[str]
    attendees: dict[str, AttendeeNegotiationState]
    status: str = "negotiating"
    agreed_slot: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "negotiation_id": self.negotiation_id,
            "title": self.title,
            "requester_open_id": self.requester_open_id,
            "timezone": self.timezone,
            "duration_minutes": self.duration_minutes,
            "max_rounds": self.max_rounds,
            "current_round": self.current_round,
            "candidate_slots": list(self.candidate_slots),
            "status": self.status,
            "agreed_slot": self.agreed_slot,
            "attendees": {key: value.to_dict() for key, value in self.attendees.items()},
        }


def _to_slot_key(value: str, timezone_name: str) -> str:
    dt = _parse_time(value, timezone_name)
    return dt.isoformat()


def _deserialize_negotiation_state(state_payload: dict[str, Any]) -> MeetingNegotiationState:
    attendees_payload = state_payload.get("attendees") or {}
    attendees: dict[str, AttendeeNegotiationState] = {}
    for key, value in attendees_payload.items():
        if not isinstance(value, dict):
            continue
        attendee_open_id = str(value.get("attendee_open_id") or key).strip()
        if not attendee_open_id:
            continue
        attendees[attendee_open_id] = AttendeeNegotiationState(
            attendee_open_id=attendee_open_id,
            display_name=str(value.get("display_name") or attendee_open_id),
            accepted_slots=set(str(item) for item in value.get("accepted_slots") or []),
            declined_slots=set(str(item) for item in value.get("declined_slots") or []),
            rounds_responded=set(int(item) for item in value.get("rounds_responded") or []),
            notes=[str(item) for item in value.get("notes") or []],
        )

    return MeetingNegotiationState(
        negotiation_id=str(state_payload.get("negotiation_id") or uuid.uuid4().hex),
        title=str(state_payload.get("title") or ""),
        requester_open_id=str(state_payload.get("requester_open_id") or state_payload.get("initiator_open_id") or "").strip(),
        timezone=str(state_payload.get("timezone") or DEFAULT_TIMEZONE),
        duration_minutes=int(state_payload.get("duration_minutes") or 30),
        max_rounds=max(int(state_payload.get("max_rounds") or DEFAULT_NEGOTIATION_ROUNDS), 1),
        current_round=max(int(state_payload.get("current_round") or 1), 1),
        candidate_slots=[str(item) for item in state_payload.get("candidate_slots") or []],
        attendees=attendees,
        status=str(state_payload.get("status") or "negotiating"),
        agreed_slot=str(state_payload.get("agreed_slot") or "").strip() or None,
    )


def _env(name: str) -> str:
    value = (os.getenv(name) or "").strip()
    if not value:
        # Provide helpful error message with debugging info
        loaded_from_env = "FEISHU_APP_ID" in os.environ or "FEISHU_APP_SECRET" in os.environ
        error_msg = f"Missing required environment variable: {name}"
        if not loaded_from_env:
            error_msg += " (no Feishu credentials loaded from .env)"
        raise FeishuSkillError(error_msg)
    return value


def _get_client() -> Client:
    """Return a cached lark-oapi Client built from environment credentials."""
    global _client_instance
    if _client_instance is None:
        app_id = _env("FEISHU_APP_ID")
        app_secret = _env("FEISHU_APP_SECRET")
        domain = (os.getenv("FEISHU_DOMAIN") or "feishu").strip().lower()
        base_url = "https://open.larksuite.com" if domain == "lark" else "https://open.feishu.cn"
        _client_instance = (
            Client.builder()
            .app_id(app_id)
            .app_secret(app_secret)
            .domain(base_url)
            .log_level(LogLevel.ERROR)
            .build()
        )
    return _client_instance


def _unwrap(resp: Any) -> Any:
    """Unwrap a typed SDK response, raising FeishuSkillError on API failure."""
    if resp.success():
        return resp.data
    raise FeishuSkillError(
        resp.msg or f"Feishu API error (code: {resp.code})",
        payload={"code": resp.code, "msg": resp.msg},
    )


def _get_attr(obj: Any, name: str, default: Any = None) -> Any:
    """Safely read an attribute from a dict or an SDK model object."""
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _normalize_department_names(user: Any) -> list[str]:
    names: list[str] = []
    for item in _get_attr(user, "department_path") or []:
        if item is None:
            continue
        name = str(_get_attr(item, "name") or _get_attr(item, "department_name") or "").strip()
        if name:
            names.append(name)
    return names


def _score_candidate(query: str, user: Any) -> tuple[float, str]:
    normalized_query = query.strip().casefold()
    if not normalized_query:
        return 0.0, "empty_query"

    fields = [
        ("display_name", str(_get_attr(user, "name") or "").strip()),
        ("english_name", str(_get_attr(user, "en_name") or "").strip()),
        ("email", str(_get_attr(user, "email") or _get_attr(user, "enterprise_email") or "").strip()),
        ("open_id", str(_get_attr(user, "open_id") or "").strip()),
    ]
    for field_name, value in fields:
        if value and value.casefold() == normalized_query:
            return 1.0, f"exact_{field_name}"
    for field_name, value in fields:
        if value and normalized_query in value.casefold():
            return 0.7, f"partial_{field_name}"
    return 0.0, "no_match"


def _normalize_contact_candidate(query: str, user: Any) -> dict[str, Any] | None:
    score, match_reason = _score_candidate(query, user)
    open_id = str(_get_attr(user, "open_id") or "").strip()
    if score <= 0.0 or not open_id:
        return None
    avatar = _get_attr(user, "avatar")
    avatar_url = None
    if avatar is not None:
        avatar_url = str(_get_attr(avatar, "avatar_72") or _get_attr(avatar, "avatar_240") or "").strip() or None
    return {
        "display_name": str(_get_attr(user, "name") or _get_attr(user, "en_name") or open_id),
        "open_id": open_id,
        "union_id": str(_get_attr(user, "union_id") or "").strip() or None,
        "avatar_url": avatar_url,
        "email": str(_get_attr(user, "email") or _get_attr(user, "enterprise_email") or "").strip() or None,
        "department_names": _normalize_department_names(user),
        "match_reason": match_reason,
        "score": score,
    }


def search_contacts(query: str, *, limit: int = 10) -> dict[str, Any]:
    normalized_query = query.strip()
    if not normalized_query:
        raise FeishuSkillError("query is required")

    seen: dict[str, dict[str, Any]] = {}
    page_token: str | None = None
    client = _get_client()
    for _ in range(5):
        builder = (
            FindByDepartmentUserRequestBuilder()
            .department_id("0")
            .department_id_type("department_id")
            .user_id_type("open_id")
            .page_size(50)
        )
        if page_token:
            builder = builder.page_token(page_token)
        req = builder.build()
        data = _unwrap(client.contact.v3.user.find_by_department(req))
        items = data.items or []
        for item in items:
            if not item:
                continue
            candidate = _normalize_contact_candidate(normalized_query, item)
            if candidate is None:
                continue
            seen[candidate["open_id"]] = candidate
            if len(seen) >= limit:
                break
        if len(seen) >= limit:
            break
        if not data.has_more:
            break
        page_token = str(data.page_token or "").strip() or None
        if not page_token:
            break

    candidates = sorted(seen.values(), key=lambda item: (-float(item["score"]), item["display_name"]))[:limit]
    return {
        "query": normalized_query,
        "organizer_identity": DEFAULT_ORGANIZER_IDENTITY,
        "contact_scope": DEFAULT_CONTACT_SCOPE,
        "candidates": candidates,
    }


def _score_chat_candidate(query: str, chat: Any) -> tuple[float, str]:
    normalized_query = query.strip().casefold()
    name = str(_get_attr(chat, "name") or "").strip()
    if not normalized_query or not name:
        return 0.0, "empty_query_or_name"
    normalized_name = name.casefold()
    if normalized_name == normalized_query:
        return 1.0, "exact_chat_name"
    if normalized_query in normalized_name:
        return 0.8, "partial_chat_name"
    if "群" in normalized_query:
        simplified = normalized_query.replace("群里的所有人", "").replace("群里所有人", "").replace("群", "").strip()
        if simplified and simplified in normalized_name:
            return 0.7, "normalized_group_phrase"
    return 0.0, "no_match"


def search_chats(query: str, *, limit: int = 10) -> dict[str, Any]:
    normalized_query = query.strip()
    if not normalized_query:
        raise FeishuSkillError("query is required")

    matches: list[dict[str, Any]] = []
    page_token: str | None = None
    client = _get_client()
    for _ in range(5):
        builder = ListChatRequestBuilder().page_size(50)
        if page_token:
            builder = builder.page_token(page_token)
        req = builder.build()
        data = _unwrap(client.im.v1.chat.list(req))
        for item in data.items or []:
            if not item:
                continue
            score, reason = _score_chat_candidate(normalized_query, item)
            if score <= 0.0:
                continue
            chat_id = str(_get_attr(item, "chat_id") or "").strip()
            if not chat_id:
                continue
            matches.append(
                {
                    "chat_id": chat_id,
                    "name": str(_get_attr(item, "name") or chat_id),
                    "description": str(_get_attr(item, "description") or "").strip() or None,
                    "score": score,
                    "match_reason": reason,
                }
            )
        if not data.has_more:
            break
        page_token = str(data.page_token or "").strip() or None
        if not page_token:
            break

    matches.sort(key=lambda item: (-float(item["score"]), str(item["name"])))
    return {"query": normalized_query, "candidates": matches[:limit]}


def get_chat_members(
    chat_id: str,
    *,
    member_id_type: str = "open_id",
) -> list[dict[str, Any]]:
    normalized_chat_id = chat_id.strip()
    if not normalized_chat_id:
        raise FeishuSkillError("chat_id is required")

    normalized_member_id_type = str(member_id_type or "open_id").strip().lower()
    if normalized_member_id_type not in {"open_id", "union_id", "user_id"}:
        raise FeishuSkillError(
            "member_id_type must be one of: open_id, union_id, user_id",
            payload={"member_id_type": member_id_type},
        )

    members: list[dict[str, Any]] = []
    page_token: str | None = None
    client = _get_client()
    for _ in range(5):
        builder = GetChatMembersRequestBuilder().chat_id(normalized_chat_id).member_id_type(normalized_member_id_type).page_size(50)
        if page_token:
            builder = builder.page_token(page_token)
        req = builder.build()
        data = _unwrap(client.im.v1.chat_members.get(req))
        for item in data.items or []:
            if not item:
                continue
            open_id = str(_get_attr(item, "member_id") or _get_attr(item, "open_id") or "").strip()
            if not open_id:
                continue
            members.append(
                {
                    "open_id": open_id,
                    "display_name": str(_get_attr(item, "name") or open_id),
                }
            )
        if not data.has_more:
            break
        page_token = str(data.page_token or "").strip() or None
        if not page_token:
            break
    return members


def _resolve_group_phrase_attendees(group_phrase: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    chats = search_chats(group_phrase, limit=5).get("candidates") or []
    if not chats:
        raise FeishuSkillError("No matching group/chat found", payload={"group_phrase": group_phrase})
    top_chat = chats[0]
    if len(chats) > 1 and float(chats[0].get("score") or 0.0) == float(chats[1].get("score") or 0.0):
        raise FeishuSkillError(
            "Ambiguous group/chat match",
            payload={"group_phrase": group_phrase, "candidates": chats[:3]},
        )

    members = get_chat_members(str(top_chat.get("chat_id") or ""))
    if not members:
        raise FeishuSkillError("Matched group/chat has no resolvable members", payload={"chat": top_chat})

    attendee_results = [
        {
            "requested": group_phrase,
            "status": "resolved",
            "display_name": item["display_name"],
            "open_id": item["open_id"],
            "match_reason": "group_member",
            "source_chat_id": top_chat.get("chat_id"),
            "source_chat_name": top_chat.get("name"),
        }
        for item in members
    ]
    resolved_attendees = [{"type": "user", "user_id": item["open_id"], "is_optional": False} for item in members]
    return attendee_results, resolved_attendees


def _resolve_email_attendee(email: str) -> dict[str, Any] | None:
    client = _get_client()
    body = BatchGetIdUserRequestBodyBuilder().emails([email]).include_resigned(False).build()
    req = BatchGetIdUserRequestBuilder().user_id_type("open_id").request_body(body).build()
    data = _unwrap(client.contact.v3.user.batch_get_id(req))
    user_list = data.user_list or []
    if not user_list:
        return None
    user = user_list[0]
    open_id = str(_get_attr(user, "user_id") or "").strip()
    if not open_id:
        return None
    return {
        "display_name": str(_get_attr(user, "name") or _get_attr(user, "email") or open_id),
        "open_id": open_id,
        "union_id": str(_get_attr(user, "union_id") or "").strip() or None,
        "email": str(_get_attr(user, "email") or email).strip() or None,
        "department_names": [],
        "match_reason": "exact_email",
        "score": 1.0,
    }


def _normalize_attendee_spec(raw_item: Any) -> dict[str, str | None]:
    if isinstance(raw_item, str):
        value = raw_item.strip()
        return {"name": None if "@" in value else value or None, "open_id": None, "email": value if "@" in value else None}
    if not isinstance(raw_item, dict):
        raise FeishuSkillError(f"Unsupported attendee spec: {raw_item!r}")
    normalized = {
        "name": str(raw_item.get("name") or raw_item.get("display_name") or "").strip() or None,
        "open_id": str(raw_item.get("open_id") or "").strip() or None,
        "email": str(raw_item.get("email") or "").strip() or None,
    }
    if not any(normalized.values()):
        raise FeishuSkillError(f"Unsupported attendee spec: {raw_item!r}")
    return normalized


def _parse_time(value: str, timezone_name: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = datetime.strptime(value, "%Y-%m-%d %H:%M")
        except ValueError as exc:
            raise FeishuSkillError(f"Unsupported time format: {value}") from exc
    timezone = ZoneInfo(timezone_name)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone)
    return parsed.astimezone(timezone)


def _build_time_info(dt: datetime, timezone_name: str) -> dict[str, str]:
    return {"timestamp": str(int(dt.timestamp())), "timezone": timezone_name}


def _bot_calendar_id() -> str:
    """Return the bot's own primary calendar ID."""
    client = _get_client()
    req = PrimaryCalendarRequestBuilder().user_id_type("open_id").build()
    data = _unwrap(client.calendar.v4.calendar.primary(req))
    calendars = _get_attr(data, "calendars") or []
    for item in calendars:
        if item is None:
            continue
        inner_calendar = _get_attr(item, "calendar")
        if inner_calendar is not None:
            calendar_id = str(_get_attr(inner_calendar, "calendar_id") or "").strip()
            if calendar_id:
                return calendar_id
        calendar_id = str(_get_attr(item, "calendar_id") or "").strip()
        if calendar_id:
            return calendar_id
    calendar = _get_attr(data, "calendar")
    if calendar is not None:
        calendar_id = str(_get_attr(calendar, "calendar_id") or "").strip()
        if calendar_id:
            return calendar_id
    raise FeishuSkillError("Bot primary calendar lookup returned no calendar_id", payload={})


def _primary_calendar_id_for_user(user_open_id: str) -> str | None:
    """Return the user's primary calendar ID, or None if lookup fails."""
    target = user_open_id.strip()
    if not target:
        return None
    client = _get_client()
    body = PrimarysCalendarRequestBodyBuilder().user_ids([target]).build()
    req = PrimarysCalendarRequestBuilder().request_body(body).user_id_type("open_id").build()
    try:
        data = _unwrap(client.calendar.v4.calendar.primarys(req))
    except FeishuSkillError:
        return None
    calendars = _get_attr(data, "calendars") or []
    for item in calendars:
        if item is None:
            continue
        item_user_id = str(_get_attr(item, "user_id") or "").strip()
        if item_user_id != target:
            continue
        inner_calendar = _get_attr(item, "calendar")
        if inner_calendar is not None:
            calendar_id = str(_get_attr(inner_calendar, "calendar_id") or "").strip()
            if calendar_id:
                return calendar_id
        calendar_id = str(_get_attr(item, "calendar_id") or "").strip()
        if calendar_id:
            return calendar_id
    return None


def start_negotiation(
    *,
    title: str,
    requester_open_id: str,
    attendee_open_ids: list[str],
    candidate_slots: list[str],
    duration_minutes: int,
    timezone: str = DEFAULT_TIMEZONE,
    max_rounds: int = DEFAULT_NEGOTIATION_ROUNDS,
) -> dict[str, Any]:
    if not title.strip():
        raise FeishuSkillError("title is required")
    if not requester_open_id.strip():
        raise FeishuSkillError("requester_open_id is required")
    if duration_minutes <= 0:
        raise FeishuSkillError("duration_minutes must be greater than zero")

    slots = []
    seen_slots: set[str] = set()
    for raw_slot in candidate_slots:
        slot = _to_slot_key(raw_slot, timezone)
        if slot in seen_slots:
            continue
        seen_slots.add(slot)
        slots.append(slot)
    if not slots:
        raise FeishuSkillError("At least one candidate slot is required")

    attendees: dict[str, AttendeeNegotiationState] = {}
    for attendee_open_id in attendee_open_ids:
        attendee = attendee_open_id.strip()
        if not attendee:
            continue
        attendees[attendee] = AttendeeNegotiationState(attendee_open_id=attendee, display_name=attendee)

    if not attendees:
        raise FeishuSkillError("At least one attendee is required")

    state = MeetingNegotiationState(
        negotiation_id=uuid.uuid4().hex,
        title=title.strip(),
        requester_open_id=requester_open_id.strip(),
        timezone=timezone,
        duration_minutes=duration_minutes,
        max_rounds=max(max_rounds, 1),
        current_round=1,
        candidate_slots=slots,
        attendees=attendees,
    )
    return state.to_dict()


def _build_round_prompt(state: MeetingNegotiationState, attendee_open_id: str) -> str:
    options = "\n".join(f"- {datetime.fromisoformat(slot).strftime('%Y-%m-%d %H:%M')}" for slot in state.candidate_slots)
    return (
        f"Round {state.current_round}/{state.max_rounds}: Please confirm your available slots for '{state.title}'\n"
        f"Timezone: {state.timezone}\n"
        f"Options:\n{options}\n"
        "Reply with all available options."
    )


def next_round_prompts(state_payload: dict[str, Any]) -> dict[str, Any]:
    state = _deserialize_negotiation_state(state_payload)
    prompts: list[dict[str, str]] = []
    for attendee in state.attendees.values():
        if state.current_round in attendee.rounds_responded:
            continue
        prompts.append(
            {
                "attendee_open_id": attendee.attendee_open_id,
                "display_name": attendee.display_name,
                "prompt": _build_round_prompt(state, attendee.attendee_open_id),
            }
        )
    return {"negotiation_id": state.negotiation_id, "round": state.current_round, "prompts": prompts}


def submit_attendee_response(
    state_payload: dict[str, Any],
    *,
    attendee_open_id: str,
    accepted_slots: list[str],
    declined_slots: list[str] | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    state = _deserialize_negotiation_state(state_payload)
    attendee_id = attendee_open_id.strip()
    attendee = state.attendees.get(attendee_id)
    if attendee is None:
        raise FeishuSkillError("attendee_open_id is not part of this negotiation", payload={"attendee_open_id": attendee_id})

    accepted = {_to_slot_key(slot, state.timezone) for slot in accepted_slots}
    declined = {_to_slot_key(slot, state.timezone) for slot in (declined_slots or [])}
    invalid = [slot for slot in accepted if slot not in state.candidate_slots]
    if invalid:
        raise FeishuSkillError("accepted_slots must be within candidate_slots", payload={"invalid_slots": invalid})

    attendee.accepted_slots.update(accepted)
    attendee.declined_slots.update(declined)
    attendee.rounds_responded.add(state.current_round)
    if note:
        attendee.notes.append(note)

    votes: dict[str, int] = {slot: 0 for slot in state.candidate_slots}
    all_responded = True
    for item in state.attendees.values():
        if state.current_round not in item.rounds_responded:
            all_responded = False
        for slot in item.accepted_slots:
            if slot in votes:
                votes[slot] += 1

    attendee_count = len(state.attendees)
    agreed_slot: str | None = None
    for slot in state.candidate_slots:
        if votes.get(slot, 0) == attendee_count:
            agreed_slot = slot
            break

    if agreed_slot:
        state.agreed_slot = agreed_slot
        state.status = "agreed"
    elif all_responded and state.current_round >= state.max_rounds:
        state.status = "failed"
    elif all_responded:
        state.current_round += 1

    return {
        "state": state.to_dict(),
        "votes": votes,
        "all_responded": all_responded,
        "agreed_slot": agreed_slot,
    }


def send_final_invitations(
    *,
    attendee_open_ids: list[str],
    title: str,
    start_time: str,
    end_time: str,
    timezone: str,
    meeting_link: str | None,
) -> dict[str, Any]:
    message = (
        f"会议确认: {title}\n"
        f"时间: {start_time} - {end_time} ({timezone})\n"
        f"链接: {meeting_link or '请查看日历邀请'}"
    )
    content = json.dumps({"text": message}, ensure_ascii=False)
    delivered: list[str] = []
    failed: list[dict[str, str]] = []
    client = _get_client()

    for attendee_open_id in attendee_open_ids:
        target = attendee_open_id.strip()
        if not target:
            continue
        try:
            body = (
                CreateMessageRequestBodyBuilder()
                .receive_id(target)
                .msg_type("text")
                .content(content)
                .build()
            )
            req = CreateMessageRequestBuilder().receive_id_type("open_id").request_body(body).build()
            _unwrap(client.im.v1.message.create(req))
            delivered.append(target)
        except FeishuSkillError as exc:
            failed.append({"attendee_open_id": target, "error": str(exc)})

    return {"delivered": delivered, "failed": failed}


def finalize_negotiation_and_create_meeting(
    state_payload: dict[str, Any],
    *,
    description: str | None = None,
    location: str | None = None,
) -> dict[str, Any]:
    state = _deserialize_negotiation_state(state_payload)
    if state.status != "agreed" or not state.agreed_slot:
        raise FeishuSkillError("negotiation has not reached an agreement", payload=state.to_dict())

    start_dt = datetime.fromisoformat(state.agreed_slot)
    end_dt = datetime.fromtimestamp(start_dt.timestamp() + state.duration_minutes * 60, tz=start_dt.tzinfo)
    attendee_open_ids = sorted(set(state.attendees.keys()))
    participant_open_ids = sorted(set(attendee_open_ids + [state.requester_open_id]))

    # Create a single event on the requester's primary calendar.
    # Feishu automatically propagates it to attendee calendars when
    # participants are included in the event's attendee list.
    calendar_id = _primary_calendar_id_for_user(state.requester_open_id)
    meeting = create_meeting(
        title=state.title,
        start_time=start_dt.isoformat(),
        end_time=end_dt.isoformat(),
        attendees=participant_open_ids,
        timezone=state.timezone,
        description=description,
        location=location,
        requester_open_id=state.requester_open_id,
        requester_calendar_id=calendar_id,
    )
    created_meetings = [
        {
            "calendar_owner_open_id": state.requester_open_id,
            "meeting": meeting,
        }
    ]

    primary_meeting = meeting

    invitation = send_final_invitations(
        attendee_open_ids=attendee_open_ids,
        title=state.title,
        start_time=start_dt.strftime("%Y-%m-%d %H:%M"),
        end_time=end_dt.strftime("%Y-%m-%d %H:%M"),
        timezone=state.timezone,
        meeting_link=primary_meeting.get("join_url"),
    )

    return {
        "negotiation_id": state.negotiation_id,
        "agreed_slot": state.agreed_slot,
        "meeting_owner_open_id": state.requester_open_id,
        "primary_meeting": primary_meeting,
        "meetings": created_meetings,
        "invitation_delivery": invitation,
    }


def _resolve_meeting_attendees(attendees: list[Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    attendee_results: list[dict[str, Any]] = []
    resolved_attendees: list[dict[str, Any]] = []
    warnings: list[str] = []

    for raw_item in attendees:
        spec = _normalize_attendee_spec(raw_item)
        requested = spec["open_id"] or spec["email"] or spec["name"] or str(raw_item)
        if spec["open_id"]:
            resolved_attendees.append({"type": "user", "user_id": spec["open_id"], "is_optional": False})
            attendee_results.append({
                "requested": requested,
                "status": "resolved",
                "display_name": spec["name"],
                "open_id": spec["open_id"],
                "match_reason": "provided_open_id",
            })
            continue

        if spec["email"]:
            candidate = _resolve_email_attendee(spec["email"])
            if candidate is None:
                attendee_results.append({
                    "requested": requested,
                    "status": "unresolved",
                    "error": "email_not_found",
                })
                continue
            resolved_attendees.append({"type": "user", "user_id": candidate["open_id"], "is_optional": False})
            attendee_results.append({
                "requested": requested,
                "status": "resolved",
                "display_name": candidate["display_name"],
                "open_id": candidate["open_id"],
                "match_reason": candidate["match_reason"],
            })
            continue

        normalized_name = str(spec["name"] or "").strip()
        if "群" in normalized_name:
            try:
                group_results, group_attendees = _resolve_group_phrase_attendees(normalized_name)
            except FeishuSkillError as exc:
                attendee_results.append(
                    {
                        "requested": requested,
                        "status": "unresolved",
                        "error": "group_lookup_failed",
                        "details": str(exc),
                    }
                )
                continue
            attendee_results.extend(group_results)
            resolved_attendees.extend(group_attendees)
            continue

        search_result = search_contacts(str(spec["name"] or ""), limit=5)
        candidates = search_result["candidates"]
        if not candidates:
            # Fallback: name may be a group/chat even without "群" in it
            chat_result = search_chats(str(spec["name"] or ""), limit=1)
            chat_candidates = chat_result.get("candidates") or []
            if chat_candidates and float(chat_candidates[0].get("score") or 0.0) >= 0.8:
                try:
                    group_results, group_attendees = _resolve_group_phrase_attendees(str(spec["name"] or ""))
                except FeishuSkillError as exc:
                    attendee_results.append(
                        {
                            "requested": requested,
                            "status": "unresolved",
                            "error": "group_lookup_failed",
                            "details": str(exc),
                        }
                    )
                    continue
                attendee_results.extend(group_results)
                resolved_attendees.extend(group_attendees)
                continue
            attendee_results.append({
                "requested": requested,
                "status": "unresolved",
                "error": "name_not_found",
            })
            continue
        top_candidate = candidates[0]
        if len(candidates) == 1 or top_candidate["score"] >= 1.0:
            resolved_attendees.append({"type": "user", "user_id": top_candidate["open_id"], "is_optional": False})
            attendee_results.append({
                "requested": requested,
                "status": "resolved",
                "display_name": top_candidate["display_name"],
                "open_id": top_candidate["open_id"],
                "match_reason": top_candidate["match_reason"],
            })
            continue
        warnings.append(f"Ambiguous attendee '{requested}' matched {len(candidates)} contacts")
        attendee_results.append({
            "requested": requested,
            "status": "ambiguous",
            "display_name": top_candidate["display_name"],
            "open_id": top_candidate["open_id"],
            "match_reason": top_candidate["match_reason"],
            "error": "ambiguous_name",
        })

    deduped_attendees: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for item in resolved_attendees:
        user_id = str(item.get("user_id") or "").strip()
        if not user_id or user_id in seen_ids:
            continue
        seen_ids.add(user_id)
        deduped_attendees.append(item)

    return attendee_results, deduped_attendees, warnings


def create_meeting(
    *,
    title: str,
    start_time: str,
    end_time: str,
    attendees: list[Any],
    timezone: str = DEFAULT_TIMEZONE,
    description: str | None = None,
    location: str | None = None,
    idempotency_key: str | None = None,
    requester_open_id: str | None = None,
    requester_calendar_id: str | None = None,
) -> dict[str, Any]:
    start_dt = _parse_time(start_time, timezone)
    end_dt = _parse_time(end_time, timezone)
    if end_dt <= start_dt:
        raise FeishuSkillError("end_time must be later than start_time")

    attendee_results, resolved_attendees, warnings = _resolve_meeting_attendees(attendees)
    unresolved = [item for item in attendee_results if item["status"] != "resolved"]
    if unresolved:
        raise FeishuSkillError(
            "Not all attendees could be resolved",
            payload={"attendee_results": attendee_results, "warnings": warnings},
        )

    if not requester_open_id and not requester_calendar_id:
        requester_open_id = (os.getenv("FEISHU_REQUESTER_OPEN_ID") or "").strip() or None

    if requester_calendar_id:
        calendar_id = requester_calendar_id.strip()
        target_calendar_owner = "explicit"
    elif requester_open_id:
        user_calendar_id = _primary_calendar_id_for_user(requester_open_id)
        if user_calendar_id:
            calendar_id = user_calendar_id
            target_calendar_owner = "user"
        else:
            calendar_id = _bot_calendar_id()
            target_calendar_owner = "bot"
            warnings.append(
                "Could not determine requester's primary calendar; using bot calendar as fallback."
            )
    else:
        raise FeishuSkillError(
            "requester_open_id is required for create_meeting to ensure user-calendar ownership; "
            "set FEISHU_REQUESTER_OPEN_ID env var or pass --requester-open-id"
        )

    # Ensure the requester is always included as an attendee so the event
    # appears on their calendar and they receive the invitation.
    requester_in_attendees = False
    if requester_open_id:
        for item in resolved_attendees:
            if item.get("user_id") == requester_open_id:
                requester_in_attendees = True
                break
        if not requester_in_attendees:
            resolved_attendees.append(
                {"type": "user", "user_id": requester_open_id, "is_optional": False}
            )
            attendee_results.append(
                {
                    "requested": requester_open_id,
                    "status": "resolved",
                    "display_name": requester_open_id,
                    "open_id": requester_open_id,
                    "match_reason": "requester_implicit",
                }
            )

    attendee_objs = [
        CalendarEventAttendeeBuilder()
        .type("user")
        .user_id(item["user_id"])
        .is_optional(bool(item.get("is_optional")))
        .build()
        for item in resolved_attendees
    ]

    # Determine requester display name for organizer field.
    requester_display_name = requester_open_id
    if requester_open_id:
        for item in attendee_results:
            if item.get("open_id") == requester_open_id and item.get("display_name"):
                requester_display_name = item["display_name"]
                break

    body_builder = (
        CalendarEventBuilder()
        .summary(title)
        .description(description or "")
        .need_notification(True)
        .start_time(TimeInfoBuilder().timestamp(str(int(start_dt.timestamp()))).timezone(timezone).build())
        .end_time(TimeInfoBuilder().timestamp(str(int(end_dt.timestamp()))).timezone(timezone).build())
        .vchat(VchatBuilder().vc_type("vc").build())
        .attendee_ability("can_see_others")
    )
    if requester_open_id:
        body_builder = body_builder.event_organizer(
            EventOrganizerBuilder()
            .user_id(requester_open_id)
            .display_name(requester_display_name)
            .build()
        )
    if location:
        body_builder = body_builder.location(EventLocationBuilder().name(location).build())

    builder = (
        CreateCalendarEventRequestBuilder()
        .calendar_id(calendar_id)
        .user_id_type("open_id")
        .request_body(body_builder.build())
    )
    if idempotency_key:
        builder = builder.idempotency_key(idempotency_key)
    req = builder.build()

    client = _get_client()
    resp = client.calendar.v4.calendar_event.create(req)

    # If the bot lacks write access to the user's calendar (191002), fall back to
    # the bot's own calendar so the event can still be created and invitations sent.
    if not resp.success() and target_calendar_owner == "user" and resp.code == 191002:
        calendar_id = _bot_calendar_id()
        target_calendar_owner = "bot"
        warnings.append(
            "Bot lacks write access to requester's calendar; created on bot calendar instead. "
            "Attendees will still receive invitations."
        )
        builder = (
            CreateCalendarEventRequestBuilder()
            .calendar_id(calendar_id)
            .user_id_type("open_id")
            .request_body(body_builder.build())
        )
        if idempotency_key:
            builder = builder.idempotency_key(idempotency_key)
        req = builder.build()
        resp = client.calendar.v4.calendar_event.create(req)

    data = _unwrap(resp)
    event = _get_attr(data, "event")
    if event is None:
        raise FeishuSkillError("Meeting creation response did not include event", payload={})
    vchat = _get_attr(event, "vchat")
    event_id = str(_get_attr(event, "event_id") or "").strip()
    if not event_id:
        raise FeishuSkillError("Meeting creation response did not include event_id", payload={})

    # Feishu ignores attendees in the create-event body; add them via the dedicated
    # attendee API so that invitations are actually sent and appear on calendars.
    if attendee_objs:
        attendee_body = (
            CreateCalendarEventAttendeeRequestBodyBuilder()
            .attendees(attendee_objs)
            .need_notification(True)
            .build()
        )
        attendee_req = (
            CreateCalendarEventAttendeeRequestBuilder()
            .calendar_id(calendar_id)
            .event_id(event_id)
            .user_id_type("open_id")
            .request_body(attendee_body)
            .build()
        )
        try:
            _unwrap(client.calendar.v4.calendar_event_attendee.create(attendee_req))
        except FeishuSkillError as exc:
            warnings.append(f"Attendee invitation failed: {exc}")

    # Use the actual organizer from Feishu response if available.
    resp_organizer = _get_attr(event, "event_organizer")
    organizer_name = str(_get_attr(resp_organizer, "display_name") or requester_display_name).strip()
    return {
        "event_id": event_id,
        "organizer_identity": organizer_name,
        "requester_open_id": requester_open_id,
        "calendar_id": str(_get_attr(event, "organizer_calendar_id") or calendar_id),
        "join_url": str(_get_attr(vchat, "meeting_url") or _get_attr(vchat, "live_link") or "").strip() or None,
        "attendee_results": attendee_results,
        "warnings": warnings,
    }


def _build_cli() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Feishu bot meeting helper for the feishu-bot-meeting-coordinator skill")
    subparsers = parser.add_subparsers(dest="command", required=True)

    chat_search_parser = subparsers.add_parser("search-chats")
    chat_search_parser.add_argument("--query", required=True)
    chat_search_parser.add_argument("--limit", type=int, default=10)

    chat_members_parser = subparsers.add_parser("get-chat-members")
    chat_members_parser.add_argument("--chat-id", required=True)
    chat_members_parser.add_argument(
        "--member-id-type",
        choices=["open_id", "union_id", "user_id"],
        default="open_id",
    )

    search_parser = subparsers.add_parser("search-contacts")
    search_parser.add_argument("--query", required=True)
    search_parser.add_argument("--limit", type=int, default=10)

    meeting_parser = subparsers.add_parser("create-meeting")
    meeting_parser.add_argument("--title", required=True)
    meeting_parser.add_argument("--start-time", required=True)
    meeting_parser.add_argument("--end-time", required=True)
    meeting_parser.add_argument("--timezone", default=DEFAULT_TIMEZONE)
    meeting_parser.add_argument("--attendee", action="append", dest="attendees", required=True)
    meeting_parser.add_argument("--description")
    meeting_parser.add_argument("--location")
    meeting_parser.add_argument("--idempotency-key")
    meeting_owner_group = meeting_parser.add_mutually_exclusive_group(required=False)
    meeting_owner_group.add_argument("--requester-open-id", help="Requester open_id; defaults to FEISHU_REQUESTER_OPEN_ID env var")
    meeting_owner_group.add_argument("--requester-calendar-id", help="Explicit calendar id override")

    negotiation_parser = subparsers.add_parser("start-negotiation")
    negotiation_parser.add_argument("--title", required=True)
    negotiation_parser.add_argument("--requester-open-id", required=True)
    negotiation_parser.add_argument("--duration-minutes", type=int, required=True)
    negotiation_parser.add_argument("--timezone", default=DEFAULT_TIMEZONE)
    negotiation_parser.add_argument("--max-rounds", type=int, default=DEFAULT_NEGOTIATION_ROUNDS)
    negotiation_parser.add_argument("--attendee-open-id", action="append", required=True, dest="attendee_open_ids")
    negotiation_parser.add_argument("--candidate-slot", action="append", required=True, dest="candidate_slots")

    submit_parser = subparsers.add_parser("submit-response")
    submit_parser.add_argument("--state-json", required=True)
    submit_parser.add_argument("--attendee-open-id", required=True)
    submit_parser.add_argument("--accepted-slot", action="append", required=True, dest="accepted_slots")
    submit_parser.add_argument("--declined-slot", action="append", dest="declined_slots")
    submit_parser.add_argument("--note")

    finalize_parser = subparsers.add_parser("finalize-negotiation")
    finalize_parser.add_argument("--state-json", required=True)
    finalize_parser.add_argument("--description")
    finalize_parser.add_argument("--location")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_cli()
    args = parser.parse_args(argv)
    try:
        if args.command == "search-chats":
            result = search_chats(args.query, limit=args.limit)
        elif args.command == "get-chat-members":
            result = get_chat_members(args.chat_id, member_id_type=args.member_id_type)
        elif args.command == "search-contacts":
            result = search_contacts(args.query, limit=args.limit)
        elif args.command == "create-meeting":
            result = create_meeting(
                title=args.title,
                start_time=args.start_time,
                end_time=args.end_time,
                attendees=list(args.attendees or []),
                timezone=args.timezone,
                description=args.description,
                location=args.location,
                idempotency_key=args.idempotency_key,
                requester_open_id=args.requester_open_id,
                requester_calendar_id=args.requester_calendar_id,
            )
        elif args.command == "start-negotiation":
            result = start_negotiation(
                title=args.title,
                requester_open_id=args.requester_open_id,
                attendee_open_ids=list(args.attendee_open_ids or []),
                candidate_slots=list(args.candidate_slots or []),
                duration_minutes=args.duration_minutes,
                timezone=args.timezone,
                max_rounds=args.max_rounds,
            )
        elif args.command == "submit-response":
            state_payload = json.loads(args.state_json)
            result = submit_attendee_response(
                state_payload,
                attendee_open_id=args.attendee_open_id,
                accepted_slots=list(args.accepted_slots or []),
                declined_slots=list(args.declined_slots or []),
                note=args.note,
            )
        else:
            state_payload = json.loads(args.state_json)
            result = finalize_negotiation_and_create_meeting(
                state_payload,
                description=args.description,
                location=args.location,
            )
    except FeishuSkillError as exc:
        print(json.dumps({"ok": False, "error": str(exc), "payload": exc.payload}, ensure_ascii=False, indent=2))
        return 1
    except ObtainAccessTokenException as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": f"Feishu auth failed: {exc}",
                    "payload": {},
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1

    print(json.dumps({"ok": True, "result": result}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
