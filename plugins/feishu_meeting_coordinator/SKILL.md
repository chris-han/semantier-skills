---
name: feishu-bot-meeting-coordinator
description: >
  Book Feishu meetings and run deterministic follow-up negotiation workflows
  through the bundled plugin.
version: 1.0.0
author: Semantier
license: MIT
tags:
  - feishu
  - calendar
  - meetings
  - contacts
---

# Feishu Bot Meeting Coordinator

When a user books a Feishu meeting with `feishu_meeting_create`, the tool creates the event and leaves RSVP follow-up orchestration to the durable negotiation follow-up flow.

Infer meeting parameters from the conversation as much as possible before asking the user. For example, infer title, date, start time, duration/end time, timezone, online meeting format, organizer, and named participants when the user's request is unambiguous. Build an attendee list from invitees only and exclude the requester. If named attendees are not already Feishu `open_id` values or emails, call `feishu_contacts_search` with `attendees` or `queries` so each attendee is searched, then pass the resolved attendee `open_id` values into meeting creation. Ask the user only when a required value is missing or ambiguous, such as multiple matching contacts, unclear date, missing duration/end time, or uncertain attendee identity.

For `feishu_meeting_create` in an active Feishu chat, do not fill `requester_open_id` from an attendee, invitee, meeting calendar, or guessed contact. The tool derives the requester from the Feishu chat initiator.

When a user asks for RSVP status, call live Feishu attendee status first. Do not infer RSVP state from memory.

The plugin handles follow-up reminders, creator escalation, delivery retry, and cron repair.

For a Kanban task whose body has `metadata.task_type` equal to `feishu_meeting_negotiation`, run the durable negotiation worker through `feishu_meeting_negotiation_kanban_worker_tick` with the Kanban task id and full task body. Do not manually send ad hoc messages for `pending_decliner_input`; the worker calls the deterministic negotiation tick, sends the decliner prompt once, and blocks or completes the Kanban task according to persisted state.

Use the registered Feishu tools directly for contact lookup, chat lookup, meeting creation, attendee messaging, direct RSVP checks, replacement slot proposals, and meeting-time updates:

- `feishu_contacts_search`
- `feishu_chats_search`
- `feishu_chat_members_get`
- `feishu_meeting_create`
- `feishu_meeting_negotiation_case_tick`
- `feishu_meeting_negotiation_kanban_worker_tick`
- `feishu_meeting_negotiation_start`
- `feishu_meeting_negotiation_next_round_prompts`
- `feishu_meeting_negotiation_submit_response`
- `feishu_meeting_negotiation_finalize`
- `feishu_meeting_attendee_status_list`
- `feishu_final_invitations_send`
- `feishu_attendee_message_send`
- `feishu_meeting_new_time_propose`
- `feishu_meeting_time_update`

Do not use terminal, `write_file`, `execute_code`, generated Python, generated shell scripts, raw HTTP calls, or temporary files such as `/tmp/create_feishu_meeting.py` for Feishu meeting, contact, chat, or calendar operations. Do not synthesize commands such as `hermes feishu ...` or `python .../feishu_bot_api.py ...`.

If one of the registered Feishu tools needed for the task is unavailable, stop and report that the Feishu meeting-coordinator tool surface is not loaded. Do not work around the missing tool by generating code at runtime.

The plugin tools call `scripts/feishu_bot_api.py` directly. The returned `user_id` / `message_user_id` values from RSVP lookups are Feishu `open_id` values and can be passed directly into direct-message follow-up tooling.
