---
name: feishu-bot-meeting-coordinator
description: >
  Coordinate Feishu bot-assisted contact search and meeting scheduling for
  workspace users. Use this skill when the Semantier backend is configured to
  run multi-round attendee availability negotiation, then create the final
  calendar events on the requester's calendar with attendee invitations,
  and deliver invitations.
version: 1.0.0
author: Semantier
license: MIT
tags:
  - feishu
  - calendar
  - meetings
  - contacts
triggers:
  - schedule a feishu meeting
  - find feishu contacts
  - invite contacts in feishu
  - create feishu meeting
  - search feishu contact
  - 创建飞书会议
  - 安排飞书会议
  - 搜索飞书联系人
  - 飞书会议邀请
metadata:
  hermes:
    tags: [feishu, calendar, meetings, contacts]
    config:
      - key: feishu.bot.identity
        description: Human-readable organizer identity for the installed Feishu bot
        default: semantier
        prompt: Feishu bot organizer identity
      - key: feishu.bot.timezone
        description: Default timezone to use when the user does not specify one
        default: Asia/Shanghai
        prompt: Default timezone for Feishu meetings
      - key: feishu.bot.contact_scope
        description: Expected contact visibility model for the bot's searchable contacts
        default: contacts-added-to-bot
        prompt: Bot contact visibility mode
---

# Feishu Bot Meeting Coordinator

## Purpose

Use this skill to coordinate a Feishu bot that can:

- search the bot's visible contact list
- run multi-round availability negotiation with each attendee
- create calendar meetings via the bot's calendar after agreement (with requester as organizer identity where supported)
- invite user-selected contacts to the meeting

This skill is for the direct Feishu bot/API path.

## Runtime Contract: Script Materialization

**IMPORTANT**: This skill is intended for Semantier/Hermes runtimes that materialize helper scripts into a per-task sandbox before execution.

### What You Don't Do
- Do NOT reference absolute system paths like `/home/chris/repo/semantier/agent/src/skills/...`
- Do NOT use `skill_view(...)` to extract and inline script source code into terminal commands
- Do NOT use hardcoded paths in terminal commands

### What the Wrapper Layer Does (Automatically)
The runtime wrapper automatically:

1. **Detects** that this skill execution needs the helper script
2. **Materializes** the shared script from the installed skill package at `skills/feishu-bot-meeting-coordinator/scripts/feishu_bot_api.py` into the task sandbox
3. **Exposes** the script at a sandbox-relative path like `.scripts/feishu-bot-meeting-coordinator/scripts/feishu_bot_api.py`
4. **Cleans up** the script when the task completes (no leftovers)

This ensures:
- ✅ No sandbox escape attempts
- ✅ No cross-task interference (each task gets its own copy)
- ✅ Works across all deployment models (local, Docker, serverless)

## Execution Surface

### Loading the Helper

Before attempting contact search or meeting creation, load the helper code with `skill_view(name="feishu-bot-meeting-coordinator", file_path="scripts/feishu_bot_api.py")`.

The wrapper layer automatically injects the helper script into your workspace. **You reference it as a relative path in the task sandbox**, not as a system path.

**Example usage in Python/bash**:

```bash
# Terminal command (wrapper materializes to task sandbox automatically)
python .scripts/feishu-bot-meeting-coordinator/scripts/feishu_bot_api.py search-chats --query "管理层群"
```

**Credentials and Config**:
- Credentials are loaded from the active Hermes/Semantier governed SQLite auth store
- Workspace config such as timezone and organizer identity should come from the active runtime config
- You do NOT ask users to verify environment variables or provide secrets in chat

## Repository Install Paths

This standalone repository is designed so the installable skill lives at:

- `skills/feishu-bot-meeting-coordinator/SKILL.md`
- `skills/feishu-bot-meeting-coordinator/scripts/feishu_bot_api.py`

For GitHub-backed installation flows, the canonical identifier after publish is:

```text
chris-han/publishable-skills/feishu-bot-meeting-coordinator/skills/feishu-bot-meeting-coordinator
```

For raw-URL installation flows, the canonical SKILL path after publish is:

```text
https://raw.githubusercontent.com/chris-han/publishable-skills/main/feishu-bot-meeting-coordinator/skills/feishu-bot-meeting-coordinator/SKILL.md
```

### Helper API Surface

The materialized script provides:

