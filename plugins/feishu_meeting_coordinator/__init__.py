from __future__ import annotations

from pathlib import Path

from .cli import command, register_cli
from .tools import (
    feishu_attendee_message_send,
    feishu_chat_members_get,
    feishu_chats_search,
    feishu_contacts_search,
    feishu_final_invitations_send,
    feishu_meeting_attendee_status_list,
    feishu_meeting_create,
    feishu_meeting_delivery_task_requeue,
    feishu_meeting_escalation_retry_tick,
    feishu_meeting_monitor_start,
    feishu_meeting_monitor_stop,
    feishu_meeting_monitor_tick,
    feishu_meeting_negotiation_finalize,
    feishu_meeting_negotiation_next_round_prompts,
    feishu_meeting_negotiation_start,
    feishu_meeting_negotiation_submit_response,
    feishu_meeting_new_time_propose,
    feishu_meeting_time_update,
)


def _object_schema(properties, *, required=()):
    return {
        "type": "object",
        "properties": properties,
        "required": list(required),
        "additionalProperties": False,
    }


def _function_schema(name: str) -> dict:
    return {"parameters": TOOL_SCHEMAS[name]}


_STRING_LIST_SCHEMA = {"type": "array", "items": {"type": "string"}}
_ATTENDEE_SCHEMA = {
    "type": "array",
    "description": (
        "Meeting invitees, excluding the requester. Infer from the user's request when clear. Items may be "
        "Feishu open_id strings, emails, display names, group phrases, or objects "
        "with open_id, email, name, group_phrase, and is_optional."
    ),
    "items": {
        "oneOf": [
            {"type": "string"},
            _object_schema(
                {
                    "open_id": {"type": "string"},
                    "email": {"type": "string"},
                    "name": {"type": "string"},
                    "group_phrase": {"type": "string"},
                    "is_optional": {"type": "boolean"},
                }
            ),
        ]
    },
}
_CREATOR_BINDING_SCHEMA = _object_schema(
    {
        "platform": {"type": "string"},
        "workspace_id": {"type": "string"},
        "session_id": {"type": "string"},
        "session_key": {"type": "string"},
        "chat_id": {"type": "string"},
        "thread_id": {"type": "string"},
        "origin_user_id": {"type": "string"},
    }
)
_SIMPLE_RESULT_STATE_SCHEMA = {
    "type": "object",
    "description": "State payload returned by a previous negotiation tool call.",
    "additionalProperties": True,
}


