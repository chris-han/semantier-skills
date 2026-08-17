from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_utc_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _db_path() -> Path:
    root = (
        Path(os.environ.get("SEMANTIER_LOCAL_STATE_DIR") or ".semantier-home")
        .expanduser()
        .resolve()
    )
    root.mkdir(parents=True, exist_ok=True)
    return root / "state.db"


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _canonical_json_array(values: list[Any]) -> str:
    return json.dumps(values, ensure_ascii=False, separators=(",", ":"))


def _hash_id(prefix: str, values: list[Any], *, length: int = 24) -> str:
    raw = _canonical_json_array(values).encode("utf-8")
    return f"{prefix}_{hashlib.sha256(raw).hexdigest()[:length]}"


def _monitor_id(workspace_id: str, event_id: str, event_revision_id: str) -> str:
    raw = f"{workspace_id}\0{event_id}\0{event_revision_id}".encode("utf-8")
    return f"m_{hashlib.sha256(raw).hexdigest()[:24]}"


def _negotiation_id(workspace_id: str, event_id: str, event_revision_id: str) -> str:
    return _hash_id(
        "neg",
        ["meeting_time_negotiation:v1", workspace_id, event_id, event_revision_id],
    )


TERMINAL_RSVP_STATUSES = {"accepted", "declined", "tentative"}
NON_TERMINAL_RSVP_STATUSES = {"needs_action", "unknown"}
ALL_RSVP_STATUSES = TERMINAL_RSVP_STATUSES | NON_TERMINAL_RSVP_STATUSES
DEFAULT_MAX_FOLLOWUPS = 3
TERMINAL_NEGOTIATION_STATUSES = {
    "consented",
    "requester_decided",
    "cancelled",
    "expired",
    "failed",
}
FOLLOWUP_CRON_STATUSES = {
    "not_created",
    "active",
    "paused",
    "disabled",
    "failed",
    "removed",
    "repair_required",
}
NEGOTIATION_CASE_LOCK_TTL_SECONDS = 90
_UNSET = object()
GUARDED_NEGOTIATION_PATCH_FIELDS = {
    "negotiation_id",
    "workspace_id",
    "monitor_id",
    "event_id",
    "event_revision_id",
    "calendar_id",
    "creator_user_id",
    "status",
    "created_at",
}