```python
# search-chats: Find contact groups by keyword
python .scripts/feishu-bot-meeting-coordinator/scripts/feishu_bot_api.py \
  search-chats --query "管理层群" --limit 5

# get-chat-members: Retrieve all members of a contact group
python .scripts/feishu-bot-meeting-coordinator/scripts/feishu_bot_api.py \
  get-chat-members --chat-id "oc_abc123"

# search-contacts: Find individual contacts by name or email
python .scripts/feishu-bot-meeting-coordinator/scripts/feishu_bot_api.py \
  search-contacts --query "Alex" --limit 10

# start-negotiation: Start a multi-round availability negotiation
python .scripts/feishu-bot-meeting-coordinator/scripts/feishu_bot_api.py \
  start-negotiation --title "项目汇报会" \
    --requester-open-id "ou_requester_001" --duration-minutes 30 \
    --attendee-open-id "ou_a" --attendee-open-id "ou_b" \
    --candidate-slot "2026-04-28 15:00" --candidate-slot "2026-04-28 15:30"

# submit-response: Record an attendee response for the current round
python .scripts/feishu-bot-meeting-coordinator/scripts/feishu_bot_api.py \
  submit-response --state-json '<state-json>' --attendee-open-id "ou_a" \
    --accepted-slot "2026-04-28 15:00"

# finalize-negotiation: Create meetings after a slot is agreed
python .scripts/feishu-bot-meeting-coordinator/scripts/feishu_bot_api.py \
  finalize-negotiation --state-json '<state-json>' --description "项目进度汇报"

# create-meeting: Create calendar event after agreement
python .scripts/feishu-bot-meeting-coordinator/scripts/feishu_bot_api.py \
  create-meeting --title "项目汇报会" \
    --start-time "2026-04-28 15:00" --end-time "2026-04-28 15:30" \
    --attendee "ou_attendee_001" --attendee "ou_attendee_002" --description "项目进度汇报"
```

## Installed Skill Config

When this skill is installed into a workspace, use the configured values as follows:

- `feishu.bot.identity`: treat as the organizer identity to reference in summaries and confirmations; use `semantier` as the default organizer identity for Feishu functions
- `feishu.bot.timezone`: use as the default timezone for proposed meeting times
- `feishu.bot.contact_scope`: assume this describes which contacts are expected to be discoverable by the bot

## Operating Rules

1. **The requester (Feishu message sender) is always the default meeting owner.** For Feishu channel sessions, the runtime automatically injects `FEISHU_REQUESTER_OPEN_ID=<sender_open_id>` into the command environment when invoking `feishu_bot_api.py` via the terminal tool. For non-Feishu channels (for example web), `FEISHU_REQUESTER_OPEN_ID` is NOT auto-injected. In that case you MUST determine the requester's identity (for example by asking the user or searching contacts) and pass `--requester-open-id` explicitly. If you use the Python API directly (importing functions from the script), you MUST pass `requester_open_id` explicitly in all cases. Never default to the `semantier` bot identity as meeting owner.
1a. **Calendar ownership:** The script first attempts to create the event on the requester's primary calendar. If Feishu returns `191002` (bot lacks write access), it falls back to the bot's own calendar. Attendees still receive proper invitations via the separate `calendar_event_attendee.create` API.
1b. **Organizer display:** On the bot calendar, Feishu ignores `event_organizer` and always shows the bot as the organizer. The requester is implicitly added as an attendee so the event appears on their calendar. If the user complains about the organizer showing as "semantier", explain that this is a Feishu platform limitation when using the bot calendar fallback.
1a. If the user explicitly designates a different organizer (for example: `组织者是 X` or `organizer is X`), you MAY use that designated organizer instead of the requester, but you MUST obtain explicit approval from that organizer first.
1b. If `organizer` and `requester` are not the same person, you MUST obtain explicit approval from the designated organizer before running `create-meeting` or `finalize-negotiation`.
1c. Approval must be explicit and attributable to the designated organizer (clear yes/approve intent). If approval is missing or ambiguous, do not create events.
2. **MANDATORY**: When any required meeting field is missing, you MUST emit the `a2ui` `schema_form` block defined in the **Missing Input A2UI Contract** section below. A free-form markdown bullet list asking for the same fields is NEVER acceptable — even when reading the skill for the first time.
2a. When the agent is not certain about any required meeting field, it must ask the user to clarify via that form. Do not silently assume a default duration, attendee list, or other required value.
2b. Before creating an event, if any parameter is inferred/defaulted (for example duration, timezone, description, or selected organizer/requester), you MUST show a pre-create review `schema_form` with those default values and ask whether to edit or approve.
2c. Do not persist confirmation or review forms through file tools. Render the `a2ui` `schema_form` directly in the assistant response and avoid temporary files (for example `/tmp/*.md`) or any absolute host path.
3. Resolve attendees through the materialized `feishu_bot_api.py` script rather than guessing account identifiers.
4. Confirm ambiguous contact matches before creating the meeting.
5. Run attendee negotiation rounds until all attendees agree on one slot or rounds are exhausted.
6. After agreement, create the meeting. The script attempts the requester's calendar first, then falls back to the bot calendar. Attendees are added via the dedicated `calendar_event_attendee.create` API (Feishu silently ignores `attendees` in the create-event body). The event is configured with `attendee_ability="can_see_others"` so participants can see each other's names.
7. Treat the requester as the meeting owner identity in summaries and final outputs.
7a. If organizer override is used, include both identities explicitly in confirmations: organizer identity and requester identity.
7b. Never execute create-event calls when organizer approval is still pending.
8. Send final invitation notifications to each resolved attendee after event creation.
9. Summarize invitees, timezone, and schedule before final confirmation when the user request is ambiguous.
10. Treat app secrets, user tokens, and webhook secrets as backend-owned secrets. Never ask the user to paste them into chat or store them in skill config.
11. When the attendee expression contains a group phrase (for example `管理层群`, `管理层群里的所有人`), pass the **exact user phrase** directly to `create-meeting` as an attendee. Do NOT substitute it with the resolved chat name. The script automatically resolves group members via Feishu chat/member APIs. You do NOT need to manually run `search-chats` and `get-chat-members` before `create-meeting` unless the user explicitly asks to preview the member list.