TOOL_SCHEMAS = {
    "feishu_contacts_search": _object_schema(
        {
            "query": {
                "type": "string",
                "description": (
                    "Single attendee name, email, or Feishu open_id to search for. "
                    "Do not use this for the requester."
                ),
            },
            "queries": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Attendee names, emails, or Feishu open_id values to search one by one.",
            },
            "attendees": {
                **_ATTENDEE_SCHEMA,
                "description": (
                    "Invitee list inferred from the user's request, excluding the requester. "
                    "The tool searches each unresolved attendee."
                ),
            },
            "participants": {
                **_ATTENDEE_SCHEMA,
                "description": "Alias for attendees; exclude the requester.",
            },
            "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 10},
        },
    ),
    "feishu_chats_search": _object_schema(
        {
            "query": {
                "type": "string",
                "description": "Chat or group name/phrase to search for. Infer from group mentions.",
            },
            "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 10},
        },
        required=("query",),
    ),
    "feishu_chat_members_get": _object_schema(
        {
            "chat_id": {"type": "string", "description": "Feishu chat_id returned by feishu_chats_search."},
            "member_id_type": {
                "type": "string",
                "enum": ["open_id", "union_id", "user_id"],
                "default": "open_id",
            },
        },
        required=("chat_id",),
    ),
    "feishu_meeting_create": _object_schema(
        {
            "title": {"type": "string", "description": "Meeting title. Infer from the user's request when clear."},
            "start_time": {
                "type": "string",
                "description": "Meeting start time as ISO-8601 or an unambiguous local datetime.",
            },
            "end_time": {
                "type": "string",
                "description": "Meeting end time as ISO-8601 or an unambiguous local datetime.",
            },
            "duration_minutes": {
                "type": "integer",
                "minimum": 1,
                "description": "Optional duration used by the agent to infer end_time before calling the tool.",
            },
            "timezone": {"type": "string", "default": "Asia/Shanghai"},
            "attendees": _ATTENDEE_SCHEMA,
            "attendee_open_ids": {
                **_STRING_LIST_SCHEMA,
                "description": "Resolved Feishu open_id invitees; alias for attendees.",
            },
            "attendee_open_id": {
                "type": "string",
                "description": "Single resolved Feishu open_id invitee; alias for attendee.",
            },
            "attendee": {
                "description": "Single attendee alias for attendees.",
                "oneOf": [{"type": "string"}, {"type": "object", "additionalProperties": True}],
            },
            "participants": _ATTENDEE_SCHEMA,
            "participant": {
                "description": "Single participant alias for attendees.",
                "oneOf": [{"type": "string"}, {"type": "object", "additionalProperties": True}],
            },
            "description": {"type": "string"},
            "location": {"type": "string"},
            "idempotency_key": {"type": "string"},
            "requester_open_id": {
                "type": "string",
                "description": (
                    "Requester Feishu open_id. Leave unset during Feishu chat sessions; "
                    "the tool derives it from the chat initiator."
                ),
            },
            "requester_calendar_id": {"type": "string"},
            "start_rsvp_monitor": {
                "type": "boolean",
                "default": True,
                "description": "Whether to start automatic RSVP follow-up monitoring after creation.",
            },
            "is_recurrent_meeting": {
                "type": "boolean",
                "description": "Unsupported in v0.1; true requests must be clarified or rejected.",
            },
        },
        required=("title", "start_time", "end_time"),
    ),
    "feishu_meeting_negotiation_start": _object_schema(
        {
            "title": {"type": "string"},
            "requester_open_id": {"type": "string"},
            "attendee_open_ids": _STRING_LIST_SCHEMA,
            "attendee_open_id": {"type": "string"},
            "candidate_slots": _STRING_LIST_SCHEMA,
            "candidate_slot": {"type": "string"},
            "duration_minutes": {"type": "integer", "minimum": 1},
            "timezone": {"type": "string", "default": "Asia/Shanghai"},
            "max_rounds": {"type": "integer", "minimum": 1, "default": 3},
        },
        required=("title", "requester_open_id", "attendee_open_ids", "candidate_slots", "duration_minutes"),
    ),
    "feishu_meeting_negotiation_next_round_prompts": _object_schema(
        {
            "state": _SIMPLE_RESULT_STATE_SCHEMA,
            "state_payload": _SIMPLE_RESULT_STATE_SCHEMA,
        }
    ),
    "feishu_meeting_negotiation_submit_response": _object_schema(
        {
            "state": _SIMPLE_RESULT_STATE_SCHEMA,
            "state_payload": _SIMPLE_RESULT_STATE_SCHEMA,
            "attendee_open_id": {"type": "string"},
            "accepted_slots": _STRING_LIST_SCHEMA,
            "accepted_slot": {"type": "string"},
            "declined_slots": _STRING_LIST_SCHEMA,
            "declined_slot": {"type": "string"},
            "note": {"type": "string"},
        },
        required=("attendee_open_id",),
    ),
    "feishu_meeting_negotiation_finalize": _object_schema(
        {
            "state": _SIMPLE_RESULT_STATE_SCHEMA,
            "state_payload": _SIMPLE_RESULT_STATE_SCHEMA,
            "description": {"type": "string"},
            "location": {"type": "string"},
        }
    ),
    "feishu_meeting_attendee_status_list": _object_schema(
        {
            "event_id": {"type": "string"},
            "calendar_id": {"type": "string"},
            "requester_open_id": {"type": "string"},
            "page_size": {"type": "integer", "minimum": 1, "maximum": 100, "default": 50},
        },
        required=("event_id",),
    ),
    "feishu_final_invitations_send": _object_schema(
        {
            "attendee_open_ids": _STRING_LIST_SCHEMA,
            "attendee_open_id": {"type": "string"},
            "title": {"type": "string"},
            "start_time": {"type": "string"},
            "end_time": {"type": "string"},
            "timezone": {"type": "string", "default": "Asia/Shanghai"},
            "meeting_link": {"type": "string"},
        },
        required=("attendee_open_ids", "title", "start_time", "end_time"),
    ),
    "feishu_attendee_message_send": _object_schema(
        {
            "attendee_open_ids": _STRING_LIST_SCHEMA,
            "attendee_open_id": {"type": "string"},
            "message": {"type": "string"},
        },
        required=("attendee_open_ids", "message"),
    ),
    "feishu_meeting_new_time_propose": _object_schema(
        {
            "attendee_open_ids": _STRING_LIST_SCHEMA,
            "attendee_open_id": {"type": "string"},
            "title": {"type": "string"},
            "candidate_slots": _STRING_LIST_SCHEMA,
            "candidate_slot": {"type": "string"},
            "timezone": {"type": "string", "default": "Asia/Shanghai"},
            "event_id": {"type": "string"},
            "current_time": {"type": "string"},
            "note": {"type": "string"},
        },
        required=("attendee_open_ids", "title", "candidate_slots"),
    ),
    "feishu_meeting_time_update": _object_schema(
        {
            "event_id": {"type": "string"},
            "calendar_id": {"type": "string"},
            "start_time": {"type": "string"},
            "end_time": {"type": "string"},
            "timezone": {"type": "string", "default": "Asia/Shanghai"},
        },
        required=("event_id", "calendar_id", "start_time", "end_time"),
    ),
    "feishu_meeting_monitor_start": _object_schema(
        {
            "workspace_id": {"type": "string"},
            "platform": {"type": "string", "default": "feishu"},
            "event_id": {"type": "string"},
            "event_revision_id": {"type": "string"},
            "calendar_id": {"type": "string"},
            "meeting_title": {"type": "string"},
            "meeting_start_time": {"type": "string"},
            "meeting_end_time": {"type": "string"},
            "timezone": {"type": "string", "default": "Asia/Shanghai"},
            "attendees": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
            "creator_delivery_binding": _CREATOR_BINDING_SCHEMA,
        },
        required=("workspace_id", "event_id", "event_revision_id", "calendar_id"),
    ),
    "feishu_meeting_monitor_tick": _object_schema(
        {
            "monitor_id": {"type": "string"},
            "workspace_id": {"type": "string"},
        }
    ),
    "feishu_meeting_monitor_stop": _object_schema(
        {
            "monitor_id": {"type": "string"},
            "workspace_id": {"type": "string"},
            "reason": {"type": "string"},
        }
    ),
    "feishu_meeting_escalation_retry_tick": _object_schema(
        {
            "workspace_id": {"type": "string"},
        },
        required=("workspace_id",),
    ),
    "feishu_meeting_delivery_task_requeue": _object_schema(
        {
            "delivery_task_id": {"type": "string"},
            "reason": {"type": "string"},
        },
        required=("delivery_task_id",),
    ),
}
TOOL_SCHEMAS["feishu_contacts_search"]["anyOf"] = [
    {"required": ["query"]},
    {"required": ["queries"]},
    {"required": ["attendees"]},
    {"required": ["participants"]},
]