class MeetingCoordinatorStore:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path is not None else _db_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS meeting_rsvp_monitors (
                    monitor_id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    creator_user_id TEXT NOT NULL,
                    platform TEXT NOT NULL,
                    event_id TEXT NOT NULL,
                    event_revision_id TEXT NOT NULL,
                    calendar_id TEXT NOT NULL,
                    cron_job_id TEXT,
                    creator_delivery_binding_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    last_start_error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    completed_at TEXT,
                    last_checked_at TEXT,
                    payload_json TEXT NOT NULL,
                    UNIQUE(workspace_id, event_id, event_revision_id)
                );
                CREATE TABLE IF NOT EXISTS meeting_rsvp_attendees (
                    monitor_id TEXT NOT NULL,
                    attendee_user_id TEXT NOT NULL,
                    message_user_id TEXT,
                    display_name TEXT,
                    response_status TEXT NOT NULL,
                    last_response_at TEXT,
                    last_followup_at TEXT,
                    followup_count INTEGER NOT NULL DEFAULT 0,
                    delivery_status TEXT NOT NULL,
                    escalated_at TEXT,
                    PRIMARY KEY(monitor_id, attendee_user_id)
                );
                CREATE TABLE IF NOT EXISTS meeting_rsvp_followups (
                    followup_id TEXT PRIMARY KEY,
                    monitor_id TEXT NOT NULL,
                    attendee_user_id TEXT NOT NULL,
                    round_number INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    message_channel TEXT NOT NULL,
                    message_id TEXT,
                    error_detail TEXT,
                    created_at TEXT NOT NULL,
                    sent_at TEXT
                );
                CREATE TABLE IF NOT EXISTS meeting_rsvp_escalations (
                    escalation_id TEXT PRIMARY KEY,
                    monitor_id TEXT NOT NULL,
                    attendee_user_id TEXT NOT NULL,
                    creator_user_id TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    delivery_task_id TEXT,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS meeting_rsvp_delivery_tasks (
                    delivery_task_id TEXT PRIMARY KEY,
                    monitor_id TEXT NOT NULL,
                    workspace_id TEXT NOT NULL,
                    task_type TEXT NOT NULL,
                    target_user_id TEXT NOT NULL,
                    delivery_binding_json TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    attempt_count INTEGER NOT NULL DEFAULT 0,
                    next_attempt_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    result_detail TEXT
                );
                CREATE TABLE IF NOT EXISTS meeting_rsvp_workspace_state (
                    workspace_id TEXT PRIMARY KEY,
                    delivery_retry_scheduler_status TEXT NOT NULL,
                    delivery_retry_scheduler_detail TEXT,
                    max_followups INTEGER NOT NULL DEFAULT 3,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS meeting_time_negotiations (
                    negotiation_id TEXT PRIMARY KEY,
                    monitor_id TEXT NOT NULL,
                    workspace_id TEXT NOT NULL,
                    event_id TEXT NOT NULL,
                    event_revision_id TEXT NOT NULL,
                    calendar_id TEXT NOT NULL,
                    creator_user_id TEXT NOT NULL,
                    session_id TEXT NOT NULL DEFAULT '',
                    declined_attendee_user_id TEXT,
                    status TEXT NOT NULL CHECK (status IN (
                        'pending_decliner_input',
                        'collecting_votes',
                        'awaiting_requester_decision',
                        'consented',
                        'requester_decided',
                        'cancelled',
                        'expired',
                        'failed'
                    )),
                    current_round INTEGER NOT NULL CHECK (current_round >= 0),
                    max_rounds INTEGER NOT NULL CHECK (max_rounds >= 1),
                    duration_minutes INTEGER NOT NULL,
                    timezone TEXT NOT NULL,
                    original_start_time TEXT NOT NULL,
                    original_end_time TEXT NOT NULL,
                    selected_slot_json TEXT,
                    creator_delivery_binding_json TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    last_agent_error TEXT,
                    failure_reason TEXT CHECK (failure_reason IS NULL OR failure_reason IN (
                        'failed_config',
                        'failed_delivery',
                        'failed_calendar_update',
                        'stale_meeting_revision',
                        'unsafe_runtime_error'
                    )),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    completed_at TEXT,
                    terminal_authority TEXT,
                    terminal_at TEXT,
                    terminal_reason TEXT,
                    terminal_event_revision_id TEXT,
                    kanban_task_id TEXT,
                    followup_cron_job_id TEXT,
                    followup_cron_status TEXT NOT NULL DEFAULT 'not_created',
                    followup_cron_last_tick_at TEXT,
                    followup_cron_failure_count INTEGER NOT NULL DEFAULT 0,
                    next_followup_at TEXT,
                    expires_at_utc TEXT NOT NULL,
                    finalize_status TEXT NOT NULL DEFAULT 'not_started',
                    finalize_attempt_id TEXT,
                    trigger_attendee_user_ids_json TEXT NOT NULL,
                    UNIQUE(monitor_id, event_revision_id),
                    FOREIGN KEY(monitor_id) REFERENCES meeting_rsvp_monitors(monitor_id)
                );
                CREATE INDEX IF NOT EXISTS idx_meeting_time_negotiations_workspace_status
                ON meeting_time_negotiations(workspace_id, status, updated_at);
                CREATE INDEX IF NOT EXISTS idx_meeting_time_negotiations_expiry
                ON meeting_time_negotiations(status, expires_at_utc);
                CREATE TABLE IF NOT EXISTS meeting_time_negotiation_participants (
                    negotiation_id TEXT NOT NULL,
                    attendee_user_id TEXT NOT NULL,
                    message_user_id TEXT,
                    display_name TEXT,
                    role TEXT NOT NULL CHECK (role IN ('decliner', 'attendee', 'requester')),
                    required_for_consent INTEGER NOT NULL CHECK (required_for_consent IN (0, 1)),
                    latest_response_status TEXT NOT NULL CHECK (latest_response_status IN (
                        'unknown',
                        'asked',
                        'accepted_slot',
                        'declined_slot',
                        'proposed_slot',
                        'abstained'
                    )),
                    latest_slot_id TEXT,
                    last_contacted_at TEXT,
                    last_response_at TEXT,
                    followup_count INTEGER NOT NULL DEFAULT 0,
                    last_followup_at TEXT,
                    delivery_status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(negotiation_id, attendee_user_id),
                    FOREIGN KEY(negotiation_id) REFERENCES meeting_time_negotiations(negotiation_id)
                );
                CREATE INDEX IF NOT EXISTS idx_meeting_time_participants_delivery
                ON meeting_time_negotiation_participants(negotiation_id, delivery_status, last_contacted_at);

                CREATE TABLE IF NOT EXISTS meeting_time_negotiation_case_locks (
                    negotiation_id TEXT PRIMARY KEY,
                    owner TEXT NOT NULL,
                    lease_expires_at TEXT NOT NULL,
                    acquired_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(negotiation_id) REFERENCES meeting_time_negotiations(negotiation_id)
                        ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS meeting_time_negotiation_followup_crons (
                    owner_profile TEXT NOT NULL,
                    owner_idempotency_key TEXT NOT NULL DEFAULT '',
                    workspace_id TEXT NOT NULL,
                    negotiation_id TEXT NOT NULL,
                    cron_name TEXT NOT NULL,
                    cron_job_id TEXT,
                    status TEXT NOT NULL DEFAULT 'active',
                    acquired_at TEXT NOT NULL,
                    lease_expires_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (workspace_id, negotiation_id, cron_name),
                    FOREIGN KEY(negotiation_id) REFERENCES meeting_time_negotiations(negotiation_id)
                        ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_meeting_time_negotiation_followup_crons_status
                ON meeting_time_negotiation_followup_crons(workspace_id, status, lease_expires_at);
                CREATE INDEX IF NOT EXISTS idx_meeting_time_negotiation_followup_crons_owner
                ON meeting_time_negotiation_followup_crons(owner_profile, owner_idempotency_key);

                CREATE TABLE IF NOT EXISTS meeting_time_candidate_slots (
                    slot_id TEXT PRIMARY KEY,
                    negotiation_id TEXT NOT NULL,
                    proposed_by_user_id TEXT NOT NULL,
                    round_number INTEGER NOT NULL,
                    start_time TEXT NOT NULL,
                    end_time TEXT NOT NULL,
                    timezone TEXT NOT NULL,
                    source_text TEXT,
                    status TEXT NOT NULL CHECK (status IN ('candidate', 'superseded', 'selected', 'rejected')),
                    created_at TEXT NOT NULL,
                    UNIQUE(negotiation_id, start_time, end_time, timezone),
                    FOREIGN KEY(negotiation_id) REFERENCES meeting_time_negotiations(negotiation_id)
                );
                CREATE INDEX IF NOT EXISTS idx_meeting_time_slots_case_round
                ON meeting_time_candidate_slots(negotiation_id, round_number, status);
                CREATE INDEX IF NOT EXISTS idx_meeting_time_slots_replay
                ON meeting_time_candidate_slots(negotiation_id, created_at, slot_id);

                CREATE TABLE IF NOT EXISTS meeting_time_negotiation_messages (
                    message_event_id TEXT PRIMARY KEY,
                    negotiation_id TEXT NOT NULL,
                    direction TEXT NOT NULL CHECK (direction IN ('outbound', 'inbound')),
                    participant_user_id TEXT NOT NULL,
                    message_channel TEXT NOT NULL,
                    message_id TEXT,
                    message_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    kanban_comment_id TEXT,
                    agent_trace_ref TEXT,
                    created_at TEXT NOT NULL,
                    UNIQUE(message_channel, message_id),
                    FOREIGN KEY(negotiation_id) REFERENCES meeting_time_negotiations(negotiation_id)
                );
                CREATE INDEX IF NOT EXISTS idx_meeting_time_messages_correlation
                ON meeting_time_negotiation_messages(
                    negotiation_id, participant_user_id, message_type, created_at
                );
                CREATE INDEX IF NOT EXISTS idx_meeting_time_messages_replay
                ON meeting_time_negotiation_messages(negotiation_id, created_at, message_event_id);

                CREATE TABLE IF NOT EXISTS meeting_time_negotiation_votes (
                    vote_id TEXT PRIMARY KEY,
                    negotiation_id TEXT NOT NULL,
                    slot_id TEXT NOT NULL,
                    attendee_user_id TEXT NOT NULL,
                    vote TEXT NOT NULL CHECK (vote IN ('yes', 'no', 'propose_alternative')),
                    alternative_slot_id TEXT,
                    note TEXT,
                    created_at TEXT NOT NULL,
                    UNIQUE(negotiation_id, slot_id, attendee_user_id),
                    FOREIGN KEY(negotiation_id) REFERENCES meeting_time_negotiations(negotiation_id),
                    FOREIGN KEY(slot_id) REFERENCES meeting_time_candidate_slots(slot_id)
                );
                CREATE INDEX IF NOT EXISTS idx_meeting_time_votes_replay
                ON meeting_time_negotiation_votes(negotiation_id, created_at, vote_id);

                CREATE TABLE IF NOT EXISTS meeting_time_finalize_attempts (
                    finalize_attempt_id TEXT PRIMARY KEY,
                    finalize_idempotency_key TEXT NOT NULL UNIQUE,
                    negotiation_id TEXT NOT NULL,
                    event_revision_id TEXT NOT NULL,
                    selected_slot_id TEXT NOT NULL,
                    decision_source TEXT NOT NULL CHECK (
                        decision_source IN ('consent', 'requester_final_decision')
                    ),
                    requested_by_user_id TEXT NOT NULL,
                    calendar_update_payload_json TEXT NOT NULL,
                    status TEXT NOT NULL CHECK (status IN (
                        'pending',
                        'calendar_update_started',
                        'calendar_update_succeeded',
                        'calendar_update_failed_retryable',
                        'calendar_update_failed_permanent'
                    )),
                    next_retry_at TEXT,
                    calendar_update_result_json TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    CHECK (
                        status != 'calendar_update_failed_retryable'
                        OR next_retry_at IS NOT NULL
                    ),
                    FOREIGN KEY(negotiation_id) REFERENCES meeting_time_negotiations(negotiation_id)
                );
                CREATE INDEX IF NOT EXISTS idx_meeting_time_finalize_replay
                ON meeting_time_finalize_attempts(negotiation_id, created_at, finalize_attempt_id);

                CREATE TABLE IF NOT EXISTS meeting_time_negotiation_events (
                    event_id TEXT PRIMARY KEY,
                    negotiation_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    actor_type TEXT NOT NULL,
                    actor_id TEXT NOT NULL,
                    prior_state TEXT,
                    next_state TEXT,
                    prior_state_version INTEGER,
                    next_state_version INTEGER,
                    kanban_task_id TEXT,
                    kanban_run_id INTEGER,
                    payload_hash TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(negotiation_id) REFERENCES meeting_time_negotiations(negotiation_id)
                );
                CREATE INDEX IF NOT EXISTS idx_meeting_time_events_replay
                ON meeting_time_negotiation_events(negotiation_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_meeting_time_events_type
                ON meeting_time_negotiation_events(negotiation_id, event_type);
                """
            )
            attendee_columns = {
                row["name"]
                for row in conn.execute(
                    "PRAGMA table_info(meeting_rsvp_attendees)"
                ).fetchall()
            }
            if "negotiation_status" not in attendee_columns:
                conn.execute(
                    "ALTER TABLE meeting_rsvp_attendees ADD COLUMN negotiation_status TEXT NOT NULL DEFAULT 'none'"
                )
            if "negotiation_id" not in attendee_columns:
                conn.execute(
                    "ALTER TABLE meeting_rsvp_attendees ADD COLUMN negotiation_id TEXT"
                )
            if "followup_count" not in attendee_columns:
                conn.execute(
                    "ALTER TABLE meeting_rsvp_attendees ADD COLUMN followup_count INTEGER NOT NULL DEFAULT 0"
                )
                attendee_columns.add("followup_count")
            if "last_followup_at" not in attendee_columns:
                conn.execute(
                    "ALTER TABLE meeting_rsvp_attendees ADD COLUMN last_followup_at TEXT"
                )
                attendee_columns.add("last_followup_at")
            columns = {
                row["name"]
                for row in conn.execute(
                    "PRAGMA table_info(meeting_rsvp_workspace_state)"
                ).fetchall()
            }
            if "max_followups" not in columns:
                conn.execute(
                    "ALTER TABLE meeting_rsvp_workspace_state ADD COLUMN max_followups INTEGER NOT NULL DEFAULT 3"
                )
            negotiation_columns = {
                row["name"]
                for row in conn.execute(
                    "PRAGMA table_info(meeting_time_negotiations)"
                ).fetchall()
            }
            for col_name in (
                "session_id",
                "followup_cron_job_id",
                "followup_cron_status",
                "followup_cron_last_tick_at",
                "followup_cron_failure_count",
                "next_followup_at",
                "terminal_authority",
                "terminal_at",
                "terminal_reason",
                "terminal_event_revision_id",
            ):
                if col_name in negotiation_columns:
                    continue
                if col_name == "session_id":
                    conn.execute(
                        "ALTER TABLE meeting_time_negotiations ADD COLUMN session_id TEXT NOT NULL DEFAULT ''"
                    )
                elif col_name == "followup_cron_status":
                    conn.execute(
                        "ALTER TABLE meeting_time_negotiations ADD COLUMN followup_cron_status TEXT NOT NULL DEFAULT 'not_created'"
                    )
                elif col_name == "followup_cron_failure_count":
                    conn.execute(
                        "ALTER TABLE meeting_time_negotiations ADD COLUMN followup_cron_failure_count INTEGER NOT NULL DEFAULT 0"
                    )
                else:
                    conn.execute(
                        f"ALTER TABLE meeting_time_negotiations ADD COLUMN {col_name} TEXT"
                    )
                negotiation_columns.add(col_name)
            if "kanban_task_id" not in negotiation_columns:
                conn.execute(
                    "ALTER TABLE meeting_time_negotiations ADD COLUMN kanban_task_id TEXT"
                )
                negotiation_columns.add("kanban_task_id")
            conn.execute(
                """
                UPDATE meeting_time_negotiations
                SET session_id = COALESCE(
                    NULLIF(json_extract(payload_json, '$.session_id'), ''),
                    NULLIF(json_extract(payload_json, '$.creator_delivery_binding.session_id'), ''),
                    session_id
                )
                WHERE COALESCE(session_id, '') = ''
                  AND json_valid(payload_json)
                  AND COALESCE(
                      json_extract(payload_json, '$.session_id'),
                      json_extract(payload_json, '$.creator_delivery_binding.session_id'),
                      ''
                  ) != ''
                """
            )
            participant_columns = {
                row["name"]
                for row in conn.execute(
                    "PRAGMA table_info(meeting_time_negotiation_participants)"
                ).fetchall()
            }
            if "followup_count" not in participant_columns:
                conn.execute(
                    "ALTER TABLE meeting_time_negotiation_participants ADD COLUMN followup_count INTEGER NOT NULL DEFAULT 0"
                )
            if "last_followup_at" not in participant_columns:
                conn.execute(
                    "ALTER TABLE meeting_time_negotiation_participants ADD COLUMN last_followup_at TEXT"
                )
            self._remove_negotiation_process_control_columns(
                conn, columns=negotiation_columns
            )
            conn.executescript(
                """
                DROP INDEX IF EXISTS idx_meeting_time_negotiations_scheduler_heal;
                CREATE INDEX IF NOT EXISTS idx_meeting_time_negotiations_workspace_status
                ON meeting_time_negotiations(workspace_id, status, updated_at);
                CREATE INDEX IF NOT EXISTS idx_meeting_time_negotiations_expiry
                ON meeting_time_negotiations(status, expires_at_utc);
                CREATE INDEX IF NOT EXISTS idx_meeting_time_negotiations_kanban_task
                ON meeting_time_negotiations(kanban_task_id);
                CREATE INDEX IF NOT EXISTS idx_meeting_time_negotiations_followup_status
                ON meeting_time_negotiations(followup_cron_status);
                CREATE INDEX IF NOT EXISTS idx_meeting_time_participants_followup
                ON meeting_time_negotiation_participants(
                    negotiation_id,
                    required_for_consent,
                    followup_count,
                    last_followup_at
                );
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS meeting_time_negotiation_case_locks (
                    negotiation_id TEXT PRIMARY KEY,
                    owner TEXT NOT NULL,
                    lease_expires_at TEXT NOT NULL,
                    acquired_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(negotiation_id) REFERENCES meeting_time_negotiations(negotiation_id)
                        ON DELETE CASCADE
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS meeting_time_negotiation_followup_crons (
                    owner_profile TEXT NOT NULL,
                    owner_idempotency_key TEXT NOT NULL DEFAULT '',
                    workspace_id TEXT NOT NULL,
                    negotiation_id TEXT NOT NULL,
                    cron_name TEXT NOT NULL,
                    cron_job_id TEXT,
                    status TEXT NOT NULL DEFAULT 'active',
                    acquired_at TEXT NOT NULL,
                    lease_expires_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (workspace_id, negotiation_id, cron_name),
                    FOREIGN KEY(negotiation_id) REFERENCES meeting_time_negotiations(negotiation_id)
                        ON DELETE CASCADE
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_meeting_time_negotiation_followup_crons_status
                ON meeting_time_negotiation_followup_crons(workspace_id, status, lease_expires_at)
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_meeting_time_negotiation_followup_crons_owner
                ON meeting_time_negotiation_followup_crons(owner_profile, owner_idempotency_key)
                """
            )
            message_columns = {
                row["name"]
                for row in conn.execute(
                    "PRAGMA table_info(meeting_time_negotiation_messages)"
                ).fetchall()
            }
            if "kanban_comment_id" not in message_columns:
                conn.execute(
                    "ALTER TABLE meeting_time_negotiation_messages ADD COLUMN kanban_comment_id TEXT"
                )
            event_columns = {
                row["name"]
                for row in conn.execute(
                    "PRAGMA table_info(meeting_time_negotiation_events)"
                ).fetchall()
            }
            if "kanban_task_id" not in event_columns:
                conn.execute(
                    "ALTER TABLE meeting_time_negotiation_events ADD COLUMN kanban_task_id TEXT"
                )
            if "kanban_run_id" not in event_columns:
                conn.execute(
                    "ALTER TABLE meeting_time_negotiation_events ADD COLUMN kanban_run_id INTEGER"
                )
            conn.executescript(
                """
                CREATE INDEX IF NOT EXISTS idx_meeting_time_events_kanban
                ON meeting_time_negotiation_events(kanban_task_id, kanban_run_id);
                """
            )

    def _remove_negotiation_process_control_columns(
        self,
        conn: sqlite3.Connection,
        *,
        columns: set[str],
    ) -> None:
        retired = {
            "cron_job_id",
            "state_version",
            "case_lease_owner",
            "case_lease_expires_at",
            "scheduler_retry_count",
            "next_scheduler_retry_at",
            "scheduler_status",
        }
        if not retired.intersection(columns):
            return
        conn.executescript(
            """
            CREATE TABLE meeting_time_negotiations_new (
                negotiation_id TEXT PRIMARY KEY,
                monitor_id TEXT NOT NULL,
                workspace_id TEXT NOT NULL,
                event_id TEXT NOT NULL,
                event_revision_id TEXT NOT NULL,
                calendar_id TEXT NOT NULL,
                creator_user_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                declined_attendee_user_id TEXT,
                status TEXT NOT NULL CHECK (status IN (
                    'pending_decliner_input',
                    'collecting_votes',
                    'awaiting_requester_decision',
                    'consented',
                    'requester_decided',
                    'cancelled',
                    'expired',
                    'failed'
                )),
                current_round INTEGER NOT NULL CHECK (current_round >= 0),
                max_rounds INTEGER NOT NULL CHECK (max_rounds >= 1),
                duration_minutes INTEGER NOT NULL,
                timezone TEXT NOT NULL,
                original_start_time TEXT NOT NULL,
                original_end_time TEXT NOT NULL,
                selected_slot_json TEXT,
                creator_delivery_binding_json TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                last_agent_error TEXT,
                failure_reason TEXT CHECK (failure_reason IS NULL OR failure_reason IN (
                    'failed_config',
                    'failed_delivery',
                    'failed_calendar_update',
                    'stale_meeting_revision',
                    'unsafe_runtime_error'
                )),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                completed_at TEXT,
                terminal_authority TEXT,
                terminal_at TEXT,
                terminal_reason TEXT,
                terminal_event_revision_id TEXT,
                kanban_task_id TEXT,
                expires_at_utc TEXT NOT NULL,
                finalize_status TEXT NOT NULL DEFAULT 'not_started',
                finalize_attempt_id TEXT,
                followup_cron_job_id TEXT,
                followup_cron_status TEXT NOT NULL DEFAULT 'not_created',
                followup_cron_last_tick_at TEXT,
                followup_cron_failure_count INTEGER NOT NULL DEFAULT 0,
                next_followup_at TEXT,
                trigger_attendee_user_ids_json TEXT NOT NULL,
                UNIQUE(monitor_id, event_revision_id),
                FOREIGN KEY(monitor_id) REFERENCES meeting_rsvp_monitors(monitor_id)
            );
            INSERT INTO meeting_time_negotiations_new(
                negotiation_id, monitor_id, workspace_id, event_id,
                event_revision_id, calendar_id, creator_user_id,
                session_id, declined_attendee_user_id, status, current_round, max_rounds,
                duration_minutes, timezone, original_start_time,
                original_end_time, selected_slot_json,
                creator_delivery_binding_json, payload_json,
                last_agent_error, failure_reason, created_at, updated_at,
                completed_at,
                terminal_authority, terminal_at, terminal_reason, terminal_event_revision_id,
                kanban_task_id, followup_cron_job_id, followup_cron_status,
                followup_cron_last_tick_at, followup_cron_failure_count, next_followup_at,
                expires_at_utc, finalize_status,
                finalize_attempt_id, trigger_attendee_user_ids_json
            )
            SELECT
                negotiation_id, monitor_id, workspace_id, event_id,
                event_revision_id, calendar_id, creator_user_id,
                COALESCE(session_id, ''),
                declined_attendee_user_id, status, current_round, max_rounds,
                duration_minutes, timezone, original_start_time,
                original_end_time, selected_slot_json,
                creator_delivery_binding_json, payload_json,
                last_agent_error, failure_reason, created_at, updated_at,
                completed_at,
                terminal_authority, terminal_at, terminal_reason, terminal_event_revision_id,
                kanban_task_id,
                NULL AS followup_cron_job_id,
                COALESCE(followup_cron_status, 'not_created'),
                followup_cron_last_tick_at, COALESCE(followup_cron_failure_count, 0),
                next_followup_at,
                expires_at_utc, finalize_status,
                finalize_attempt_id, trigger_attendee_user_ids_json
            FROM meeting_time_negotiations;
            DROP TABLE meeting_time_negotiations;
            ALTER TABLE meeting_time_negotiations_new RENAME TO meeting_time_negotiations;
            """
        )

    def start_monitor(self, payload: dict[str, Any]) -> dict[str, Any]:
        now = utc_now_iso()
        monitor_id = _monitor_id(
            payload["workspace_id"],
            payload["event_id"],
            payload["event_revision_id"],
        )
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT * FROM meeting_rsvp_monitors WHERE monitor_id=?",
                (monitor_id,),
            ).fetchone()
            if existing is not None:
                return dict(existing)
            conn.execute(
                """
                UPDATE meeting_rsvp_monitors
                SET status='replaced', updated_at=?
                WHERE workspace_id=? AND event_id=? AND status IN ('active', 'pending_start', 'error', 'failed')
                """,
                (now, payload["workspace_id"], payload["event_id"]),
            )
            conn.execute(
                """
                INSERT INTO meeting_rsvp_monitors(
                    monitor_id, workspace_id, creator_user_id, platform, event_id,
                    event_revision_id, calendar_id, cron_job_id,
                    creator_delivery_binding_json, status, created_at, updated_at,
                    payload_json
                )
                VALUES (?, ?, ?, 'feishu', ?, ?, ?, NULL, ?, 'pending_start', ?, ?, ?)
                """,
                (
                    monitor_id,
                    payload["workspace_id"],
                    payload["creator_user_id"],
                    payload["event_id"],
                    payload["event_revision_id"],
                    payload["calendar_id"],
                    _json(payload["creator_delivery_binding"]),
                    now,
                    now,
                    _json(payload),
                ),
            )
            for attendee in payload.get("attendees") or []:
                user_id = str(attendee.get("user_id") or "").strip()
                if not user_id:
                    continue
                conn.execute(
                    """
                    INSERT OR REPLACE INTO meeting_rsvp_attendees(
                        monitor_id, attendee_user_id, message_user_id, display_name,
                        response_status, delivery_status
                    )
                    VALUES (?, ?, ?, ?, 'unknown', 'ready')
                    """,
                    (
                        monitor_id,
                        user_id,
                        str(attendee.get("message_user_id") or ""),
                        str(attendee.get("display_name") or ""),
                    ),
                )
            row = conn.execute(
                "SELECT * FROM meeting_rsvp_monitors WHERE monitor_id=?",
                (monitor_id,),
            ).fetchone()
        return dict(row) if row is not None else self.get_monitor(monitor_id)

    def get_monitor(self, monitor_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM meeting_rsvp_monitors WHERE monitor_id=?",
                (monitor_id,),
            ).fetchone()
        if row is None:
            raise KeyError(monitor_id)
        return dict(row)

    def attach_cron_job(self, monitor_id: str, cron_job_id: str) -> dict[str, Any]:
        now = utc_now_iso()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE meeting_rsvp_monitors
                SET cron_job_id=?, status='active', last_start_error=NULL, updated_at=?
                WHERE monitor_id=?
                """,
                (cron_job_id, now, monitor_id),
            )
        return self.get_monitor(monitor_id)

    def mark_monitor_start_failed(
        self, monitor_id: str, *, detail: str
    ) -> dict[str, Any]:
        now = utc_now_iso()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE meeting_rsvp_monitors
                SET status='pending_start', last_start_error=?, updated_at=?
                WHERE monitor_id=?
                """,
                (detail, now, monitor_id),
            )
        return self.get_monitor(monitor_id)

    def mark_monitor_complete(self, monitor_id: str) -> dict[str, Any]:
        now = utc_now_iso()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE meeting_rsvp_monitors
                SET status='complete', completed_at=?, updated_at=?
                WHERE monitor_id=?
                """,
                (now, now, monitor_id),
            )
        return self.get_monitor(monitor_id)

    def mark_monitor_negotiating(
        self, monitor_id: str, *, negotiation_id: str
    ) -> dict[str, Any]:
        now = utc_now_iso()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE meeting_rsvp_monitors
                SET status='negotiating',
                    completed_at=COALESCE(completed_at, ?),
                    last_start_error=?,
                    updated_at=?
                WHERE monitor_id=?
                """,
                (now, f"negotiation_started:{negotiation_id}", now, monitor_id),
            )
        return self.get_monitor(monitor_id)

    def mark_monitor_cancelled(
        self, monitor_id: str, *, detail: str | None = None
    ) -> dict[str, Any]:
        now = utc_now_iso()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE meeting_rsvp_monitors
                SET status='cancelled',
                    completed_at=COALESCE(completed_at, ?),
                    last_start_error=?,
                    updated_at=?
                WHERE monitor_id=?
                """,
                (now, detail, now, monitor_id),
            )
        return self.get_monitor(monitor_id)

    def mark_monitor_failed(self, monitor_id: str, *, detail: str) -> dict[str, Any]:
        now = utc_now_iso()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE meeting_rsvp_monitors
                SET status='failed',
                    completed_at=COALESCE(completed_at, ?),
                    last_start_error=?,
                    updated_at=?
                WHERE monitor_id=?
                """,
                (now, detail, now, monitor_id),
            )
        return self.get_monitor(monitor_id)

    def _normalize_rsvp_status(self, value: Any) -> str:
        status = str(value or "unknown").strip().lower()
        if status in {"accept", "accepted"}:
            return "accepted"
        if status in {"decline", "declined"}:
            return "declined"
        if status in {"tentative", "maybe"}:
            return "tentative"
        if status in {"needs_action", "needsaction", "pending", "none", "null"}:
            return "needs_action"
        if status in ALL_RSVP_STATUSES:
            return status
        return "unknown"

    def update_attendee_statuses(
        self,
        monitor_id: str,
        live_attendees: list[dict[str, Any]],
    ) -> dict[str, int]:
        now = utc_now_iso()
        counts = {status: 0 for status in sorted(ALL_RSVP_STATUSES)}
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE meeting_rsvp_monitors
                SET last_checked_at=?, updated_at=?
                WHERE monitor_id=?
                """,
                (now, now, monitor_id),
            )
            for item in live_attendees:
                attendee_user_id = str(
                    item.get("user_id") or item.get("attendee_user_id") or ""
                ).strip()
                if not attendee_user_id:
                    continue
                status = self._normalize_rsvp_status(item.get("response_status"))
                counts[status] += 1
                last_response_at = now if status in TERMINAL_RSVP_STATUSES else None
                conn.execute(
                    """
                    UPDATE meeting_rsvp_attendees
                    SET response_status=?,
                        message_user_id=COALESCE(NULLIF(?, ''), message_user_id),
                        display_name=COALESCE(NULLIF(?, ''), display_name),
                        last_response_at=COALESCE(?, last_response_at)
                    WHERE monitor_id=? AND attendee_user_id=?
                    """,
                    (
                        status,
                        str(item.get("message_user_id") or ""),
                        str(item.get("display_name") or ""),
                        last_response_at,
                        monitor_id,
                        attendee_user_id,
                    ),
                )
        return counts

    def get_attendee(self, monitor_id: str, attendee_user_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM meeting_rsvp_attendees
                WHERE monitor_id=? AND attendee_user_id=?
                """,
                (monitor_id, attendee_user_id),
            ).fetchone()
        if row is None:
            raise KeyError(f"{monitor_id}:{attendee_user_id}")
        return dict(row)

    def list_attendees(self, monitor_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM meeting_rsvp_attendees
                WHERE monitor_id=?
                ORDER BY attendee_user_id
                """,
                (monitor_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def list_pending_followup_attendees(self, monitor_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM meeting_rsvp_attendees
                WHERE monitor_id=?
                  AND response_status IN ('needs_action', 'unknown')
                  AND delivery_status != 'escalated'
                ORDER BY attendee_user_id
                """,
                (monitor_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def record_followup_attempt(
        self,
        monitor_id: str,
        *,
        attendee_user_id: str,
        channel: str,
        target_id: str,
        status: str,
        message_id: str | None,
        error_detail: str | None,
    ) -> dict[str, Any]:
        del target_id
        now = utc_now_iso()
        followup_id = f"fu_{uuid.uuid4().hex}"
        attendee = self.get_attendee(monitor_id, attendee_user_id)
        round_number = int(attendee["followup_count"] or 0) + 1
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO meeting_rsvp_followups(
                    followup_id, monitor_id, attendee_user_id, round_number,
                    status, message_channel, message_id, error_detail,
                    created_at, sent_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    followup_id,
                    monitor_id,
                    attendee_user_id,
                    round_number,
                    status,
                    channel,
                    message_id,
                    error_detail,
                    now,
                    now if status == "sent" else None,
                ),
            )
            if status == "sent":
                conn.execute(
                    """
                    UPDATE meeting_rsvp_attendees
                    SET followup_count=followup_count + 1,
                        last_followup_at=?
                    WHERE monitor_id=? AND attendee_user_id=?
                    """,
                    (now, monitor_id, attendee_user_id),
                )
            row = conn.execute(
                "SELECT * FROM meeting_rsvp_followups WHERE followup_id=?",
                (followup_id,),
            ).fetchone()
        return dict(row)

    def mark_attendee_escalated(
        self,
        monitor_id: str,
        *,
        attendee_user_id: str,
        creator_user_id: str,
        reason: str,
        delivery_task_id: str,
        status: str = "pending",
    ) -> dict[str, Any]:
        if status not in {"pending", "sent", "failed"}:
            raise ValueError("invalid escalation status")
        now = utc_now_iso()
        escalation_id = f"esc_{uuid.uuid4().hex}"
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE meeting_rsvp_attendees
                SET delivery_status='escalated', escalated_at=?
                WHERE monitor_id=? AND attendee_user_id=?
                """,
                (now, monitor_id, attendee_user_id),
            )
            conn.execute(
                """
                INSERT INTO meeting_rsvp_escalations(
                    escalation_id, monitor_id, attendee_user_id, creator_user_id,
                    reason, delivery_task_id, status, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    escalation_id,
                    monitor_id,
                    attendee_user_id,
                    creator_user_id,
                    reason,
                    delivery_task_id,
                    status,
                    now,
                    now,
                ),
            )
            row = conn.execute(
                "SELECT * FROM meeting_rsvp_escalations WHERE escalation_id=?",
                (escalation_id,),
            ).fetchone()
        return dict(row)

    def mark_escalations_for_delivery_task(
        self,
        delivery_task_id: str,
        *,
        status: str,
    ) -> int:
        if status not in {"pending", "sent", "failed"}:
            raise ValueError("invalid escalation status")
        now = utc_now_iso()
        with self._connect() as conn:
            cursor = conn.execute(
                """
                UPDATE meeting_rsvp_escalations
                SET status=?, updated_at=?
                WHERE delivery_task_id=?
                """,
                (status, now, delivery_task_id),
            )
        return int(cursor.rowcount or 0)

    def create_delivery_task(
        self,
        *,
        monitor_id: str,
        task_type: str,
        target_user_id: str,
        delivery_binding: dict[str, Any],
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        monitor = self.get_monitor(monitor_id)
        now = utc_now_iso()
        task_id = f"dt_{uuid.uuid4().hex}"
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO meeting_rsvp_delivery_tasks(
                    delivery_task_id, monitor_id, workspace_id, task_type,
                    target_user_id, delivery_binding_json, payload_json,
                    status, attempt_count, next_attempt_at, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', 0, ?, ?, ?)
                """,
                (
                    task_id,
                    monitor_id,
                    monitor["workspace_id"],
                    task_type,
                    target_user_id,
                    _json(delivery_binding),
                    _json(payload),
                    now,
                    now,
                    now,
                ),
            )
            row = conn.execute(
                """
                SELECT * FROM meeting_rsvp_delivery_tasks
                WHERE delivery_task_id=?
                """,
                (task_id,),
            ).fetchone()
        return dict(row) if row is not None else self.get_delivery_task(task_id)

    def get_delivery_task(self, delivery_task_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM meeting_rsvp_delivery_tasks
                WHERE delivery_task_id=?
                """,
                (delivery_task_id,),
            ).fetchone()
        if row is None:
            raise KeyError(delivery_task_id)
        return dict(row)

    def mark_delivery_task_failed(
        self,
        delivery_task_id: str,
        *,
        retryable: bool,
        detail: str,
    ) -> dict[str, Any]:
        now = utc_now_iso()
        next_attempt_at = (
            (datetime.now(timezone.utc) + timedelta(minutes=2))
            .isoformat()
            .replace("+00:00", "Z")
            if retryable
            else None
        )
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE meeting_rsvp_delivery_tasks
                SET status=?, result_detail=?, next_attempt_at=?, updated_at=?
                WHERE delivery_task_id=?
                """,
                (
                    "failed_retryable" if retryable else "failed_permanent",
                    detail,
                    next_attempt_at,
                    now,
                    delivery_task_id,
                ),
            )
        return self.get_delivery_task(delivery_task_id)

    def mark_delivery_task_sent(
        self, delivery_task_id: str, *, detail: str
    ) -> dict[str, Any]:
        now = utc_now_iso()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE meeting_rsvp_delivery_tasks
                SET status='sent',
                    attempt_count=attempt_count + 1,
                    result_detail=?,
                    next_attempt_at=NULL,
                    updated_at=?
                WHERE delivery_task_id=?
                """,
                (detail, now, delivery_task_id),
            )
        return self.get_delivery_task(delivery_task_id)

    def mark_delivery_task_attempt_failed(
        self,
        delivery_task_id: str,
        *,
        retryable: bool,
        detail: str,
    ) -> dict[str, Any]:
        now = utc_now_iso()
        next_attempt_at = (
            (datetime.now(timezone.utc) + timedelta(minutes=2))
            .isoformat()
            .replace("+00:00", "Z")
            if retryable
            else None
        )
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE meeting_rsvp_delivery_tasks
                SET status=?,
                    attempt_count=attempt_count + 1,
                    result_detail=?,
                    next_attempt_at=?,
                    updated_at=?
                WHERE delivery_task_id=?
                """,
                (
                    "failed_retryable" if retryable else "failed_permanent",
                    detail,
                    next_attempt_at,
                    now,
                    delivery_task_id,
                ),
            )
        return self.get_delivery_task(delivery_task_id)

    def requeue_delivery_task(
        self, delivery_task_id: str, *, reason: str
    ) -> dict[str, Any]:
        task = self.get_delivery_task(delivery_task_id)
        if task["status"] not in {"failed_retryable", "failed_permanent"}:
            raise ValueError("only failed delivery tasks can be requeued")
        now = utc_now_iso()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE meeting_rsvp_delivery_tasks
                SET status='pending', next_attempt_at=?, result_detail=?, updated_at=?
                WHERE delivery_task_id=?
                """,
                (now, reason, now, delivery_task_id),
            )
        return self.get_delivery_task(delivery_task_id)

    def list_due_delivery_tasks(
        self, *, workspace_id: str, limit: int
    ) -> list[dict[str, Any]]:
        now = utc_now_iso()
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM meeting_rsvp_delivery_tasks
                WHERE workspace_id=?
                  AND status IN ('pending', 'failed_retryable')
                  AND (next_attempt_at IS NULL OR next_attempt_at <= ?)
                ORDER BY created_at
                LIMIT ?
                """,
                (workspace_id, now, int(limit)),
            ).fetchall()
        return [dict(row) for row in rows]

    def list_non_terminal_delivery_tasks(
        self,
        *,
        workspace_id: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM meeting_rsvp_delivery_tasks
                WHERE workspace_id=?
                  AND status IN ('pending', 'failed_retryable')
                ORDER BY created_at
                LIMIT ?
                """,
                (workspace_id, int(limit)),
            ).fetchall()
        return [dict(row) for row in rows]

    def mark_delivery_retry_scheduler_unavailable(
        self,
        *,
        workspace_id: str,
        detail: str,
    ) -> dict[str, Any]:
        now = utc_now_iso()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO meeting_rsvp_workspace_state(
                    workspace_id,
                    delivery_retry_scheduler_status,
                    delivery_retry_scheduler_detail,
                    updated_at
                )
                VALUES (?, 'unavailable', ?, ?)
                ON CONFLICT(workspace_id) DO UPDATE SET
                    delivery_retry_scheduler_status='unavailable',
                    delivery_retry_scheduler_detail=excluded.delivery_retry_scheduler_detail,
                    updated_at=excluded.updated_at
                """,
                (workspace_id, detail, now),
            )
        return self.get_workspace_state(workspace_id)

    def get_workspace_state(self, workspace_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM meeting_rsvp_workspace_state
                WHERE workspace_id=?
                """,
                (workspace_id,),
            ).fetchone()
        if row is None:
            return {
                "workspace_id": workspace_id,
                "delivery_retry_scheduler_status": "ok",
                "delivery_retry_scheduler_detail": None,
                "max_followups": DEFAULT_MAX_FOLLOWUPS,
                "updated_at": None,
            }
        record = dict(row)
        try:
            max_followups = int(record.get("max_followups") or DEFAULT_MAX_FOLLOWUPS)
        except (TypeError, ValueError):
            max_followups = DEFAULT_MAX_FOLLOWUPS
        record["max_followups"] = max(1, max_followups)
        return record

    def update_workspace_settings(
        self,
        workspace_id: str,
        *,
        max_followups: int,
    ) -> dict[str, Any]:
        if max_followups < 1:
            raise ValueError("max_followups must be at least 1")
        if max_followups > 20:
            raise ValueError("max_followups must be at most 20")
        now = utc_now_iso()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO meeting_rsvp_workspace_state(
                    workspace_id,
                    delivery_retry_scheduler_status,
                    delivery_retry_scheduler_detail,
                    max_followups,
                    updated_at
                )
                VALUES (?, 'ok', NULL, ?, ?)
                ON CONFLICT(workspace_id) DO UPDATE SET
                    max_followups=excluded.max_followups,
                    updated_at=excluded.updated_at
                """,
                (workspace_id, max_followups, now),
            )
        return self.get_workspace_state(workspace_id)

    def _record_negotiation_event(
        self,
        conn: sqlite3.Connection,
        *,
        negotiation_id: str,
        event_type: str,
        actor_type: str,
        actor_id: str,
        payload: dict[str, Any],
        prior_state: str | None = None,
        next_state: str | None = None,
        prior_state_version: int | None = None,
        next_state_version: int | None = None,
        kanban_task_id: str | None = None,
        kanban_run_id: int | None = None,
    ) -> dict[str, Any]:
        now = utc_now_iso()
        payload_json = _json(payload)
        payload_hash = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
        event_id = _hash_id(
            "nevt",
            [
                "meeting_time_negotiation_event:v1",
                negotiation_id,
                event_type,
                actor_type,
                actor_id,
                payload_hash,
                now,
            ],
            length=32,
        )
        conn.execute(
            """
            INSERT INTO meeting_time_negotiation_events(
                event_id, negotiation_id, event_type, actor_type, actor_id,
                prior_state, next_state, prior_state_version, next_state_version,
                kanban_task_id, kanban_run_id, payload_hash, payload_json, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                negotiation_id,
                event_type,
                actor_type,
                actor_id,
                prior_state,
                next_state,
                prior_state_version,
                next_state_version,
                kanban_task_id,
                kanban_run_id,
                payload_hash,
                payload_json,
                now,
            ),
        )
        row = conn.execute(
            "SELECT * FROM meeting_time_negotiation_events WHERE event_id=?",
            (event_id,),
        ).fetchone()
        return dict(row)

    def record_negotiation_event(
        self,
        *,
        negotiation_id: str,
        event_type: str,
        actor_type: str,
        actor_id: str,
        payload: dict[str, Any],
        prior_state: str | None = None,
        next_state: str | None = None,
        prior_state_version: int | None = None,
        next_state_version: int | None = None,
        kanban_task_id: str | None = None,
        kanban_run_id: int | None = None,
    ) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM meeting_time_negotiations WHERE negotiation_id=?",
                (negotiation_id,),
            ).fetchone()
            if row is None:
                raise KeyError(negotiation_id)
            return self._record_negotiation_event(
                conn,
                negotiation_id=negotiation_id,
                event_type=event_type,
                actor_type=actor_type,
                actor_id=actor_id,
                payload=payload,
                prior_state=prior_state,
                next_state=next_state,
                prior_state_version=prior_state_version,
                next_state_version=next_state_version,
                kanban_task_id=kanban_task_id,
                kanban_run_id=kanban_run_id,
            )

    def _negotiation_expiry(self, *, created_at: str, original_start_time: str) -> str:
        created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        try:
            original_start = datetime.fromisoformat(
                original_start_time.replace("Z", "+00:00")
            )
        except ValueError:
            original_start = created + timedelta(hours=48)
        candidate = min(
            original_start - timedelta(hours=1), created + timedelta(hours=48)
        )
        expires_at = max(candidate, created + timedelta(minutes=15))
        return expires_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

    def _duration_minutes(self, payload: dict[str, Any]) -> int:
        try:
            start = datetime.fromisoformat(
                str(payload.get("start_time") or "").replace("Z", "+00:00")
            )
            end = datetime.fromisoformat(
                str(payload.get("end_time") or "").replace("Z", "+00:00")
            )
            return max(1, int((end - start).total_seconds() // 60))
        except ValueError:
            return int(payload.get("duration_minutes") or 30)

    def get_negotiation(self, negotiation_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM meeting_time_negotiations WHERE negotiation_id=?",
                (negotiation_id,),
            ).fetchone()
        if row is None:
            raise KeyError(negotiation_id)
        return dict(row)

    def set_negotiation_kanban_task(
        self,
        negotiation_id: str,
        *,
        kanban_task_id: str,
        actor_id: str = "meeting-rsvp-monitor",
    ) -> dict[str, Any]:
        now = utc_now_iso()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE meeting_time_negotiations
                SET kanban_task_id=COALESCE(kanban_task_id, ?), updated_at=?
                WHERE negotiation_id=?
                """,
                (kanban_task_id, now, negotiation_id),
            )
            row = conn.execute(
                "SELECT * FROM meeting_time_negotiations WHERE negotiation_id=?",
                (negotiation_id,),
            ).fetchone()
            if row is None:
                raise KeyError(negotiation_id)
            if row["kanban_task_id"] != kanban_task_id:
                raise ValueError(
                    "negotiation already linked to a different Kanban task"
                )
            self._record_negotiation_event(
                conn,
                negotiation_id=negotiation_id,
                event_type="KANBAN_TASK_LINKED",
                actor_type="system",
                actor_id=actor_id,
                kanban_task_id=kanban_task_id,
                payload={"kanban_task_id": kanban_task_id},
        )
        return dict(row)

    def record_negotiation_followup_attempt(
        self,
        negotiation_id: str,
        *,
        attendee_user_id: str,
        status: str,
        error_detail: str | None = None,
    ) -> dict[str, Any]:
        if status not in {"sent", "failed"}:
            raise ValueError("invalid followup status")
        now = utc_now_iso()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM meeting_time_negotiation_participants WHERE negotiation_id=? AND attendee_user_id=?",
                (negotiation_id, attendee_user_id),
            ).fetchone()
            if row is None:
                raise KeyError(f"{negotiation_id}:{attendee_user_id}")
            if status == "sent":
                conn.execute(
                    """
                    UPDATE meeting_time_negotiation_participants
                    SET followup_count=followup_count + 1,
                        last_followup_at=?,
                        updated_at=?
                    WHERE negotiation_id=? AND attendee_user_id=?
                    """,
                    (now, now, negotiation_id, attendee_user_id),
                )
            else:
                conn.execute(
                    """
                    UPDATE meeting_time_negotiation_participants
                    SET updated_at=?
                    WHERE negotiation_id=? AND attendee_user_id=?
                    """,
                    (now, negotiation_id, attendee_user_id),
                )
            row = conn.execute(
                "SELECT * FROM meeting_time_negotiation_participants WHERE negotiation_id=? AND attendee_user_id=?",
                (negotiation_id, attendee_user_id),
            ).fetchone()
        return dict(row)

    def set_negotiation_followup_cron_metadata(
        self,
        negotiation_id: str,
        *,
        followup_cron_job_id: str | None = _UNSET,
        followup_cron_status: str | None = _UNSET,
        followup_cron_last_tick_at: Any = _UNSET,
        followup_cron_failure_count: int | None = _UNSET,
        next_followup_at: str | None = _UNSET,
        expected_followup_cron_job_id: str | None = _UNSET,
        terminal_authority: str | None = _UNSET,
        terminal_at: str | None = _UNSET,
        terminal_reason: str | None = _UNSET,
        terminal_event_revision_id: str | None = _UNSET,
    ) -> dict[str, Any]:
        if (
            followup_cron_status is not _UNSET
            and followup_cron_status not in FOLLOWUP_CRON_STATUSES
        ):
            raise ValueError("invalid followup_cron_status")
        if (
            followup_cron_failure_count is not _UNSET
            and not isinstance(followup_cron_failure_count, int)
        ):
            raise ValueError("followup_cron_failure_count must be an integer")
        if (
            followup_cron_last_tick_at is not _UNSET
            and followup_cron_last_tick_at is not None
            and not isinstance(followup_cron_last_tick_at, str)
        ):
            raise ValueError("followup_cron_last_tick_at must be a string ISO8601 timestamp")
        if (
            next_followup_at is not _UNSET
            and next_followup_at is not None
            and not isinstance(next_followup_at, str)
        ):
            raise ValueError("next_followup_at must be a string ISO8601 timestamp")
        if (
            terminal_at is not _UNSET
            and terminal_at is not None
            and not isinstance(terminal_at, str)
        ):
            raise ValueError("terminal_at must be a string ISO8601 timestamp")
        if (
            terminal_authority is not _UNSET
            and terminal_authority is not None
            and not isinstance(terminal_authority, str)
        ):
            raise ValueError("terminal_authority must be a string")
        if (
            terminal_reason is not _UNSET
            and terminal_reason is not None
            and not isinstance(terminal_reason, str)
        ):
            raise ValueError("terminal_reason must be a string")
        if (
            terminal_event_revision_id is not _UNSET
            and terminal_event_revision_id is not None
            and not isinstance(terminal_event_revision_id, str)
        ):
            raise ValueError("terminal_event_revision_id must be a string")
        if (
            expected_followup_cron_job_id is not _UNSET
            and expected_followup_cron_job_id is not None
            and not isinstance(expected_followup_cron_job_id, str)
        ):
            raise ValueError("expected_followup_cron_job_id must be a string")

        assignments: list[str] = []
        values: list[Any] = []
        if followup_cron_job_id is not _UNSET:
            assignments.append("followup_cron_job_id=?")
            values.append(followup_cron_job_id)
        if followup_cron_status is not _UNSET:
            assignments.append("followup_cron_status=?")
            values.append(followup_cron_status)
        if followup_cron_last_tick_at is not _UNSET:
            assignments.append("followup_cron_last_tick_at=?")
            values.append(
                followup_cron_last_tick_at
                if followup_cron_last_tick_at is not None
                else None
            )
        if followup_cron_failure_count is not _UNSET:
            assignments.append("followup_cron_failure_count=?")
            values.append(followup_cron_failure_count)
        if next_followup_at is not _UNSET:
            assignments.append("next_followup_at=?")
            values.append(
                next_followup_at
                if next_followup_at is not None
                else None
            )
        if terminal_authority is not _UNSET:
            assignments.append("terminal_authority=?")
            values.append(terminal_authority)
        if terminal_at is not _UNSET:
            assignments.append("terminal_at=?")
            values.append(terminal_at)
        if terminal_reason is not _UNSET:
            assignments.append("terminal_reason=?")
            values.append(terminal_reason)
        if terminal_event_revision_id is not _UNSET:
            assignments.append("terminal_event_revision_id=?")
            values.append(terminal_event_revision_id)
        if not assignments:
            raise ValueError("no followup cron fields provided")
        assignments.append("updated_at=?")
        values.append(utc_now_iso())
        values.append(negotiation_id)

        where_clause = "negotiation_id=?"
        if expected_followup_cron_job_id is not _UNSET:
            expected_followup_cron_job_id = str(expected_followup_cron_job_id or "").strip()
            if expected_followup_cron_job_id:
                where_clause = (
                    "negotiation_id=? AND followup_cron_job_id=?"
                )
                values.append(expected_followup_cron_job_id)
            else:
                where_clause = (
                    "negotiation_id=? AND (followup_cron_job_id IS NULL OR followup_cron_job_id='')"
                )

        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM meeting_time_negotiations WHERE negotiation_id=?",
                (negotiation_id,),
            ).fetchone()
            if row is None:
                raise KeyError(negotiation_id)
            set_clause = ", ".join(assignments)
            cursor = conn.execute(
                f"""
                UPDATE meeting_time_negotiations
                SET {set_clause}
                WHERE {where_clause}
                """,
                values,
            )
            if expected_followup_cron_job_id is not _UNSET and int(cursor.rowcount or 0) != 1:
                raise RuntimeError("followup cron ownership mismatch")
            row = conn.execute(
                "SELECT * FROM meeting_time_negotiations WHERE negotiation_id=?",
                (negotiation_id,),
            ).fetchone()
            self._record_negotiation_event(
                conn,
                negotiation_id=negotiation_id,
                event_type="FOLLOWUP_CRON_METADATA_SET",
                actor_type="system",
                actor_id="meeting-rsvp-monitor",
                payload={"negotiation_id": negotiation_id},
            )
        return dict(row)

    def bump_followup_cron_failure(
        self,
        negotiation_id: str,
        *,
        terminal: bool = False,
    ) -> dict[str, Any]:
        now = utc_now_iso()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM meeting_time_negotiations WHERE negotiation_id=?",
                (negotiation_id,),
            ).fetchone()
            if row is None:
                raise KeyError(negotiation_id)
            failure_count = int(row["followup_cron_failure_count"] or 0) + 1
            status = "failed" if failure_count > 0 else "active"
            if terminal:
                status = "disabled"
            conn.execute(
                """
                UPDATE meeting_time_negotiations
                SET followup_cron_failure_count=?, followup_cron_status=?, updated_at=?
                WHERE negotiation_id=?
                """,
                (failure_count, status, now, negotiation_id),
            )
            row = conn.execute(
                "SELECT * FROM meeting_time_negotiations WHERE negotiation_id=?",
                (negotiation_id,),
            ).fetchone()
        return dict(row)

    def ensure_followup_cron_ownership(
        self,
        negotiation_id: str,
        cron_name: str,
        *,
        owner_profile: str,
        owner_idempotency_key: str | None = None,
        workspace_id: str | None = None,
        cron_job_id: str | None = None,
        ttl_seconds: int = NEGOTIATION_CASE_LOCK_TTL_SECONDS * 2,
    ) -> bool:
        negotiation_id = str(negotiation_id or "").strip()
        cron_name = str(cron_name or "").strip()
        owner_profile = str(owner_profile or "").strip()
        owner_idempotency_key = str(owner_idempotency_key or "").strip()
        if not negotiation_id or not cron_name:
            raise ValueError("negotiation_id and cron_name are required")
        if not owner_profile:
            raise ValueError("owner_profile is required")
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        negotiation = self.get_negotiation(negotiation_id)
        if workspace_id is None:
            workspace_id = str(negotiation["workspace_id"])
        workspace_id = str(workspace_id or "").strip()
        if not workspace_id:
            raise ValueError("workspace_id is required")

        now = datetime.now(timezone.utc)
        now_iso = now.isoformat().replace("+00:00", "Z")
        lease_expires_at = (now + timedelta(seconds=ttl_seconds)).isoformat().replace(
            "+00:00", "Z"
        )

        for _ in range(2):
            with self._connect() as conn:
                row = conn.execute(
                    """
                    SELECT * FROM meeting_time_negotiation_followup_crons
                    WHERE workspace_id=? AND negotiation_id=? AND cron_name=?
                    """,
                    (workspace_id, negotiation_id, cron_name),
                ).fetchone()
                if row is None:
                    try:
                        conn.execute(
                            """
                            INSERT INTO meeting_time_negotiation_followup_crons(
                                owner_profile,
                                owner_idempotency_key,
                                workspace_id,
                                negotiation_id,
                                cron_name,
                                cron_job_id,
                                status,
                                acquired_at,
                                lease_expires_at,
                                updated_at
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                owner_profile,
                                owner_idempotency_key,
                                workspace_id,
                                negotiation_id,
                                cron_name,
                                cron_job_id,
                                "active",
                                now_iso,
                                lease_expires_at,
                                now_iso,
                            ),
                        )
                        return True
                    except sqlite3.IntegrityError:
                        continue

                existing_owner = str(row["owner_profile"] or "")
                existing_key = str(row["owner_idempotency_key"] or "")
                existing_lease = _parse_utc_iso(str(row["lease_expires_at"] or ""))
                active = existing_lease is not None and existing_lease > now
                if active and (
                    existing_owner != owner_profile
                    or existing_key != owner_idempotency_key
                ):
                    raise RuntimeError("followup cron ownership conflict")

                conn.execute(
                    """
                    UPDATE meeting_time_negotiation_followup_crons
                    SET owner_profile=?,
                        owner_idempotency_key=?,
                        status='active',
                        cron_job_id=COALESCE(?, cron_job_id),
                        acquired_at=?,
                        lease_expires_at=?,
                        updated_at=?
                    WHERE workspace_id=? AND negotiation_id=? AND cron_name=?
                    """,
                    (
                        owner_profile,
                        owner_idempotency_key,
                        cron_job_id,
                        now_iso,
                        lease_expires_at,
                        now_iso,
                        workspace_id,
                        negotiation_id,
                        cron_name,
                    ),
                )
                return True
        return False

    def release_followup_cron_ownership(
        self,
        negotiation_id: str,
        cron_name: str,
        *,
        owner_profile: str | None = None,
        owner_idempotency_key: str | None = None,
        workspace_id: str | None = None,
    ) -> bool:
        negotiation_id = str(negotiation_id or "").strip()
        cron_name = str(cron_name or "").strip()
        if not negotiation_id or not cron_name:
            raise ValueError("negotiation_id and cron_name are required")
        if workspace_id is None:
            negotiation = self.get_negotiation(negotiation_id)
            workspace_id = str(negotiation["workspace_id"])
        workspace_id = str(workspace_id or "").strip()
        if not workspace_id:
            raise ValueError("workspace_id is required")

        query = """
            DELETE FROM meeting_time_negotiation_followup_crons
            WHERE workspace_id=? AND negotiation_id=? AND cron_name=?
        """
        params: list[str] = [workspace_id, negotiation_id, cron_name]
        if owner_profile is not None:
            query += " AND owner_profile=?"
            params.append(owner_profile.strip())
        if owner_idempotency_key is not None:
            query += " AND owner_idempotency_key=?"
            params.append(owner_idempotency_key.strip())

        with self._connect() as conn:
            cursor = conn.execute(query, tuple(params))
            return bool(cursor.rowcount and cursor.rowcount > 0)

    def acquire_negotiation_case_lock(
        self,
        negotiation_id: str,
        *,
        owner: str,
        lease_ttl_seconds: int = NEGOTIATION_CASE_LOCK_TTL_SECONDS,
    ) -> bool:
        if not owner.strip():
            raise ValueError("owner is required")
        if lease_ttl_seconds <= 0:
            raise ValueError("lease_ttl_seconds must be positive")
        owner = owner.strip()
        now = datetime.now(timezone.utc)
        now_iso = now.isoformat().replace("+00:00", "Z")
        expires_at = (now + timedelta(seconds=lease_ttl_seconds)).isoformat().replace(
            "+00:00", "Z"
        )
        with self._connect() as conn:
            # Ensure negotiation exists before writing a lock row.
            existing = conn.execute(
                "SELECT 1 FROM meeting_time_negotiations WHERE negotiation_id=?",
                (negotiation_id,),
            ).fetchone()
            if existing is None:
                raise KeyError(negotiation_id)
            row = conn.execute(
                "SELECT * FROM meeting_time_negotiation_case_locks WHERE negotiation_id=?",
                (negotiation_id,),
            ).fetchone()
            if row is None:
                conn.execute(
                    """
                    INSERT INTO meeting_time_negotiation_case_locks(
                        negotiation_id, owner, lease_expires_at, acquired_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (negotiation_id, owner, expires_at, now_iso, now_iso),
                )
                return True
            prior_owner = str(row["owner"] or "")
            prior_expiry = _parse_utc_iso(str(row["lease_expires_at"] or ""))
            if prior_expiry is None or prior_expiry <= now or prior_owner == owner:
                conn.execute(
                    """
                    UPDATE meeting_time_negotiation_case_locks
                    SET owner=?,
                        lease_expires_at=?,
                        acquired_at=?,
                        updated_at=?
                    WHERE negotiation_id=?
                    """,
                    (owner, expires_at, now_iso, now_iso, negotiation_id),
                )
                return True
            return False

    def release_negotiation_case_lock(self, negotiation_id: str, *, owner: str) -> bool:
        if not owner.strip():
            return False
        owner = owner.strip()
        with self._connect() as conn:
            row = conn.execute(
                "DELETE FROM meeting_time_negotiation_case_locks "
                "WHERE negotiation_id=? AND owner=?",
                (negotiation_id, owner),
            )
        return bool(row.rowcount and row.rowcount > 0)

    def list_negotiations_for_monitor(self, monitor_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM meeting_time_negotiations
                WHERE monitor_id=?
                ORDER BY created_at, negotiation_id
                """,
                (monitor_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def mark_negotiation_kanban_task_cleaned(
        self,
        negotiation_id: str,
        *,
        kanban_task_id: str,
        reason: str,
        actor_id: str = "meeting-rsvp-monitor",
    ) -> dict[str, Any]:
        now = utc_now_iso()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM meeting_time_negotiations WHERE negotiation_id=?",
                (negotiation_id,),
            ).fetchone()
            if row is None:
                raise KeyError(negotiation_id)
            conn.execute(
                """
                UPDATE meeting_time_negotiations
                SET kanban_task_id=NULL, updated_at=?
                WHERE negotiation_id=? AND kanban_task_id=?
                """,
                (now, negotiation_id, kanban_task_id),
            )
            self._record_negotiation_event(
                conn,
                negotiation_id=negotiation_id,
                event_type="KANBAN_TASK_CLEANED",
                actor_type="system",
                actor_id=actor_id,
                kanban_task_id=kanban_task_id,
                payload={"kanban_task_id": kanban_task_id, "reason": reason},
            )
            refreshed = conn.execute(
                "SELECT * FROM meeting_time_negotiations WHERE negotiation_id=?",
                (negotiation_id,),
            ).fetchone()
        return dict(refreshed)

    def set_message_kanban_comment(
        self,
        message_event_id: str,
        *,
        kanban_comment_id: str,
    ) -> dict[str, Any]:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE meeting_time_negotiation_messages
                SET kanban_comment_id=COALESCE(kanban_comment_id, ?)
                WHERE message_event_id=?
                """,
                (kanban_comment_id, message_event_id),
            )
            row = conn.execute(
                "SELECT * FROM meeting_time_negotiation_messages WHERE message_event_id=?",
                (message_event_id,),
            ).fetchone()
            if row is None:
                raise KeyError(message_event_id)
            if row["kanban_comment_id"] != kanban_comment_id:
                raise ValueError("message already linked to a different Kanban comment")
            negotiation = conn.execute(
                "SELECT kanban_task_id FROM meeting_time_negotiations WHERE negotiation_id=?",
                (row["negotiation_id"],),
            ).fetchone()
            self._record_negotiation_event(
                conn,
                negotiation_id=row["negotiation_id"],
                event_type="KANBAN_COMMENT_LINKED",
                actor_type="system",
                actor_id="meeting-time-negotiator",
                kanban_task_id=negotiation["kanban_task_id"] if negotiation else None,
                payload={
                    "message_event_id": message_event_id,
                    "kanban_comment_id": kanban_comment_id,
                },
            )
        return dict(row)

    def list_negotiation_participants(
        self, negotiation_id: str
    ) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM meeting_time_negotiation_participants
                WHERE negotiation_id=?
                ORDER BY role DESC, attendee_user_id
                """,
                (negotiation_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def list_negotiation_events(self, negotiation_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM meeting_time_negotiation_events
                WHERE negotiation_id=?
                ORDER BY created_at, event_id
                """,
                (negotiation_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def list_negotiation_messages(self, negotiation_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM meeting_time_negotiation_messages
                WHERE negotiation_id=?
                ORDER BY created_at, message_event_id
                """,
                (negotiation_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def list_negotiation_votes(self, negotiation_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM meeting_time_negotiation_votes
                WHERE negotiation_id=?
                ORDER BY created_at, vote_id
                """,
                (negotiation_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def list_finalize_attempts(self, negotiation_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM meeting_time_finalize_attempts
                WHERE negotiation_id=?
                ORDER BY created_at, finalize_attempt_id
                """,
                (negotiation_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def set_negotiation_participant_rsvp_status(
        self,
        *,
        negotiation_id: str,
        attendee_user_id: str,
        response_status: str,
        responded: bool = True,
    ) -> dict[str, Any]:
        normalized = str(response_status or "").strip().lower()
        if normalized not in {
            "unknown",
            "asked",
            "accepted_slot",
            "declined_slot",
            "proposed_slot",
            "abstained",
        }:
            raise ValueError("invalid negotiation response status")
        now = utc_now_iso()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE meeting_time_negotiation_participants
                SET latest_response_status=?,
                    last_response_at=COALESCE(?, last_response_at),
                    responded_at=COALESCE(?, last_response_at),
                    updated_at=?
                WHERE negotiation_id=? AND attendee_user_id=?
                """,
                (normalized, now if responded else None, now if responded else None, now, negotiation_id, attendee_user_id),
            )
            row = conn.execute(
                """
                SELECT * FROM meeting_time_negotiation_participants
                WHERE negotiation_id=? AND attendee_user_id=?
                """,
                (negotiation_id, attendee_user_id),
            ).fetchone()
        if row is None:
            raise KeyError(f"{negotiation_id}:{attendee_user_id}")
        return dict(row)

    def list_new_declined_attendees_requiring_negotiation(
        self,
        monitor_id: str,
    ) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM meeting_rsvp_attendees
                WHERE monitor_id=?
                  AND response_status='declined'
                  AND negotiation_status='none'
                ORDER BY attendee_user_id
                """,
                (monitor_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def create_or_get_negotiation_case(
        self,
        *,
        monitor_id: str,
        event_revision_id: str,
        trigger_attendee_user_id: str,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        now = utc_now_iso()
        with self._connect() as conn:
            monitor_row = conn.execute(
                "SELECT * FROM meeting_rsvp_monitors WHERE monitor_id=?",
                (monitor_id,),
            ).fetchone()
            if monitor_row is None:
                raise KeyError(monitor_id)
            monitor = dict(monitor_row)
            payload = json.loads(str(monitor.get("payload_json") or "{}"))
            resolved_session_id = str(
                session_id or payload.get("session_id") or ""
            ).strip()
            negotiation_id = _negotiation_id(
                monitor["workspace_id"],
                monitor["event_id"],
                event_revision_id,
            )
            existing_row = conn.execute(
                """
                SELECT * FROM meeting_time_negotiations
                WHERE monitor_id=? AND event_revision_id=?
                """,
                (monitor_id, event_revision_id),
            ).fetchone()
            if existing_row is None:
                start_time = str(
                    payload.get("start_time")
                    or payload.get("meeting_start_time")
                    or now
                )
                end_time = str(
                    payload.get("end_time")
                    or payload.get("meeting_end_time")
                    or start_time
                )
                trigger_ids = [trigger_attendee_user_id]
                conn.execute(
                    """
                    INSERT INTO meeting_time_negotiations(
                        negotiation_id, monitor_id, workspace_id, event_id,
                        event_revision_id, calendar_id, creator_user_id,
                        session_id,
                        declined_attendee_user_id, status, current_round, max_rounds,
                        duration_minutes, timezone, original_start_time,
                        original_end_time, selected_slot_json,
                        creator_delivery_binding_json, payload_json,
                        last_agent_error, failure_reason, created_at, updated_at,
                        completed_at, kanban_task_id, expires_at_utc, finalize_status,
                        finalize_attempt_id, trigger_attendee_user_ids_json
                    )
                    VALUES (
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending_decliner_input',
                        0, 5, ?, ?, ?, ?, NULL, ?, ?, NULL, NULL,
                        ?, ?, NULL, NULL, ?, 'not_started', NULL, ?
                    )
                    """,
                    (
                        negotiation_id,
                        monitor_id,
                        monitor["workspace_id"],
                        monitor["event_id"],
                        event_revision_id,
                        monitor["calendar_id"],
                        monitor["creator_user_id"],
                        resolved_session_id,
                        trigger_attendee_user_id,
                        self._duration_minutes(payload),
                        str(payload.get("timezone") or "UTC"),
                        start_time,
                        end_time,
                        monitor["creator_delivery_binding_json"],
                        _json(payload),
                        now,
                        now,
                        self._negotiation_expiry(
                            created_at=now, original_start_time=start_time
                        ),
                        _json(trigger_ids),
                    ),
                )
                self._record_negotiation_event(
                    conn,
                    negotiation_id=negotiation_id,
                    event_type="CASE_CREATED",
                    actor_type="cron",
                    actor_id="meeting-rsvp-monitor",
                    next_state="pending_decliner_input",
                    payload={
                        "monitor_id": monitor_id,
                        "event_revision_id": event_revision_id,
                        "trigger_attendee_user_id": trigger_attendee_user_id,
                    },
                )
            else:
                negotiation_id = existing_row["negotiation_id"]
                if resolved_session_id and not existing_row["session_id"]:
                    conn.execute(
                        """
                        UPDATE meeting_time_negotiations
                        SET session_id=?
                        WHERE negotiation_id=?
                        """,
                        (resolved_session_id, negotiation_id),
                    )

            row = conn.execute(
                "SELECT * FROM meeting_time_negotiations WHERE negotiation_id=?",
                (negotiation_id,),
            ).fetchone()
            negotiation = dict(row)
            attendee_row = conn.execute(
                """
                SELECT * FROM meeting_rsvp_attendees
                WHERE monitor_id=? AND attendee_user_id=?
                """,
                (monitor_id, trigger_attendee_user_id),
            ).fetchone()
            if attendee_row is None:
                raise KeyError(f"{monitor_id}:{trigger_attendee_user_id}")
            attendee = dict(attendee_row)

            if negotiation["status"] in TERMINAL_NEGOTIATION_STATUSES:
                self._record_negotiation_event(
                    conn,
                    negotiation_id=negotiation_id,
                    event_type="LATE_DECLINE_AFTER_TERMINAL_CASE",
                    actor_type="cron",
                    actor_id="meeting-rsvp-monitor",
                    prior_state=negotiation["status"],
                    payload={
                        "trigger_attendee_user_id": trigger_attendee_user_id,
                        "monitor_id": monitor_id,
                    },
                )
                return negotiation

            trigger_ids = json.loads(
                str(negotiation["trigger_attendee_user_ids_json"] or "[]")
            )
            if trigger_attendee_user_id not in trigger_ids:
                trigger_ids.append(trigger_attendee_user_id)
                trigger_ids = sorted(trigger_ids)
                conn.execute(
                    """
                    UPDATE meeting_time_negotiations
                    SET trigger_attendee_user_ids_json=?, updated_at=?
                    WHERE negotiation_id=?
                    """,
                    (_json(trigger_ids), now, negotiation_id),
                )
                self._record_negotiation_event(
                    conn,
                    negotiation_id=negotiation_id,
                    event_type="DECLINE_ADDED_TO_EXISTING_CASE",
                    actor_type="cron",
                    actor_id="meeting-rsvp-monitor",
                    prior_state=negotiation["status"],
                    next_state=negotiation["status"],
                    payload={"trigger_attendee_user_id": trigger_attendee_user_id},
                )

            conn.execute(
                """
                INSERT INTO meeting_time_negotiation_participants(
                    negotiation_id, attendee_user_id, message_user_id, display_name,
                    role, required_for_consent, latest_response_status,
                    latest_slot_id, last_contacted_at, last_response_at,
                    delivery_status, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, 'decliner', 1, 'unknown', NULL, NULL, NULL, 'ready', ?, ?)
                ON CONFLICT(negotiation_id, attendee_user_id) DO UPDATE SET
                    role='decliner',
                    required_for_consent=1,
                    message_user_id=excluded.message_user_id,
                    display_name=excluded.display_name,
                    updated_at=excluded.updated_at
                """,
                (
                    negotiation_id,
                    trigger_attendee_user_id,
                    attendee.get("message_user_id"),
                    attendee.get("display_name"),
                    now,
                    now,
                ),
            )
            conn.execute(
                """
                INSERT INTO meeting_time_negotiation_participants(
                    negotiation_id, attendee_user_id, message_user_id, display_name,
                    role, required_for_consent, latest_response_status,
                    latest_slot_id, last_contacted_at, last_response_at,
                    delivery_status, created_at, updated_at
                )
                VALUES (?, ?, NULL, NULL, 'requester', 0, 'unknown', NULL, NULL, NULL, 'ready', ?, ?)
                ON CONFLICT(negotiation_id, attendee_user_id) DO UPDATE SET updated_at=excluded.updated_at
                """,
                (negotiation_id, monitor["creator_user_id"], now, now),
            )
            attendee_rows = conn.execute(
                """
                SELECT * FROM meeting_rsvp_attendees
                WHERE monitor_id=?
                ORDER BY attendee_user_id
                """,
                (monitor_id,),
            ).fetchall()
            for participant_row in attendee_rows:
                participant = dict(participant_row)
                participant_user_id = str(participant["attendee_user_id"])
                if participant_user_id == trigger_attendee_user_id:
                    continue
                conn.execute(
                    """
                    INSERT INTO meeting_time_negotiation_participants(
                        negotiation_id, attendee_user_id, message_user_id, display_name,
                        role, required_for_consent, latest_response_status,
                        latest_slot_id, last_contacted_at, last_response_at,
                        delivery_status, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, 'attendee', 1, 'unknown', NULL, NULL, NULL, 'ready', ?, ?)
                    ON CONFLICT(negotiation_id, attendee_user_id) DO UPDATE SET
                        message_user_id=excluded.message_user_id,
                        display_name=excluded.display_name,
                        updated_at=excluded.updated_at
                    """,
                    (
                        negotiation_id,
                        participant_user_id,
                        participant.get("message_user_id"),
                        participant.get("display_name"),
                        now,
                        now,
                    ),
                )
            conn.execute(
                """
                UPDATE meeting_rsvp_attendees
                SET negotiation_status='created', negotiation_id=?
                WHERE monitor_id=? AND attendee_user_id=?
                """,
                (negotiation_id, monitor_id, trigger_attendee_user_id),
            )
            row = conn.execute(
                "SELECT * FROM meeting_time_negotiations WHERE negotiation_id=?",
                (negotiation_id,),
            ).fetchone()
        return dict(row)

    def transition_negotiation_state(
        self,
        negotiation_id: str,
        *,
        expected_state: str,
        next_state: str,
        patch: dict[str, Any],
        actor_id: str | None = None,
    ) -> dict[str, Any]:
        guarded = GUARDED_NEGOTIATION_PATCH_FIELDS.intersection(patch)
        if guarded:
            raise ValueError(
                f"guarded negotiation patch fields: {', '.join(sorted(guarded))}"
            )
        allowed = {
            "current_round",
            "selected_slot_json",
            "last_agent_error",
            "failure_reason",
            "completed_at",
            "finalize_status",
            "terminal_authority",
            "terminal_at",
            "terminal_reason",
            "terminal_event_revision_id",
        }
        unknown = set(patch) - allowed
        if unknown:
            raise ValueError(
                f"unsupported negotiation patch fields: {', '.join(sorted(unknown))}"
            )
        now = utc_now_iso()
        assignments = ["status=?", "updated_at=?"]
        values: list[Any] = [next_state, now]
        with self._connect() as conn:
            current_record = conn.execute(
                "SELECT * FROM meeting_time_negotiations WHERE negotiation_id=?",
                (negotiation_id,),
            ).fetchone()
            if current_record is None:
                raise KeyError(negotiation_id)
            if next_state in TERMINAL_NEGOTIATION_STATUSES:
                if "terminal_authority" not in patch:
                    assignments.append("terminal_authority=?")
                    values.append(actor_id or "system")
                if "terminal_at" not in patch:
                    assignments.append("terminal_at=?")
                    values.append(now)
                if "terminal_reason" not in patch:
                    assignments.append("terminal_reason=?")
                    values.append(f"{next_state} terminal transition")
                if "terminal_event_revision_id" not in patch:
                    assignments.append("terminal_event_revision_id=COALESCE(terminal_event_revision_id, ?)")
                    values.append(current_record["event_revision_id"])
        for key, value in patch.items():
            assignments.append(f"{key}=?")
            values.append(
                _json(value)
                if key.endswith("_json") and not isinstance(value, str)
                else value
            )
        if next_state in TERMINAL_NEGOTIATION_STATUSES and "completed_at" not in patch:
            assignments.append("completed_at=COALESCE(completed_at, ?)")
            values.append(now)
        values.extend([negotiation_id, expected_state])
        cursor = conn.execute(
            f"""
            UPDATE meeting_time_negotiations
            SET {", ".join(assignments)}
            WHERE negotiation_id=?
              AND status=?
            """,
            values,
        )
        if int(cursor.rowcount or 0) != 1:
            row = conn.execute(
                "SELECT status FROM meeting_time_negotiations WHERE negotiation_id=?",
                (negotiation_id,),
            ).fetchone()
            if row is None:
                conn.close()
                raise KeyError(negotiation_id)
            conn.close()
            return {"ok": False, "reason": "state_conflict"}
        record = dict(
            conn.execute(
                "SELECT * FROM meeting_time_negotiations WHERE negotiation_id=?",
                (negotiation_id,),
            ).fetchone()
        )
        self._record_negotiation_event(
            conn,
            negotiation_id=negotiation_id,
            event_type="STATE_TRANSITIONED",
            actor_type=(actor_id or "system").split(":", 1)[0]
            if ":" in (actor_id or "system")
            else "system",
            actor_id=actor_id or "system",
            prior_state=expected_state,
            next_state=next_state,
            payload={"patch": patch},
        )
        conn.commit()
        conn.close()
        return {"ok": True, "record": record}

    def expire_negotiation_if_due(
        self,
        negotiation_id: str,
        *,
        owner: str,
        now_utc: datetime,
    ) -> dict[str, Any]:
        record = self.get_negotiation(negotiation_id)
        if record["status"] in TERMINAL_NEGOTIATION_STATUSES:
            return {"expired": False, "reason": "terminal", "record": record}
        expires_at = datetime.fromisoformat(
            str(record["expires_at_utc"]).replace("Z", "+00:00")
        )
        if now_utc.astimezone(timezone.utc) < expires_at:
            return {"expired": False, "reason": "not_due", "record": record}
        result = self.transition_negotiation_state(
            negotiation_id,
            expected_state=str(record["status"]),
            next_state="expired",
            patch={},
            actor_id=owner,
        )
        if not result["ok"]:
            return {
                "expired": False,
                "reason": result["reason"],
                "record": self.get_negotiation(negotiation_id),
            }
        with self._connect() as conn:
            self._record_negotiation_event(
                conn,
                negotiation_id=negotiation_id,
                event_type="CASE_EXPIRED",
                actor_type=owner.split(":", 1)[0] if ":" in owner else "system",
                actor_id=owner,
                prior_state=record["status"],
                next_state="expired",
                payload={"expires_at_utc": record["expires_at_utc"]},
            )
        return {"expired": True, "record": result["record"]}

    def add_candidate_slot(
        self,
        negotiation_id: str,
        *,
        proposed_by_user_id: str,
        round_number: int,
        start_time: str,
        end_time: str,
        timezone_name: str,
        source_text: str | None,
    ) -> dict[str, Any]:
        now = utc_now_iso()
        slot_id = _hash_id(
            "slot",
            [
                "meeting_time_slot:v1",
                negotiation_id,
                start_time,
                end_time,
                timezone_name,
            ],
        )
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO meeting_time_candidate_slots(
                    slot_id, negotiation_id, proposed_by_user_id, round_number,
                    start_time, end_time, timezone, source_text, status, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'candidate', ?)
                """,
                (
                    slot_id,
                    negotiation_id,
                    proposed_by_user_id,
                    int(round_number),
                    start_time,
                    end_time,
                    timezone_name,
                    source_text,
                    now,
                ),
            )
            self._record_negotiation_event(
                conn,
                negotiation_id=negotiation_id,
                event_type="SLOT_PROPOSED",
                actor_type="participant",
                actor_id=proposed_by_user_id,
                payload={
                    "slot_id": slot_id,
                    "start_time": start_time,
                    "end_time": end_time,
                },
            )
            row = conn.execute(
                "SELECT * FROM meeting_time_candidate_slots WHERE slot_id=?",
                (slot_id,),
            ).fetchone()
        return dict(row)

    def list_candidate_slots(self, negotiation_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM meeting_time_candidate_slots
                WHERE negotiation_id=?
                ORDER BY round_number, created_at, slot_id
                """,
                (negotiation_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def list_votes_for_slot(
        self,
        *,
        negotiation_id: str,
        slot_id: str,
    ) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM meeting_time_negotiation_votes
                WHERE negotiation_id=? AND slot_id=?
                ORDER BY created_at, vote_id
                """,
                (negotiation_id, slot_id),
            ).fetchall()
        return [dict(row) for row in rows]

    def update_negotiation_participant_response(
        self,
        *,
        negotiation_id: str,
        attendee_user_id: str,
        latest_response_status: str,
        latest_slot_id: str | None = None,
        delivery_status: str | None = None,
        contacted: bool = False,
        responded: bool = True,
    ) -> dict[str, Any]:
        now = utc_now_iso()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE meeting_time_negotiation_participants
                SET latest_response_status=?,
                    latest_slot_id=COALESCE(?, latest_slot_id),
                    delivery_status=COALESCE(?, delivery_status),
                    last_contacted_at=CASE WHEN ? THEN ? ELSE last_contacted_at END,
                    last_response_at=CASE WHEN ? THEN ? ELSE last_response_at END,
                    updated_at=?
                WHERE negotiation_id=? AND attendee_user_id=?
                """,
                (
                    latest_response_status,
                    latest_slot_id,
                    delivery_status,
                    1 if contacted else 0,
                    now,
                    1 if responded else 0,
                    now,
                    now,
                    negotiation_id,
                    attendee_user_id,
                ),
            )
            row = conn.execute(
                """
                SELECT * FROM meeting_time_negotiation_participants
                WHERE negotiation_id=? AND attendee_user_id=?
                """,
                (negotiation_id, attendee_user_id),
            ).fetchone()
        if row is None:
            raise KeyError(f"{negotiation_id}:{attendee_user_id}")
        return dict(row)

    def required_participants_have_yes(
        self,
        *,
        negotiation_id: str,
        slot_id: str,
    ) -> bool:
        slot = self.get_candidate_slot(slot_id)
        participants = self.list_negotiation_participants(negotiation_id)
        required_ids = {
            str(item["attendee_user_id"])
            for item in participants
            if int(item["required_for_consent"] or 0) == 1
        }
        votes = self.list_votes_for_slot(negotiation_id=negotiation_id, slot_id=slot_id)
        yes_ids = {
            str(item["attendee_user_id"]) for item in votes if item["vote"] == "yes"
        }
        yes_ids.add(str(slot["proposed_by_user_id"]))
        return bool(required_ids) and required_ids.issubset(yes_ids)

    def reserve_outbound_message(
        self,
        *,
        negotiation_id: str,
        message_type: str,
        participant_user_id: str,
        payload: dict[str, Any],
        slot_id: str | None = None,
        round_number: int | None = None,
        agent_trace_ref: str | None = None,
    ) -> dict[str, Any]:
        message_event_id = _hash_id(
            "out",
            [
                "meeting_time_outbound:v1",
                negotiation_id,
                message_type,
                participant_user_id,
                slot_id,
                round_number,
            ],
            length=32,
        )
        now = utc_now_iso()
        with self._connect() as conn:
            try:
                conn.execute(
                    """
                    INSERT INTO meeting_time_negotiation_messages(
                        message_event_id, negotiation_id, direction,
                        participant_user_id, message_channel, message_id,
                        message_type, payload_json, agent_trace_ref, created_at
                    )
                    VALUES (?, ?, 'outbound', ?, 'feishu', NULL, ?, ?, ?, ?)
                    """,
                    (
                        message_event_id,
                        negotiation_id,
                        participant_user_id,
                        message_type,
                        _json(payload),
                        agent_trace_ref,
                        now,
                    ),
                )
                reserved = True
                self._record_negotiation_event(
                    conn,
                    negotiation_id=negotiation_id,
                    event_type="OUTBOUND_RESERVED",
                    actor_type="agent",
                    actor_id="meeting-time-negotiator",
                    payload={
                        "message_event_id": message_event_id,
                        "message_type": message_type,
                        "participant_user_id": participant_user_id,
                    },
                )
            except sqlite3.IntegrityError:
                reserved = False
            row = conn.execute(
                """
                SELECT * FROM meeting_time_negotiation_messages
                WHERE message_event_id=?
                """,
                (message_event_id,),
            ).fetchone()
        return {"reserved": reserved, "message": dict(row)}

    def mark_outbound_message_sent(
        self,
        *,
        message_event_id: str,
        provider_message_id: str,
    ) -> dict[str, Any]:
        now = utc_now_iso()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE meeting_time_negotiation_messages
                SET message_id=?
                WHERE message_event_id=? AND direction='outbound'
                """,
                (provider_message_id, message_event_id),
            )
            row = conn.execute(
                "SELECT * FROM meeting_time_negotiation_messages WHERE message_event_id=?",
                (message_event_id,),
            ).fetchone()
            if row is None:
                raise KeyError(message_event_id)
            self._record_negotiation_event(
                conn,
                negotiation_id=row["negotiation_id"],
                event_type="OUTBOUND_SENT",
                actor_type="agent",
                actor_id="meeting-time-negotiator",
                payload={
                    "message_event_id": message_event_id,
                    "message_id": provider_message_id,
                    "sent_at": now,
                },
            )
        return dict(row)

    def get_negotiation_message(self, message_event_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM meeting_time_negotiation_messages WHERE message_event_id=?",
                (message_event_id,),
            ).fetchone()
        if row is None:
            raise KeyError(message_event_id)
        return dict(row)

    def get_outbound_negotiation_message_by_provider_id(
        self,
        *,
        provider_message_id: str,
    ) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM meeting_time_negotiation_messages
                WHERE direction='outbound'
                  AND message_channel='feishu'
                  AND message_id=?
                """,
                (provider_message_id,),
            ).fetchone()
        if row is None:
            raise KeyError(provider_message_id)
        return dict(row)

    def record_inbound_reply_rejected(
        self,
        *,
        negotiation_id: str,
        participant_user_id: str,
        reason: str,
        message_id: str | None = None,
    ) -> dict[str, Any]:
        with self._connect() as conn:
            return self._record_negotiation_event(
                conn,
                negotiation_id=negotiation_id,
                event_type="INBOUND_REJECTED",
                actor_type="participant",
                actor_id=participant_user_id,
                payload={"reason": reason, "message_id": message_id},
            )

    def record_inbound_reply_accepted(
        self,
        *,
        negotiation_id: str,
        participant_user_id: str,
        message_id: str,
        message_type: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        message_event_id = _hash_id(
            "in",
            [
                "meeting_time_inbound:v1",
                negotiation_id,
                participant_user_id,
                message_id,
            ],
            length=32,
        )
        now = utc_now_iso()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO meeting_time_negotiation_messages(
                    message_event_id, negotiation_id, direction,
                    participant_user_id, message_channel, message_id,
                    message_type, payload_json, agent_trace_ref, created_at
                )
                VALUES (?, ?, 'inbound', ?, 'feishu', ?, ?, ?, NULL, ?)
                """,
                (
                    message_event_id,
                    negotiation_id,
                    participant_user_id,
                    message_id,
                    message_type,
                    _json(payload),
                    now,
                ),
            )
            self._record_negotiation_event(
                conn,
                negotiation_id=negotiation_id,
                event_type="INBOUND_ACCEPTED",
                actor_type="participant",
                actor_id=participant_user_id,
                payload={
                    "message_event_id": message_event_id,
                    "message_id": message_id,
                },
            )
            row = conn.execute(
                "SELECT * FROM meeting_time_negotiation_messages WHERE message_event_id=?",
                (message_event_id,),
            ).fetchone()
        return dict(row)

    def record_vote(
        self,
        *,
        negotiation_id: str,
        slot_id: str,
        attendee_user_id: str,
        vote: str,
        alternative_slot_id: str | None = None,
        note: str | None = None,
    ) -> dict[str, Any]:
        now = utc_now_iso()
        vote_id = _hash_id(
            "vote",
            ["meeting_time_vote:v1", negotiation_id, slot_id, attendee_user_id],
        )
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO meeting_time_negotiation_votes(
                    vote_id, negotiation_id, slot_id, attendee_user_id, vote,
                    alternative_slot_id, note, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    vote_id,
                    negotiation_id,
                    slot_id,
                    attendee_user_id,
                    vote,
                    alternative_slot_id,
                    note,
                    now,
                ),
            )
            self._record_negotiation_event(
                conn,
                negotiation_id=negotiation_id,
                event_type="VOTE_RECORDED",
                actor_type="participant",
                actor_id=attendee_user_id,
                payload={
                    "slot_id": slot_id,
                    "vote": vote,
                    "alternative_slot_id": alternative_slot_id,
                },
            )
            row = conn.execute(
                "SELECT * FROM meeting_time_negotiation_votes WHERE vote_id=?",
                (vote_id,),
            ).fetchone()
        return dict(row)

    def get_candidate_slot(self, slot_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM meeting_time_candidate_slots WHERE slot_id=?",
                (slot_id,),
            ).fetchone()
        if row is None:
            raise KeyError(slot_id)
        return dict(row)

    def verify_negotiation_finalization(
        self,
        *,
        negotiation_id: str,
        selected_slot_id: str,
        decision_source: str,
        requested_by_user_id: str,
    ) -> dict[str, Any]:
        negotiation = self.get_negotiation(negotiation_id)
        if decision_source == "requester_final_decision":
            if requested_by_user_id != negotiation["creator_user_id"]:
                raise ValueError("requester_final_decision requires requester identity")
            return {"ok": True, "decision_source": decision_source}
        slot = self.get_candidate_slot(selected_slot_id)
        if slot["negotiation_id"] != negotiation_id:
            raise ValueError("selected slot does not belong to negotiation")
        if decision_source != "consent":
            raise ValueError("invalid decision_source")
        participants = self.list_negotiation_participants(negotiation_id)
        required_ids = {
            str(item["attendee_user_id"])
            for item in participants
            if int(item["required_for_consent"] or 0) == 1
        }
        if not required_ids:
            raise ValueError("no required participants for consent")
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT attendee_user_id, vote FROM meeting_time_negotiation_votes
                WHERE negotiation_id=? AND slot_id=?
                """,
                (negotiation_id, selected_slot_id),
            ).fetchall()
        yes_ids = {str(row["attendee_user_id"]) for row in rows if row["vote"] == "yes"}
        trigger_ids = set(
            json.loads(str(negotiation["trigger_attendee_user_ids_json"] or "[]"))
        )
        trigger_satisfied = {
            user_id
            for user_id in trigger_ids
            if user_id == slot["proposed_by_user_id"] or user_id in yes_ids
        }
        missing_yes = sorted(
            required_ids - yes_ids - {str(slot["proposed_by_user_id"])}
        )
        missing_trigger = sorted(trigger_ids - trigger_satisfied)
        if missing_yes or missing_trigger:
            raise ValueError(
                "consent finalization requires all required participant yes votes"
            )
        return {
            "ok": True,
            "decision_source": decision_source,
            "required_participants": sorted(required_ids),
        }

    def create_finalize_attempt(
        self,
        *,
        negotiation_id: str,
        selected_slot_id: str,
        decision_source: str,
        requested_by_user_id: str,
        calendar_update_payload: dict[str, Any],
    ) -> dict[str, Any]:
        now = utc_now_iso()
        selected_slot = None
        slot_start_time = ""
        slot_end_time = ""
        slot_timezone = ""
        with self._connect() as conn:
            negotiation = conn.execute(
                "SELECT * FROM meeting_time_negotiations WHERE negotiation_id=?",
                (negotiation_id,),
            ).fetchone()
            if negotiation is None:
                raise KeyError(negotiation_id)
            if not selected_slot_id:
                if decision_source == "requester_final_decision":
                    selected_slot_id = f"requester-final:{str(negotiation['negotiation_id'])}"
                else:
                    raise ValueError("selected_slot_id is required")
            try:
                row = conn.execute(
                    "SELECT * FROM meeting_time_candidate_slots WHERE slot_id=?",
                    (selected_slot_id,),
                ).fetchone()
            except Exception:
                row = None
            if row is not None:
                selected_slot = dict(row)
                if str(selected_slot.get("negotiation_id") or "") != negotiation_id:
                    raise ValueError("selected slot does not belong to negotiation")
                slot_start_time = str(selected_slot.get("start_time") or "")
                slot_end_time = str(selected_slot.get("end_time") or "")
                slot_timezone = str(selected_slot.get("timezone") or "")
            elif decision_source == "requester_final_decision":
                payload = negotiation.get("selected_slot_json") or "{}"
                try:
                    selected_slot_payload = json.loads(str(payload))
                except json.JSONDecodeError:
                    selected_slot_payload = {}
                if not isinstance(selected_slot_payload, dict):
                    selected_slot_payload = {}
                slot_start_time = str(selected_slot_payload.get("start_time") or "")
                slot_end_time = str(selected_slot_payload.get("end_time") or "")
                slot_timezone = str(selected_slot_payload.get("timezone") or "")
                if not slot_start_time or not slot_end_time:
                    slot_start_time = str(negotiation.get("original_start_time") or "")
                    slot_end_time = str(negotiation.get("original_end_time") or "")
                    slot_timezone = str(negotiation.get("timezone") or "UTC")
                if not slot_start_time or not slot_end_time or not slot_timezone:
                    raise ValueError("cannot derive original slot for requester final decision")
            else:
                raise KeyError(selected_slot_id)
            key = hashlib.sha256(
                _canonical_json_array(
                    [
                        "meeting_time_finalize:v1",
                        negotiation_id,
                        negotiation["event_revision_id"],
                        selected_slot_id,
                        decision_source,
                        slot_start_time,
                        slot_end_time,
                    ]
                ).encode("utf-8")
            ).hexdigest()
            attempt_id = _hash_id(
                "fin", ["meeting_time_finalize_attempt:v1", key], length=32
            )
            conn.execute(
                """
                INSERT INTO meeting_time_finalize_attempts(
                    finalize_attempt_id, finalize_idempotency_key, negotiation_id,
                    event_revision_id, selected_slot_id, decision_source,
                    requested_by_user_id, calendar_update_payload_json, status,
                    next_retry_at, calendar_update_result_json, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', NULL, NULL, ?, ?)
                ON CONFLICT(finalize_idempotency_key) DO NOTHING
                """,
                (
                    attempt_id,
                    key,
                    negotiation_id,
                    negotiation["event_revision_id"],
                    selected_slot_id,
                    decision_source,
                    requested_by_user_id,
                    _json(calendar_update_payload),
                    now,
                    now,
                ),
            )
            self._record_negotiation_event(
                conn,
                negotiation_id=negotiation_id,
                event_type="FINALIZE_ATTEMPTED",
                actor_type="requester",
                actor_id=requested_by_user_id,
                payload={
                    "selected_slot_id": selected_slot_id,
                    "decision_source": decision_source,
                },
            )
            row = conn.execute(
                """
                SELECT * FROM meeting_time_finalize_attempts
                WHERE finalize_idempotency_key=?
                """,
                (key,),
            ).fetchone()
        return dict(row)

    def set_negotiation_finalize_attempt(
        self,
        negotiation_id: str,
        finalize_attempt_id: str,
    ) -> dict[str, Any]:
        now = utc_now_iso()
        with self._connect() as conn:
            exists = conn.execute(
                """
                SELECT 1 FROM meeting_time_finalize_attempts
                WHERE finalize_attempt_id=? AND negotiation_id=?
                """,
                (finalize_attempt_id, negotiation_id),
            ).fetchone()
            if exists is None:
                raise ValueError("finalize_attempt_id does not exist for negotiation")
            conn.execute(
                """
                UPDATE meeting_time_negotiations
                SET finalize_attempt_id=?, updated_at=?
                WHERE negotiation_id=?
                """,
                (finalize_attempt_id, now, negotiation_id),
            )
        return self.get_negotiation(negotiation_id)

    def mark_negotiation_finalization_failed(
        self,
        negotiation_id: str,
        *,
        failure_reason: str,
        finalize_status: str = "failed_permanent",
        terminal_reason: str | None = None,
        terminal_authority: str | None = None,
    ) -> dict[str, Any]:
        now = utc_now_iso()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT status FROM meeting_time_negotiations WHERE negotiation_id=?",
                (negotiation_id,),
            ).fetchone()
            if row is None:
                raise KeyError(negotiation_id)
            prior_state = row["status"]
            conn.execute(
                """
                UPDATE meeting_time_negotiations
                SET status='failed',
                    failure_reason=?,
                    finalize_status=?,
                    terminal_authority=COALESCE(terminal_authority, ?),
                    terminal_reason=COALESCE(terminal_reason, ?),
                    terminal_at=COALESCE(terminal_at, ?),
                    terminal_event_revision_id=COALESCE(terminal_event_revision_id, event_revision_id),
                    completed_at=COALESCE(completed_at, ?),
                    updated_at=?
                WHERE negotiation_id=?
                """,
                (
                    failure_reason,
                    finalize_status,
                    terminal_authority or "system:meeting-finalizer",
                    terminal_reason or "finalization failed",
                    now,
                    now,
                    negotiation_id,
                ),
            )
            updated = conn.execute(
                "SELECT * FROM meeting_time_negotiations WHERE negotiation_id=?",
                (negotiation_id,),
            ).fetchone()
            self._record_negotiation_event(
                conn,
                negotiation_id=negotiation_id,
                event_type="STATE_TRANSITIONED",
                actor_type="system",
                actor_id="meeting-finalizer",
                prior_state=prior_state,
                next_state="failed",
                payload={
                    "failure_reason": failure_reason,
                    "finalize_status": finalize_status,
                },
            )
        return dict(updated)

    def mark_finalize_attempt_failed(
        self,
        finalize_attempt_id: str,
        *,
        retryable: bool,
        detail: dict[str, Any],
        next_retry_at: datetime | None = None,
    ) -> dict[str, Any]:
        now = utc_now_iso()
        next_retry_iso = (
            next_retry_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
            if next_retry_at is not None
            else None
        )
        if retryable and next_retry_iso is None:
            raise ValueError("retryable finalize failures require next_retry_at")
        status = (
            "calendar_update_failed_retryable"
            if retryable
            else "calendar_update_failed_permanent"
        )
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE meeting_time_finalize_attempts
                SET status=?, next_retry_at=?, calendar_update_result_json=?, updated_at=?
                WHERE finalize_attempt_id=?
                """,
                (status, next_retry_iso, _json(detail), now, finalize_attempt_id),
            )
            row = conn.execute(
                "SELECT * FROM meeting_time_finalize_attempts WHERE finalize_attempt_id=?",
                (finalize_attempt_id,),
            ).fetchone()
            if row is None:
                raise KeyError(finalize_attempt_id)
            self._record_negotiation_event(
                conn,
                negotiation_id=row["negotiation_id"],
                event_type="CALENDAR_UPDATE_FAILED",
                actor_type="system",
                actor_id="meeting-finalizer",
                payload={
                    "finalize_attempt_id": finalize_attempt_id,
                    "retryable": retryable,
                },
            )
        return dict(row)

    def mark_finalize_attempt_started(self, finalize_attempt_id: str) -> dict[str, Any]:
        now = utc_now_iso()
        with self._connect() as conn:
            updated = conn.execute(
                """
                UPDATE meeting_time_finalize_attempts
                SET status='calendar_update_started', updated_at=?
                WHERE finalize_attempt_id=?
                  AND status IN ('pending', 'calendar_update_failed_retryable')
                """,
                (now, finalize_attempt_id),
            )
            row = conn.execute(
                "SELECT * FROM meeting_time_finalize_attempts WHERE finalize_attempt_id=?",
                (finalize_attempt_id,),
            ).fetchone()
            if row is not None and updated.rowcount > 0:
                self._record_negotiation_event(
                    conn,
                    negotiation_id=row["negotiation_id"],
                    event_type="CALENDAR_UPDATE_STARTED",
                    actor_type="system",
                    actor_id="meeting-finalizer",
                    payload={"finalize_attempt_id": finalize_attempt_id},
                )
        if row is None:
            raise KeyError(finalize_attempt_id)
        return dict(row)

    def mark_finalize_attempt_succeeded(
        self,
        finalize_attempt_id: str,
        *,
        result: dict[str, Any],
    ) -> dict[str, Any]:
        now = utc_now_iso()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE meeting_time_finalize_attempts
                SET status='calendar_update_succeeded',
                    calendar_update_result_json=?,
                    next_retry_at=NULL,
                    updated_at=?
                WHERE finalize_attempt_id=?
                """,
                (_json(result), now, finalize_attempt_id),
            )
            row = conn.execute(
                "SELECT * FROM meeting_time_finalize_attempts WHERE finalize_attempt_id=?",
                (finalize_attempt_id,),
            ).fetchone()
            if row is None:
                raise KeyError(finalize_attempt_id)
            conn.execute(
                """
                UPDATE meeting_time_negotiations
                SET finalize_status='succeeded',
                    finalize_attempt_id=?,
                    updated_at=?
                WHERE negotiation_id=?
                """,
                (finalize_attempt_id, now, row["negotiation_id"]),
            )
            self._record_negotiation_event(
                conn,
                negotiation_id=row["negotiation_id"],
                event_type="CALENDAR_UPDATE_SUCCEEDED",
                actor_type="system",
                actor_id="meeting-finalizer",
                payload={"finalize_attempt_id": finalize_attempt_id},
            )
        return dict(row)

    def finalize_attempt_retry_due(
        self,
        finalize_attempt_id: str,
        *,
        now_utc: datetime,
    ) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT status, next_retry_at FROM meeting_time_finalize_attempts WHERE finalize_attempt_id=?",
                (finalize_attempt_id,),
            ).fetchone()
        if row is None:
            raise KeyError(finalize_attempt_id)
        if (
            row["status"] != "calendar_update_failed_retryable"
            or row["next_retry_at"] is None
        ):
            return False
        next_retry = datetime.fromisoformat(
            str(row["next_retry_at"]).replace("Z", "+00:00")
        )
        return now_utc.astimezone(timezone.utc) >= next_retry

    def list_operation_monitors(
        self, *, workspace_id: str, limit: int
    ) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT m.*,
                       COUNT(t.delivery_task_id) AS pending_delivery_tasks
                FROM meeting_rsvp_monitors m
                LEFT JOIN meeting_rsvp_delivery_tasks t
                  ON t.monitor_id = m.monitor_id
                 AND t.status IN ('pending', 'failed_retryable')
                WHERE m.workspace_id=?
                  AND (
                    m.status IN ('pending_start', 'active', 'error', 'complete')
                    OR t.delivery_task_id IS NOT NULL
                  )
                GROUP BY m.monitor_id
                ORDER BY m.updated_at DESC
                LIMIT ?
                """,
                (workspace_id, int(limit)),
            ).fetchall()
        return [dict(row) for row in rows]

    def list_operation_delivery_tasks(
        self,
        *,
        workspace_id: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM meeting_rsvp_delivery_tasks
                WHERE workspace_id=?
                  AND status IN ('pending', 'failed_retryable', 'failed_permanent')
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (workspace_id, int(limit)),
            ).fetchall()
        return [dict(row) for row in rows]

    def list_operation_negotiations(
        self,
        *,
        workspace_id: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM meeting_time_negotiations
                WHERE workspace_id=?
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (workspace_id, int(limit)),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_negotiation_for_workspace(
        self,
        negotiation_id: str,
        *,
        workspace_id: str,
    ) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM meeting_time_negotiations
                WHERE negotiation_id=? AND workspace_id=?
                """,
                (negotiation_id, workspace_id),
            ).fetchone()
        if row is None:
            raise KeyError(negotiation_id)
        return dict(row)