## Completion Guardrails

- **Getting group members is NEVER the final step.** If the user's request was to schedule a meeting, after resolving attendees you MUST proceed to `create-meeting` or `start-negotiation`. Never return a member table as the final answer.
- **Prefer the direct creation path.** Do not break `create-meeting` into manual `search-chats` → `get-chat-members` steps unless the user explicitly asks to see the member list first.
- **Always use exact IDs from search results.** When you do use `get-chat-members`, pass the `chat_id` exactly as returned by `search-chats`. Never invent, guess, or reuse chat_ids from examples or memory.

## Direct Meeting Creation Path (Recommended)

When the user provides enough information (title, time, attendees including group names), use the direct path:

```bash
python .scripts/feishu-bot-meeting-coordinator/scripts/feishu_bot_api.py \
  create-meeting \
    --title "项目汇报会" \
    --start-time "2026-04-25 16:00" \
    --end-time "2026-04-25 16:30" \
    --attendee "管理层群里的所有人" \
    --attendee "chris han"
```

The `create-meeting` command automatically resolves:
- Group phrases like `管理层群` into all group members
- Individual names into contacts via search
- Emails into user IDs

You do NOT need to manually run `search-chats` and `get-chat-members` before `create-meeting` unless the user explicitly asks to preview the member list first.

## Implementation Guidelines: Using the Materialized Script

### Step 1: Search for Contacts or Groups

```bash
# Search for a contact group (if user specifies "管理层群")
python .scripts/feishu-bot-meeting-coordinator/scripts/feishu_bot_api.py \
  search-chats --query "管理层群" --limit 5

# Expected output (JSON):
# {
#   "ok": true,
#   "result": {
#     "query": "管理层群",
#     "candidates": [
#       {"chat_id": "oc_abc123", "name": "管理层群", "score": 1.0}
#     ]
#   ]
# }
```

### Step 2: Get Group Members (if applicable)

```bash
# Retrieve members of the contact group
python .scripts/feishu-bot-meeting-coordinator/scripts/feishu_bot_api.py \
  get-chat-members --chat-id "oc_abc123"

# Expected output (JSON):
# {
#   "ok": true,
#   "result": [
#     {"open_id": "ou_attendee_001", "display_name": "Alex"}
#   ]
# }
```

### Step 3: Propose Meeting Slots

> Important: the state JSON below is a synthetic fixture for documentation tests.
> Never reuse literal `negotiation_id`, attendee names, or open IDs from examples in live commands.

