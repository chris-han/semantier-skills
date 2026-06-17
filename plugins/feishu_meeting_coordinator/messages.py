from __future__ import annotations

from pathlib import Path


def _prompt_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "src" / "prompts" / "meeting_coordinator"
        if candidate.exists():
            return candidate
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
