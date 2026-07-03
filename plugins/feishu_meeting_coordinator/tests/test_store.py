from __future__ import annotations

import sqlite3

import pytest

from feishu_meeting_coordinator.store import MeetingCoordinatorStore


def _binding() -> dict[str, str | None]:
    return {
        "workspace_owner_id": "ws_1",
        "creator_user_id": "user_1",
        "platform": "feishu",
        "chat_id": "oc_creator",
        "thread_id": None,
        "session_id": "sess_1",
        "session_key": "key_1",
        "hermes_home": "/tmp/hermes",
        "delivery_adapter_key": None,
        "source": "plugin_test",
        "captured_at": "2026-06-15T00:00:00Z",
    }


def _monitor_payload() -> dict:
    return {
        "workspace_id": "ws_1",
        "creator_user_id": "user_1",
        "event_id": "event_1",
        "event_revision_id": "rev_1",
        "calendar_id": "cal_1",
        "creator_delivery_binding": _binding(),
        "meeting_title": "Planning",
        "start_time": "2026-06-15T01:00:00Z",
        "end_time": "2026-06-15T01:30:00Z",
        "timezone": "Asia/Shanghai",
        "attendees": [
            {"user_id": "ou_a", "message_user_id": "ou_a", "display_name": "Amy"},
            {"user_id": "ou_b", "message_user_id": "ou_b", "display_name": "Bob"},
        ],
    }


@pytest.fixture
def store(tmp_path) -> MeetingCoordinatorStore:
    return MeetingCoordinatorStore(tmp_path / "state.db")


def test_plugin_store_schema_enforces_fk_and_kanban_columns(store: MeetingCoordinatorStore):
    with store._connect() as conn:
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        negotiation_columns = {
            row["name"]
            for row in conn.execute(
                "PRAGMA table_info(meeting_time_negotiations)"
            ).fetchall()
        }
        message_columns = {
            row["name"]
            for row in conn.execute(
                "PRAGMA table_info(meeting_time_negotiation_messages)"
            ).fetchall()
        }
        event_columns = {
            row["name"]
            for row in conn.execute(
                "PRAGMA table_info(meeting_time_negotiation_events)"
            ).fetchall()
        }

        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO meeting_time_candidate_slots(
                    slot_id, negotiation_id, proposed_by_user_id, round_number,
                    start_time, end_time, timezone, source_text, status, created_at
                )
                VALUES ('slot_orphan', 'missing_case', 'ou_a', 1,
                        '2026-06-15T02:00:00Z', '2026-06-15T02:30:00Z',
                        'Asia/Shanghai', NULL, 'candidate', '2026-06-15T00:00:00Z')
                """
            )

    assert "kanban_task_id" in negotiation_columns
    assert "kanban_comment_id" in message_columns
    assert {"kanban_task_id", "kanban_run_id"}.issubset(event_columns)


def test_plugin_store_creates_merged_negotiation_case(store: MeetingCoordinatorStore):
    monitor = store.start_monitor(_monitor_payload())
    store.update_attendee_statuses(
        monitor["monitor_id"],
        [
            {"user_id": "ou_a", "response_status": "declined"},
            {"user_id": "ou_b", "response_status": "declined"},
        ],
    )

    first = store.create_or_get_negotiation_case(
        monitor_id=monitor["monitor_id"],
        event_revision_id=monitor["event_revision_id"],
        trigger_attendee_user_id="ou_a",
    )
    second = store.create_or_get_negotiation_case(
        monitor_id=monitor["monitor_id"],
        event_revision_id=monitor["event_revision_id"],
        trigger_attendee_user_id="ou_b",
    )

    participants = store.list_negotiation_participants(first["negotiation_id"])

    assert first["negotiation_id"] == second["negotiation_id"]
    assert {
        item["attendee_user_id"] for item in participants if item["role"] == "decliner"
    } == {"ou_a", "ou_b"}
    assert [
        item["required_for_consent"]
        for item in participants
        if item["role"] == "requester"
    ] == [0]