```bash
# Start a multi-round negotiation for the candidate time slots
python .scripts/feishu-bot-meeting-coordinator/scripts/feishu_bot_api.py \
  start-negotiation \
    --title "项目汇报会" \
    --duration-minutes 30 \
    --attendee-open-id "ou_attendee_001" \
    --attendee-open-id "ou_attendee_002" \
    --candidate-slot "2026-04-28 15:00" \
    --candidate-slot "2026-04-28 15:30"

# Expected output (JSON):
# {
#   "ok": true,
#   "result": {
#     "negotiation_id": "negotiation_example_001",
#     "status": "negotiating",
#     "current_round": 1
#   }
# }
```

### Step 4: Create Meeting After Agreement

```bash
# Create the final calendar event directly when the attendee list is already known
python .scripts/feishu-bot-meeting-coordinator/scripts/feishu_bot_api.py \
  create-meeting \
    --title "项目汇报会" \
    --description "按照既定时间进行项目进度汇报" \
    --start-time "2026-04-28 15:00" \
    --end-time "2026-04-28 15:30" \
    --attendee "ou_attendee_001" \
    --attendee "ou_attendee_002"

# Expected output (JSON):
# {
#   "ok": true,
#   "result": {
#     "event_id": "event_123xyz",
#     "join_url": "https://feishu.example.com/calendar/event/event_123xyz"
#   }
# }
```

### Step 5: Finalize Negotiation After Agreement

```bash
# Finalize a negotiation state and create the meeting on the requester's calendar
python .scripts/feishu-bot-meeting-coordinator/scripts/feishu_bot_api.py \
  finalize-negotiation \
    --state-json '<state-json>' \
    --description "会议已创建，请准时参加"

# Expected output (JSON):
# {
#   "ok": true,
#   "result": {
#     "meeting_owner_open_id": "ou_requester_001",
#     "meetings": []
#   }
# }
```

## Missing Input A2UI Contract

When required meeting fields are missing, emit this schema form (do NOT use markdown lists):

```json
{
  "type": "schema_form",
  "title": "补全会议信息",
  "description": "请提供以下信息以完成会议安排",
  "fields": [
    {
      "name": "title",
      "label": "会议主题",
      "type": "text",
      "required": true,
      "placeholder": "例如：项目汇报会",
      "help": "会议的标题和目的"
    },
    {
      "name": "time",
      "label": "会议时间",
      "type": "datetime",
      "required": true,
      "placeholder": "2026-04-28T10:00",
      "help": "建议时间 (ISO 8601 格式)"
    },
    {
      "name": "duration",
      "label": "会议时长（分钟）",
      "type": "number",
      "required": true,
      "placeholder": "30",
      "help": "会议预期时长"
    },
    {
      "name": "attendees",
      "label": "参会人员",
      "type": "multiselect",
      "required": true,
      "placeholder": "选择参会人员",
      "help": "从联系人中选择参与者",
      "options": []
    }
  ]
}
```

## Card 2.0 Interaction Mode: Alternatives and Migration

### Compatibility Baseline

- In **custom bot webhook mode**, Card 2.0 is treated as one-way push UI for this skill.
- Do not emit callback-style submit interactions in custom bot mode.
- Use one of these alternatives instead:
  - **Option A (preferred in webhook mode)**: markdown guidance and chat text reply collection.
  - **Option B**: URL-only button flow (`open_url`) that redirects to an external form page.

### Hard Guardrails for Custom Bot Mode

- Never emit unsupported action container tags for submit flows.
- If required fields are missing, always render `schema_form` as display guidance plus text instructions to reply in chat.
- Treat user replies as the source of truth for form submission in webhook mode.

### Migration Checklist: Custom Bot -> App Bot Callback Flow

Use this checklist when you need true in-card submit behavior.

1. Platform setup:
  - Create or reuse a Feishu **App Bot** (not custom bot).
  - Enable bot capabilities for receiving and replying to messages.
  - Enable card callback handling in app configuration.
2. Permissions and events:
  - Apply required message and bot interaction permissions.
  - Subscribe to message/card callback events needed for submit processing.
3. Backend endpoint:
  - Add a dedicated callback endpoint for card interactions.
  - Verify request signatures and reject invalid callbacks.
  - Enforce idempotency on callback processing using callback/event IDs.
4. Data contract:
  - Map card field payloads to the meeting contract (`title`, `time`, `duration`, `attendees`).
  - Reuse existing server-side validation before any scheduling side effects.