def register(ctx) -> None:
    ctx.register_skill(
        name="feishu-bot-meeting-coordinator",
        path=Path(__file__).with_name("SKILL.md"),
        description="Book Feishu meetings and start RSVP monitoring via the bundled plugin.",
    )
    ctx.register_tool(
        name="feishu_contacts_search",
        handler=feishu_contacts_search,
        description="Search Feishu contacts by name, email, or open_id using the governed bot configuration.",
        schema=_function_schema("feishu_contacts_search"),
        toolset="meeting-coordinator",
    )
    ctx.register_tool(
        name="feishu_chats_search",
        handler=feishu_chats_search,
        description="Search Feishu chats/groups visible to the bot.",
        schema=_function_schema("feishu_chats_search"),
        toolset="meeting-coordinator",
    )
    ctx.register_tool(
        name="feishu_chat_members_get",
        handler=feishu_chat_members_get,
        description="List members of a Feishu chat/group as open_id values.",
        schema=_function_schema("feishu_chat_members_get"),
        toolset="meeting-coordinator",
    )
    ctx.register_tool(
        name="feishu_meeting_create",
        handler=feishu_meeting_create,
        description=(
            "Create an online Feishu calendar meeting and send attendee invitations. "
            "Infer title, time, duration, timezone, and participants from the user request when unambiguous."
        ),
        schema=_function_schema("feishu_meeting_create"),
        toolset="meeting-coordinator",
    )
    ctx.register_tool(
        name="feishu_meeting_negotiation_start",
        handler=feishu_meeting_negotiation_start,
        description="Start a multi-round Feishu meeting time negotiation.",
        schema=_function_schema("feishu_meeting_negotiation_start"),
        toolset="meeting-coordinator",
    )
    ctx.register_tool(
        name="feishu_meeting_negotiation_next_round_prompts",
        handler=feishu_meeting_negotiation_next_round_prompts,
        description="Build attendee prompts for the current negotiation round.",
        schema=_function_schema("feishu_meeting_negotiation_next_round_prompts"),
        toolset="meeting-coordinator",
    )
    ctx.register_tool(
        name="feishu_meeting_negotiation_submit_response",
        handler=feishu_meeting_negotiation_submit_response,
        description="Record one attendee response for a Feishu meeting time negotiation.",
        schema=_function_schema("feishu_meeting_negotiation_submit_response"),
        toolset="meeting-coordinator",
    )
    ctx.register_tool(
        name="feishu_meeting_negotiation_finalize",
        handler=feishu_meeting_negotiation_finalize,
        description="Finalize an agreed Feishu meeting negotiation and create the calendar event.",
        schema=_function_schema("feishu_meeting_negotiation_finalize"),
        toolset="meeting-coordinator",
    )
    ctx.register_tool(
        name="feishu_meeting_attendee_status_list",
        handler=feishu_meeting_attendee_status_list,
        description="Read live RSVP status for a Feishu calendar event.",
        schema=_function_schema("feishu_meeting_attendee_status_list"),
        toolset="meeting-coordinator",
    )
    ctx.register_tool(
        name="feishu_final_invitations_send",
        handler=feishu_final_invitations_send,
        description="Send final Feishu meeting confirmation messages to attendee open_id values.",
        schema=_function_schema("feishu_final_invitations_send"),
        toolset="meeting-coordinator",
    )
    ctx.register_tool(
        name="feishu_attendee_message_send",
        handler=feishu_attendee_message_send,
        description="Send a direct Feishu text message to attendee open_id values.",
        schema=_function_schema("feishu_attendee_message_send"),
        toolset="meeting-coordinator",
    )
    ctx.register_tool(
        name="feishu_meeting_new_time_propose",
        handler=feishu_meeting_new_time_propose,
        description="Send attendees a Feishu message proposing replacement meeting times.",
        schema=_function_schema("feishu_meeting_new_time_propose"),
        toolset="meeting-coordinator",
    )
    ctx.register_tool(
        name="feishu_meeting_time_update",
        handler=feishu_meeting_time_update,
        description="Update a Feishu meeting event start and end time.",
        schema=_function_schema("feishu_meeting_time_update"),
        toolset="meeting-coordinator",
    )
    ctx.register_tool(
        name="feishu_meeting_monitor_start",
        handler=feishu_meeting_monitor_start,
        description="Start or repair RSVP monitoring for a Feishu meeting revision.",
        schema=_function_schema("feishu_meeting_monitor_start"),
        toolset="meeting-coordinator",
    )
    ctx.register_tool(
        name="feishu_meeting_monitor_tick",
        handler=feishu_meeting_monitor_tick,
        description="Run one RSVP monitor tick.",
        schema=_function_schema("feishu_meeting_monitor_tick"),
        toolset="meeting-coordinator",
    )
    ctx.register_tool(
        name="feishu_meeting_monitor_stop",
        handler=feishu_meeting_monitor_stop,
        description="Stop one RSVP monitor and remove its cron job.",
        schema=_function_schema("feishu_meeting_monitor_stop"),
        toolset="meeting-coordinator",
    )
    ctx.register_tool(
        name="feishu_meeting_escalation_retry_tick",
        handler=feishu_meeting_escalation_retry_tick,
        description="Retry pending creator escalation delivery tasks.",
        schema=_function_schema("feishu_meeting_escalation_retry_tick"),
        toolset="meeting-coordinator",
    )
    ctx.register_tool(
        name="feishu_meeting_delivery_task_requeue",
        handler=feishu_meeting_delivery_task_requeue,
        description="Requeue a failed creator escalation delivery task and heal the retry cron.",
        schema=_function_schema("feishu_meeting_delivery_task_requeue"),
        toolset="meeting-coordinator",
    )
    ctx.register_cli_command(
        name="feishu-meeting-coordinator",
        help="Inspect and operate Feishu meeting RSVP monitors",
        setup_fn=register_cli,
        handler_fn=command,
        description="Operator CLI for Feishu meeting RSVP monitoring.",
    )
