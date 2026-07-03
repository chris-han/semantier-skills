"""Prompt rendering for Feishu meeting coordinator messages.

Set SEMANTIER_MEETING_COORDINATOR_PROMPT_ROOT to the directory containing
meeting-coordinator prompt assets when this plugin is installed outside the
repo-local layout.
"""

from __future__ import annotations

import os
from pathlib import Path


def _prompt_root() -> Path:
    injected = os.environ.get("SEMANTIER_MEETING_COORDINATOR_PROMPT_ROOT")
    if injected:
        root = Path(injected).expanduser().resolve()
        if root.exists():
            return root
        raise RuntimeError(f"meeting coordinator prompt root does not exist: {root}")
    root = Path(__file__).resolve().parent / "prompts"
    if root.exists():
        return root
    raise RuntimeError("meeting coordinator prompt assets not found")


def _render(template_name: str, values: dict[str, str], *, language: str = "en") -> str:
    prompt_root = _prompt_root()
    prompt_name = template_name
    if language and language != "en":
        localized = template_name.removesuffix(".md") + f".{language}.md"
        if (prompt_root / localized).exists():
            prompt_name = localized
    text = (prompt_root / prompt_name).read_text(encoding="utf-8")
    for key, value in values.items():
        text = text.replace("{{" + key + "}}", str(value))
    return text


def render_followup_message(
    *,
    attendee_name: str,
    meeting_title: str,
    start_time: str,
    organizer_name: str,
    response_status: str,
    calendar_item_link: str = "",
    language: str = "en",
) -> str:
    return _render(
        "FOLLOWUP_MESSAGE.md",
        {
            "attendee_name": attendee_name,
            "meeting_title": meeting_title,
            "start_time": start_time,
            "organizer_name": organizer_name,
            "response_status": response_status,
            "calendar_item_link": calendar_item_link,
        },
        language=language,
    )


def render_creator_escalation(
    *,
    creator_name: str,
    attendee_name: str,
    meeting_title: str,
    reason: str,
    language: str = "en",
) -> str:
    return _render(
        "CREATOR_ESCALATION.md",
        {
            "creator_name": creator_name,
            "attendee_name": attendee_name,
            "meeting_title": meeting_title,
            "reason": reason,
        },
        language=language,
    )


def render_creator_cancel_suggestion(
    *,
    creator_name: str,
    attendee_names: str,
    meeting_title: str,
    start_time: str,
    language: str = "en",
) -> str:
    return _render(
        "CREATOR_CANCEL_SUGGESTION.md",
        {
            "creator_name": creator_name,
            "attendee_names": attendee_names,
            "meeting_title": meeting_title,
            "start_time": start_time,
        },
        language=language,
    )


def render_negotiator_system(
    *,
    negotiation_id: str,
    workspace_id: str,
    language: str = "en",
) -> str:
    return _render(
        "NEGOTIATOR_SYSTEM.md",
        {
            "negotiation_id": negotiation_id,
            "workspace_id": workspace_id,
        },
        language=language,
    )


def render_ask_decliner_alternative_slot(
    *,
    attendee_name: str,
    meeting_title: str,
    original_time: str,
    timezone: str,
    calendar_item_link: str = "",
    language: str = "en",
) -> str:
    return _render(
        "ASK_DECLINER_ALTERNATIVE_SLOT.md",
        {
            "attendee_name": attendee_name,
            "meeting_title": meeting_title,
            "original_time": original_time,
            "timezone": timezone,
            "calendar_item_link": calendar_item_link,
        },
        language=language,
    )


def render_ask_attendee_slot_vote(
    *,
    attendee_name: str,
    proposed_by_name: str,
    meeting_title: str,
    candidate_slot: str,
    calendar_item_link: str = "",
    language: str = "en",
) -> str:
    return _render(
        "ASK_ATTENDEE_SLOT_VOTE.md",
        {
            "attendee_name": attendee_name,
            "proposed_by_name": proposed_by_name,
            "meeting_title": meeting_title,
            "candidate_slot": candidate_slot,
            "calendar_item_link": calendar_item_link,
        },
        language=language,
    )


def render_requester_final_decision(
    *,
    requester_name: str,
    meeting_title: str,
    original_time: str,
    candidate_summary: str,
    language: str = "en",
) -> str:
    return _render(
        "REQUESTER_FINAL_DECISION.md",
        {
            "requester_name": requester_name,
            "meeting_title": meeting_title,
            "original_time": original_time,
            "candidate_summary": candidate_summary,
        },
        language=language,
    )


def render_negotiation_confirmation(
    *,
    meeting_title: str,
    decision: str,
    selected_time: str,
    language: str = "en",
) -> str:
    return _render(
        "NEGOTIATION_CONFIRMATION.md",
        {
            "meeting_title": meeting_title,
            "decision": decision,
            "selected_time": selected_time,
        },
        language=language,
    )