5. Runtime branching:
  - Keep a mode switch in backend routing:
    - `custom_bot`: non-callback flow (markdown/open_url/text reply).
    - `app_bot`: callback submit flow.
  - Do not mix callback payload assumptions into custom bot pipeline.
6. Card rendering:
  - For `app_bot`, use callback-capable Card 2.0 interaction components.
  - For `custom_bot`, continue rendering non-callback-safe content only.
7. Rollout and fallback:
  - Ship behind a feature flag for selected workspaces.
  - Keep text-reply fallback active if callback validation fails.
8. Regression coverage:
  - Add tests proving custom bot path never emits callback-only elements.
  - Add tests proving app bot callback payloads are parsed and validated.
  - Add tests for callback signature failure and idempotency replay.

## Helper Entry Points

- Contact search CLI: `python scripts/feishu_bot_api.py search-contacts --query "Amy Q" --limit 5`
- Meeting creation CLI: `python scripts/feishu_bot_api.py create-meeting --title "项目同步" --start-time "2026-04-24 15:40" --end-time "2026-04-24 16:10" --attendee "Chris Han" --attendee "Amy Q"`
- Start negotiation CLI: `python scripts/feishu_bot_api.py start-negotiation --title "项目同步" --requester-open-id "ou_xxx" --duration-minutes 30 --attendee-open-id "ou_a" --attendee-open-id "ou_b" --candidate-slot "2026-04-24 15:40" --candidate-slot "2026-04-24 16:40"`
- Submit response CLI: `python scripts/feishu_bot_api.py submit-response --state-json '{...}' --attendee-open-id "ou_a" --accepted-slot "2026-04-24 15:40"`
- Finalize CLI: `python scripts/feishu_bot_api.py finalize-negotiation --state-json '{...}' --description "讨论项目进展"`
- Python API: import `search_contacts(...)`, `start_negotiation(...)`, `submit_attendee_response(...)`, `finalize_negotiation_and_create_meeting(...)`, and `create_meeting(...)` from `scripts/feishu_bot_api.py`.


## Missing Input A2UI Contract

> **MANDATORY OUTPUT FORMAT**: This is a hard constraint. When any required meeting field (title, time, duration, attendees) is missing, the only permitted response format is the `a2ui` `schema_form` block below followed by one short plain sentence. A markdown bullet list, numbered list, or prose request for the same information is a contract violation.

When the user wants to schedule a meeting but required fields are missing, emit exactly one fenced `a2ui` JSON block using `schema_form`, then add one short plain-language sentence below it. Do not precede it with a markdown list of questions.

Use this schema shape exactly for meeting scheduling. When a value is explicitly stated or clearly inferred from the user's message, set it as `default` on that field so the user can confirm or edit it. Use `placeholder` only when the field is truly unknown.

For example, if the user says "给我和管理层群里的所有人定个项目汇报会，今天下午6pm", emit a form where the inferred fields carry `default` and only truly unknown fields use `placeholder`:

```a2ui
{
  "version": "1.0",
  "root": {
    "component": "schema_form",
    "props": {
      "title": "请确认或编辑会议信息",
      "submitLabel": "提交会议信息",
      "followUp": "请根据以上会议信息继续搜索联系人并创建飞书会议。",
      "fields": [
        {
          "key": "meeting_title",
          "label": "会议主题",
          "type": "text",
          "required": true,
          "default": "项目汇报会",
          "placeholder": "例如：项目周会"
        },
        {
          "key": "meeting_time",
          "label": "会议时间",
          "type": "text",
          "required": true,
          "default": "今天下午 6:00",
          "placeholder": "例如：今天下午 3:40 或 2026-04-24 15:40"
        },
        {
          "key": "duration_value",
          "label": "会议时长数值",
          "type": "number",
          "required": true,
          "placeholder": "例如：30"
        },
        {
          "key": "duration_unit",
          "label": "会议时长单位",
          "type": "select",
          "required": true,
          "options": [
            { "label": "分钟", "value": "分钟" },
            { "label": "小时", "value": "小时" }
          ],
          "placeholder": "请选择时长单位"
        },
        {
          "key": "attendees",
          "label": "参会人员",
          "type": "text",
          "required": true,
          "default": "管理层群里的所有人",
          "placeholder": "例如：ou_attendee_001, ou_attendee_002"
        },
        {
          "key": "meeting_description",
          "label": "会议描述",
          "type": "textarea",
          "required": false,
          "placeholder": "可选：补充会议背景、议程或备注"
        }
      ]
    }
  }
}
```

