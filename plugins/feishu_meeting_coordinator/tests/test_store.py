from __future__ import annotations

import json
import sqlite3

import pytest

from feishu_meeting_coordinator.dashboard.plugin_api import negotiation_detail
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
        participant_columns = {
            row["name"]
            for row in conn.execute(
                "PRAGMA table_info(meeting_time_negotiation_participants)"
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

    assert {"session_id", "kanban_task_id", "followup_cron_job_id"}.issubset(
        negotiation_columns
    )
    assert {"followup_cron_status", "followup_cron_last_tick_at"}.issubset(
        negotiation_columns
    )
    assert {"followup_cron_failure_count", "next_followup_at"}.issubset(
        negotiation_columns
    )
    assert {"followup_count", "last_followup_at"}.issubset(participant_columns)
    lock_exists = conn.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type='table' AND name='meeting_time_negotiation_case_locks'
        """
    ).fetchone()
    assert lock_exists is not None
    assert "kanban_comment_id" in message_columns
    assert {"kanban_task_id", "kanban_run_id"}.issubset(event_columns)


def test_plugin_store_migrates_legacy_followup_columns(tmp_path):
    db_path = tmp_path / "legacy.db"
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE meeting_rsvp_attendees (
                monitor_id TEXT NOT NULL,
                attendee_user_id TEXT NOT NULL,
                message_user_id TEXT,
                display_name TEXT,
                response_status TEXT NOT NULL,
                last_response_at TEXT,
                delivery_status TEXT NOT NULL,
                escalated_at TEXT,
                PRIMARY KEY(monitor_id, attendee_user_id)
            );
            CREATE TABLE meeting_time_negotiation_participants (
                negotiation_id TEXT NOT NULL,
                attendee_user_id TEXT NOT NULL,
                message_user_id TEXT,
                display_name TEXT,
                role TEXT NOT NULL,
                required_for_consent INTEGER NOT NULL,
                latest_response_status TEXT NOT NULL,
                latest_slot_id TEXT,
                last_contacted_at TEXT,
                last_response_at TEXT,
                delivery_status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY(negotiation_id, attendee_user_id)
            );
            """
        )

    migrated = MeetingCoordinatorStore(db_path)
    monitor = migrated.start_monitor(_monitor_payload())

    with migrated._connect() as conn:
        attendee_columns = {
            row["name"]
            for row in conn.execute(
                "PRAGMA table_info(meeting_rsvp_attendees)"
            ).fetchall()
        }
        participant_columns = {
            row["name"]
            for row in conn.execute(
                "PRAGMA table_info(meeting_time_negotiation_participants)"
            ).fetchall()
        }

    assert monitor["status"] == "pending_start"
    assert {"followup_count", "last_followup_at"}.issubset(attendee_columns)
    assert {"followup_count", "last_followup_at"}.issubset(participant_columns)


def test_plugin_store_backfills_negotiation_session_id_from_payload(
    store: MeetingCoordinatorStore,
):
    monitor = store.start_monitor(_monitor_payload())
    negotiation = store.create_or_get_negotiation_case(
        monitor_id=monitor["monitor_id"],
        event_revision_id=monitor["event_revision_id"],
        trigger_attendee_user_id="ou_a",
        session_id="sess_1",
    )
    with store._connect() as conn:
        conn.execute(
            "UPDATE meeting_time_negotiations SET session_id='' WHERE negotiation_id=?",
            (negotiation["negotiation_id"],),
        )

    reloaded = MeetingCoordinatorStore(store.path)

    assert reloaded.get_negotiation(negotiation["negotiation_id"])["session_id"] == "sess_1"


def test_negotiation_detail_exposes_finalize_evidence_for_workflow_projection(
    store: MeetingCoordinatorStore,
):
    monitor = store.start_monitor(_monitor_payload())
    negotiation = store.create_or_get_negotiation_case(
        monitor_id=monitor["monitor_id"],
        event_revision_id=monitor["event_revision_id"],
        trigger_attendee_user_id="ou_a",
        session_id="sess_1",
    )

    detail = negotiation_detail(
        negotiation_id=negotiation["negotiation_id"],
        workspace_id="ws_1",
        store=store,
    )

    assert detail["negotiation"]["metadata"]["finalize_status"] == "not_started"
    assert detail["negotiation"]["metadata"]["finalize_attempt_id"] == ""
    assert detail["finalize_attempts"] == []
    assert isinstance(detail["events"], list)


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
        session_id="sess_1",
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
    assert first["session_id"] == "sess_1"
    assert store.get_negotiation(first["negotiation_id"])["session_id"] == "sess_1"
    with pytest.raises(KeyError):
        store.set_negotiation_followup_cron_metadata(
            "non-existent",
            followup_cron_job_id="job_missing",
        )
    updated = store.set_negotiation_followup_cron_metadata(
        first["negotiation_id"],
        followup_cron_job_id="job_1",
        followup_cron_status="active",
        followup_cron_failure_count=1,
        followup_cron_last_tick_at="2026-06-15T10:00:00Z",
        next_followup_at="2026-06-15T10:02:00Z",
    )
    assert updated["followup_cron_job_id"] == "job_1"
    assert updated["followup_cron_status"] == "active"
    assert updated["followup_cron_failure_count"] == 1
    assert updated["followup_cron_last_tick_at"] == "2026-06-15T10:00:00Z"
    assert updated["next_followup_at"] == "2026-06-15T10:02:00Z"


def _seed_active_negotiation(store: MeetingCoordinatorStore) -> str:
    monitor = store.start_monitor(_monitor_payload())
    negotiation = store.create_or_get_negotiation_case(
        monitor_id=monitor["monitor_id"],
        event_revision_id=monitor["event_revision_id"],
        trigger_attendee_user_id="ou_a",
        session_id="sess_1",
    )
    return str(negotiation["negotiation_id"])


def test_followup_cron_ownership_conflict_uses_owner_identity(store: MeetingCoordinatorStore):
    negotiation_id = _seed_active_negotiation(store)
    cron_name = f"meeting-time-negotiator-followup:{negotiation_id}"
    negotiation = store.get_negotiation(negotiation_id)
    workspace_id = str(negotiation["workspace_id"])
    assert store.ensure_followup_cron_ownership(
        negotiation_id=negotiation_id,
        cron_name=cron_name,
        owner_profile="meeting-coordinator",
        owner_idempotency_key="profile-a",
        workspace_id=workspace_id,
    )
    with pytest.raises(RuntimeError, match="followup cron ownership conflict"):
        store.ensure_followup_cron_ownership(
            negotiation_id=negotiation_id,
            cron_name=cron_name,
            owner_profile="meeting-coordinator",
            owner_idempotency_key="profile-b",
            workspace_id=workspace_id,
        )


def test_followup_cron_ownership_release_requires_owner_match(store: MeetingCoordinatorStore):
    negotiation_id = _seed_active_negotiation(store)
    cron_name = f"meeting-time-negotiator-followup:{negotiation_id}"
    negotiation = store.get_negotiation(negotiation_id)
    workspace_id = str(negotiation["workspace_id"])
    assert store.ensure_followup_cron_ownership(
        negotiation_id=negotiation_id,
        cron_name=cron_name,
        owner_profile="meeting-coordinator",
        owner_idempotency_key="keep-this",
        workspace_id=workspace_id,
    )
    assert (
        store.release_followup_cron_ownership(
            negotiation_id=negotiation_id,
            cron_name=cron_name,
            owner_profile="meeting-coordinator",
            owner_idempotency_key="wrong-key",
            workspace_id=workspace_id,
        )
        is False
    )
    assert store.release_followup_cron_ownership(
        negotiation_id=negotiation_id,
        cron_name=cron_name,
        owner_profile="meeting-coordinator",
        owner_idempotency_key="keep-this",
        workspace_id=workspace_id,
    )


def test_planning_events_preserve_history_and_reject_cross_revision(store):
    from dataclasses import replace
    from feishu_meeting_coordinator.decision_planning import MeetingDecisionPlanningBasis, form_decision_frontier
    monitor = store.start_monitor(_monitor_payload())
    case = store.create_or_get_negotiation_case(monitor_id=monitor['monitor_id'],
        event_revision_id='rev_1', trigger_attendee_user_id='ou_a')
    b = MeetingDecisionPlanningBasis(negotiation_id=case['negotiation_id'], event_revision_id='rev_1',
        original_slot={'slot_id': 'original', 'start_time': case['original_start_time'], 'end_time': case['original_end_time']},
        participants=())
    first = form_decision_frontier(b)
    event = store.record_decision_frontier(first)
    assert store.latest_decision_frontier(case['negotiation_id'])['input_hash'] == first.input_hash
    second = form_decision_frontier(replace(b, meeting_necessity='RESOLVED_ASYNCHRONOUSLY'))
    store.record_decision_frontier(second)
    events = [e for e in store.list_negotiation_events(case['negotiation_id']) if e['event_type'] == 'DECISION_FRONTIER_COMPUTED']
    assert len(events) == 2
    assert events[0]['event_id'] == event['event_id']
    assert store.latest_decision_frontier(case['negotiation_id'])['input_hash'] == second.input_hash
    with pytest.raises(ValueError, match='PLANNER_REVISION_MISMATCH'):
        store.record_decision_frontier(form_decision_frontier(replace(b, event_revision_id='stale')))
    assert len([e for e in store.list_negotiation_events(case['negotiation_id']) if e['event_type'] == 'DECISION_FRONTIER_COMPUTED']) == 2


def test_restart_after_compute_recovers_frontier_and_revision_change_hides_it(store):
    import os
    import subprocess
    import sys
    from feishu_meeting_coordinator.decision_planning import form_decision_frontier
    monitor = store.start_monitor(_monitor_payload())
    case = store.create_or_get_negotiation_case(monitor_id=monitor['monitor_id'],
        event_revision_id='rev_1', trigger_attendee_user_id='ou_a')
    frontier = form_decision_frontier(store.decision_planning_basis(case['negotiation_id']))
    persisted = store.record_decision_frontier(frontier)
    program = 'import json,sys; from feishu_meeting_coordinator.store import MeetingCoordinatorStore; print(json.dumps(MeetingCoordinatorStore(sys.argv[1]).latest_decision_frontier(sys.argv[2])))'
    restarted = subprocess.run([sys.executable, '-c', program, str(store.path), case['negotiation_id']],
                               capture_output=True, text=True, env=os.environ, timeout=20, check=True)
    assert json.loads(restarted.stdout)['input_hash'] == frontier.input_hash
    assert not any(event['event_type'] == 'DECISION_FRONTIER_PRESENTED'
                   for event in store.list_negotiation_events(case['negotiation_id']))
    # Inject an upstream event revision change after the persisted proposal.
    with store._connect() as conn:
        conn.execute('UPDATE meeting_time_negotiations SET event_revision_id=? WHERE negotiation_id=?',
                     ('rev_2', case['negotiation_id']))
    assert store.latest_decision_frontier(case['negotiation_id']) is None
    with pytest.raises(ValueError, match='PLANNER_REVISION_MISMATCH'):
        store.record_decision_frontier(frontier)
    assert any(event['event_id'] == persisted['event_id']
               for event in store.list_negotiation_events(case['negotiation_id']))


def test_planning_basis_uses_slot_specific_votes_and_original_rsvp(store):
    monitor = store.start_monitor(_monitor_payload())
    case = store.create_or_get_negotiation_case(monitor_id=monitor['monitor_id'],
        event_revision_id='rev_1', trigger_attendee_user_id='ou_a')
    slot = store.add_candidate_slot(case['negotiation_id'], proposed_by_user_id='ou_a', round_number=1,
        start_time='2026-06-15T03:00:00Z', end_time='2026-06-15T03:30:00Z', timezone_name='UTC', source_text=None)
    store.record_vote(negotiation_id=case['negotiation_id'], slot_id=slot['slot_id'], attendee_user_id='ou_b', vote='no')
    basis = store.decision_planning_basis(case['negotiation_id'])
    states = {(r['slot_id'], r['attendee_user_id']): r['status'] for r in basis.availability}
    assert states[slot['slot_id'], 'ou_a'] == 'AVAILABLE'
    assert states[slot['slot_id'], 'ou_b'] == 'UNAVAILABLE'
    assert states['original', 'ou_b'] == 'UNKNOWN'
    assert any(p['role'] == 'requester' for p in basis.participants)
    assert states['original', 'user_1'] == 'UNKNOWN'


def test_case_tick_queries_material_candidate_instead_of_latest_blocked_slot(store):
    from feishu_meeting_coordinator.gateway import _run_negotiation_case_tick
    monitor = store.start_monitor(_monitor_payload())
    store.update_attendee_statuses(monitor['monitor_id'], [{'user_id': 'ou_a', 'response_status': 'declined'}])
    case = store.create_or_get_negotiation_case(monitor_id=monitor['monitor_id'],
        event_revision_id='rev_1', trigger_attendee_user_id='ou_a')
    viable = store.add_candidate_slot(case['negotiation_id'], proposed_by_user_id='ou_a', round_number=1,
        start_time='2026-06-15T03:00:00Z', end_time='2026-06-15T03:30:00Z', timezone_name='UTC', source_text=None)
    blocked = store.add_candidate_slot(case['negotiation_id'], proposed_by_user_id='ou_a', round_number=2,
        start_time='2026-06-15T04:00:00Z', end_time='2026-06-15T04:30:00Z', timezone_name='UTC', source_text=None)
    store.record_vote(negotiation_id=case['negotiation_id'], slot_id=blocked['slot_id'], attendee_user_id='ou_a', vote='no')
    store.transition_negotiation_state(case['negotiation_id'], expected_state='pending_decliner_input',
        next_state='collecting_votes', patch={'current_round': 2}, actor_id='test')
    sent = []
    result = _run_negotiation_case_tick(negotiation_id=case['negotiation_id'], store=store,
        send_message=lambda ids, text: sent.append((ids, text)) or 'provider-message')
    assert result['vote_prompts_sent'] == 1
    messages = store.list_negotiation_messages(case['negotiation_id'])
    assert '03:00' in json.loads(messages[-1]['payload_json'])['text']
    assert store.latest_decision_frontier(case['negotiation_id']) is not None


def test_dashboard_projects_recorded_frontier_without_latest_best_slot_claim(store):
    from feishu_meeting_coordinator.dashboard.plugin_api import negotiation_task_metadata
    from feishu_meeting_coordinator.decision_planning import form_decision_frontier
    monitor = store.start_monitor(_monitor_payload())
    case = store.create_or_get_negotiation_case(monitor_id=monitor['monitor_id'], event_revision_id='rev_1', trigger_attendee_user_id='ou_a')
    store.record_decision_frontier(form_decision_frontier(store.decision_planning_basis(case['negotiation_id'])))
    metadata = negotiation_task_metadata(case, store=store)
    assert 'best_slot' not in metadata
    assert 'best_slot_id' not in metadata
    assert metadata['planner_version'] == 'meeting-decision-planner.v1'
    assert metadata['decision_options'] == []
    assert metadata['information_status'] == 'CONTINUE_INFORMATION'