Rules for this schema:

- Never include meta-instruction labels such as `根据技能说明`, `我需要了解以下信息`, or `我来帮您安排会议` as form fields.
- Never merge `会议时长` into a single hardcoded hour assumption. Always collect `duration_value` and `duration_unit` separately.
- Do not silently assume a default duration. Never prefill or preselect a required field with an uncertain guess merely to keep the flow moving. If `duration_value`, `duration_unit`, or another required field is truly unknown, use `placeholder` and leave it for the user to clarify.
- When a value is explicitly stated or clearly inferred from the user's message, you MUST set it as the `default` for that field so the user can confirm or edit it. This applies to `meeting_title`, `meeting_time`, `attendees`, and any other field where the user's intent is clear.
- `meeting_description` is optional and must remain `required: false`.
- If the user already supplied some fields, keep the same schema keys and prefill them with `default`. Only fields that are truly missing should rely on `placeholder`.
- If the attendee names might be ambiguous, still collect them in `attendees` first; resolve them through backend contact search after submit.

## Pre-Create Review and Approval A2UI Contract

After attendee resolution and before `create-meeting`/`finalize-negotiation`, if any value is inferred or defaulted, emit a review form with prefilled defaults and an explicit approve/edit choice.

Use this `a2ui` block shape:

```a2ui
{
  "version": "1.0",
  "root": {
    "component": "schema_form",
    "props": {
      "title": "确认并审批会议创建",
      "submitLabel": "提交确认",
      "followUp": "请根据审批结果继续：approve 则创建会议，edit 则先修改参数。",
      "fields": [
        {
          "key": "meeting_title",
          "label": "会议主题",
          "type": "text",
          "required": true,
          "default": "<resolved_or_default_title>"
        },
        {
          "key": "meeting_time",
          "label": "会议时间",
          "type": "text",
          "required": true,
          "default": "<resolved_or_default_time>"
        },
        {
          "key": "duration_value",
          "label": "会议时长数值",
          "type": "number",
          "required": true,
          "default": 30
        },
        {
          "key": "duration_unit",
          "label": "会议时长单位",
          "type": "select",
          "required": true,
          "options": [
            { "label": "分钟", "value": "分钟" },
            { "label": "小时", "value": "小时" }
          ],
          "default": "分钟"
        },
        {
          "key": "timezone",
          "label": "时区",
          "type": "text",
          "required": true,
          "default": "Asia/Shanghai"
        },
        {
          "key": "organizer_identity",
          "label": "组织者",
          "type": "text",
          "required": true,
          "default": "<resolved_organizer>"
        },
        {
          "key": "requester_identity",
          "label": "发起人",
          "type": "text",
          "required": true,
          "default": "<resolved_requester>"
        },
        {
          "key": "organizer_approval",
          "label": "组织者审批",
          "type": "select",
          "required": true,
          "options": [
            { "label": "approve", "value": "approve" },
            { "label": "edit", "value": "edit" }
          ]
        },
        {
          "key": "approval_note",
          "label": "审批备注",
          "type": "textarea",
          "required": false,
          "placeholder": "可选：记录组织者审批说明"
        }
      ]
    }
  }
}
```

Rules for review/approval form:

- This review form is required before create-event when inferred/defaulted values exist.
- If organizer and requester differ, `organizer_approval=approve` is mandatory before calling any create-event command.
- If user chooses `edit`, revise fields and re-confirm; do not create event in the same step.
- Keep audit clarity in final response: include organizer, requester, and whether organizer approval was obtained.

## Response Shape

For contact search results, prefer compact tables with columns for display name, Feishu identifier, and confidence or matching note.

For meeting creation, return:

- organizer identity
- requester identity
- meeting title
- start and end time with timezone
- invited contacts
- any contacts that could not be resolved

## Failure Handling

 If no matching contacts are found, report that clearly and ask for a refined name, department, or alias.
 If multiple contacts match, present the candidates and ask the user to choose.
 If the calendar operation fails, preserve the resolved attendee candidates so the user does not need to repeat them.
 If backend Feishu bot/API capability is unavailable in the current runtime, state that explicitly and ask the user whether to continue later after backend recovery or switch to a manual scheduling fallback.