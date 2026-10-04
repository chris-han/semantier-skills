from __future__ import annotations

# ruff: noqa: E402 -- plugin package path is installed explicitly for this fixture.

import sqlite3
from pathlib import Path
import sys

PLUGIN_PARENT = Path("semantier-skills/plugins").resolve()
if str(PLUGIN_PARENT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_PARENT))

import pytest

from agents.durable_responsibility import EVENT, TIMER, WAIT_EXTERNAL
from agents.timer_occurrence import ACCEPTED, CANCELLED, TimerOccurrenceStore
from feishu_meeting_coordinator.durable_runtime import MeetingResponsibilityRuntime
from feishu_meeting_coordinator.gateway import (
    _run_negotiation_followup_business,
    ensure_negotiation_followup_cron,
    finalize_negotiation_case,
    negotiation_followup_cron_tick,
    submit_negotiation_reply,
)
from feishu_meeting_coordinator.store import MeetingCoordinatorStore


def _binding():
    return {
        "workspace_owner_id": "ws_1",
        "creator_user_id": "requester",
        "platform": "feishu",
        "chat_id": "oc_requester",
        "thread_id": None,
        "session_id": "sess_1",
        "session_key": "key_1",
        "hermes_home": "/tmp/hermes",
        "delivery_adapter_key": None,
        "source": "durable_test",
        "captured_at": "2026-10-04T00:00:00Z",
    }


def _setup(tmp_path):
    store = MeetingCoordinatorStore(tmp_path / "state.db")
    monitor = store.start_monitor(
        {
            "workspace_id": "ws_1",
            "creator_user_id": "requester",
            "event_id": "event_1",
            "event_revision_id": "rev_1",
            "calendar_id": "cal_1",
            "creator_delivery_binding": _binding(),
            "meeting_title": "Durable planning",
            "start_time": "2026-10-05T01:00:00Z",
            "end_time": "2026-10-05T01:30:00Z",
            "timezone": "UTC",
            "session_id": "sess_1",
            "attendees": [
                {
                    "user_id": "attendee_a",
                    "message_user_id": "attendee_a",
                    "display_name": "A",
                }
            ],
        }
    )
    negotiation = store.create_or_get_negotiation_case(
        monitor_id=monitor["monitor_id"],
        event_revision_id=monitor["event_revision_id"],
        trigger_attendee_user_id="attendee_a",
        session_id="sess_1",
    )
    return store, negotiation


def test_requester_authority_change_blocks_decision_before_effect(tmp_path):
    from feishu_meeting_coordinator.gateway import apply_requester_decision
    store, negotiation = _setup(tmp_path)
    store.transition_negotiation_state(negotiation['negotiation_id'], expected_state=negotiation['status'],
                                       next_state='awaiting_requester_decision', patch={})
    with pytest.raises(ValueError, match='REQUESTER_AUTHORITY_REQUIRED'):
        apply_requester_decision({'negotiation_id': negotiation['negotiation_id'],
                                  'action': 'requester_cancel', 'requested_by_user_id': 'attendee_a'}, store=store)
    assert store.get_negotiation(negotiation['negotiation_id'])['status'] == 'awaiting_requester_decision'


class FakeCron:
    def __init__(self):
        self.jobs = {}
        self.created = []
        self.deleted = []
        self.fail_ensure = False

    def ensure_job(self, **kwargs):
        if self.fail_ensure:
            raise RuntimeError("timer provider unavailable")
        job_id = f"job_{len(self.created) + 1}"
        item = {"id": job_id, **kwargs}
        self.created.append(item)
        self.jobs[job_id] = item
        return job_id

    def delete_job(self, job_id):
        self.deleted.append(job_id)
        self.jobs.pop(job_id, None)
        return True

    def get_job(self, job_id):
        return self.jobs.get(job_id)

    def job_exists(self, job_id):
        return job_id in self.jobs


class FakeFeishu:
    def __init__(self):
        self.sent = []

    def get_attendee_response_statuses(self, *, calendar_id, event_id):
        return []

    def send_attendee_message(
        self, *, attendee_open_ids, message, idempotency_key=None
    ):
        message_id = f"om_{len(self.sent) + 1}"
        self.sent.append(
            {
                "targets": attendee_open_ids,
                "message": message,
                "idempotency_key": idempotency_key,
                "message_id": message_id,
            }
        )
        return {
            "delivered": attendee_open_ids,
            "failed": [],
            "message_id": message_id,
            "message_ids": {target: message_id for target in attendee_open_ids},
        }

    def get_message(self, *, message_id):
        return {"message_id": message_id, "found": True, "items": []}


def _timer_id(cron):
    return str(cron.created[-1]["name"]).split("::", 1)[1]


class FakeCalendar:
    def __init__(self):
        self.updated = []

    def update_meeting_time(self, **payload):
        self.updated.append(payload)
        return {"ok": True, "event_id": payload["event_id"]}


def test_cron_entrypoint_is_timer_signal_only_and_responsibility_runs_business(tmp_path):
    store, negotiation = _setup(tmp_path)
    cron = FakeCron()
    feishu = FakeFeishu()

    ensure_negotiation_followup_cron(
        negotiation_id=negotiation["negotiation_id"],
        store=store,
        cron=cron,
        schedule="every 1m",
    )
    runtime = MeetingResponsibilityRuntime(
        store=store, cron=cron, feishu_client=feishu, followup_interval_minutes=1
    )
    item = runtime.ensure(negotiation["negotiation_id"])
    current = runtime.responsibilities.get(item.responsibility_id)
    assert current.lifecycle_state == WAIT_EXTERNAL
    waits = runtime.responsibilities.pending_waits(item.responsibility_id)
    assert {wait.kind for wait in waits} == {EVENT, TIMER}
    assert len(cron.created) == 1

    timer_id = _timer_id(cron)
    signal = negotiation_followup_cron_tick(
        {
            "negotiation_id": negotiation["negotiation_id"],
            "timer_id": timer_id,
            "followup_interval_minutes": 1,
        },
        store=store,
        cron=cron,
        feishu_client=feishu,
    )
    assert signal["wake_accepted"] is True
    assert "followups_sent" not in signal

    assert TimerOccurrenceStore(store.path).get(timer_id).state == ACCEPTED
    assert any(
        event["event_type"] == "FOLLOWUP_TICK_STARTED"
        for event in store.list_negotiation_events(negotiation["negotiation_id"])
    )

    resumed = runtime.responsibilities.get(item.responsibility_id)
    assert resumed.lifecycle_state == WAIT_EXTERNAL
    assert len(cron.created) == 2


def test_reply_wake_cancels_sibling_timer_before_resume(tmp_path):
    store, negotiation = _setup(tmp_path)
    cron = FakeCron()
    runtime = MeetingResponsibilityRuntime(
        store=store, cron=cron, followup_interval_minutes=1
    )
    runtime.run(negotiation["negotiation_id"])
    item = runtime.ensure(negotiation["negotiation_id"])
    timer_id = _timer_id(cron)
    timer_job_id = cron.created[-1]["id"]

    reply = submit_negotiation_reply(
        {
            "negotiation_id": negotiation["negotiation_id"],
            "participant_user_id": "attendee_a",
            "message_id": "reply_1",
            "reply_text": "I can do tomorrow",
            "intent": "propose_slots",
            "start_time": "2026-10-06T01:00:00Z",
            "end_time": "2026-10-06T01:30:00Z",
            "timezone": "UTC",
        },
        store=store,
        cron=cron,
    )
    assert reply["responsibility_wake"]["accepted"] is True
    assert TimerOccurrenceStore(store.path).get(timer_id).state == CANCELLED
    assert timer_job_id in cron.deleted
    current = runtime.responsibilities.get(item.responsibility_id)
    assert current.lifecycle_state in {WAIT_EXTERNAL, "TERMINAL"}


def test_successful_finalization_terminalizes_responsibility_and_cancels_timer(tmp_path):
    store, negotiation = _setup(tmp_path)
    cron = FakeCron()
    runtime = MeetingResponsibilityRuntime(
        store=store, cron=cron, followup_interval_minutes=1
    )
    runtime.run(negotiation["negotiation_id"])
    item = runtime.ensure(negotiation["negotiation_id"])

    proposed = submit_negotiation_reply(
        {
            "negotiation_id": negotiation["negotiation_id"],
            "participant_user_id": "attendee_a",
            "message_id": "proposal_1",
            "intent": "propose_slots",
            "proposed_slot": {
                "start_time": "2026-10-06T01:00:00Z",
                "end_time": "2026-10-06T01:30:00Z",
                "timezone": "UTC",
            },
        },
        store=store,
        cron=cron,
    )
    slot_id = proposed["slot"]["slot_id"]
    submit_negotiation_reply(
        {
            "negotiation_id": negotiation["negotiation_id"],
            "participant_user_id": "attendee_a",
            "message_id": "consent_1",
            "intent": "vote_yes",
            "slot_id": slot_id,
        },
        store=store,
        cron=cron,
    )
    calendar = FakeCalendar()
    result = finalize_negotiation_case(
        {
            "negotiation_id": negotiation["negotiation_id"],
            "selected_slot_id": slot_id,
            "decision_source": "consent",
            "requested_by_user_id": "requester",
            "requester_confirmation": True,
        },
        store=store,
        calendar_client=calendar,
        cron=cron,
    )

    assert result["calendar_update_called"] is True
    assert store.get_negotiation(negotiation["negotiation_id"])["status"] == "consented"
    current = runtime.responsibilities.get(item.responsibility_id)
    assert current.lifecycle_state == "TERMINAL"
    assert runtime.responsibilities.pending_waits(item.responsibility_id) == []
    assert all(job["id"] in cron.deleted for job in cron.created)


def test_stale_claim_guard_blocks_effect_admission_before_send(tmp_path):
    store, negotiation = _setup(tmp_path)
    cron = FakeCron()
    feishu = FakeFeishu()
    runtime = MeetingResponsibilityRuntime(
        store=store, cron=cron, feishu_client=feishu, followup_interval_minutes=0
    )
    runtime.run(negotiation["negotiation_id"])
    timer_id = _timer_id(cron)
    sent_before_stale_attempt = len(feishu.sent)

    def stale_claim_in_transaction(_conn):
        raise RuntimeError("responsibility claim is stale")

    with pytest.raises(RuntimeError, match="responsibility claim is stale"):
        _run_negotiation_followup_business(
            {
                "negotiation_id": negotiation["negotiation_id"],
                "timer_id": timer_id,
                "responsibility_managed": True,
                "followup_interval_minutes": 0,
                "max_followups": 1,
                "owner": "responsibility:test:1",
            },
            store=store,
            cron=None,
            feishu_client=feishu,
            claim_guard=lambda: None,
            transaction_claim_guard=stale_claim_in_transaction,
        )

    assert len(feishu.sent) == sent_before_stale_attempt
    with sqlite3.connect(store.path) as conn:
        table = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='semantier_effect_outbox'"
        ).fetchone()
        if table is not None:
            count = conn.execute("SELECT COUNT(*) FROM semantier_effect_outbox").fetchone()[0]
            assert count == 0


def test_timer_arm_failure_leaves_durable_wait_and_repair_reuses_same_occurrence(tmp_path):
    store, negotiation = _setup(tmp_path)
    cron = FakeCron()
    cron.fail_ensure = True
    runtime = MeetingResponsibilityRuntime(
        store=store, cron=cron, followup_interval_minutes=1
    )

    result = runtime.run(negotiation["negotiation_id"])
    item = runtime.ensure(negotiation["negotiation_id"])
    assert result.disposition == WAIT_EXTERNAL
    waits = runtime.responsibilities.pending_waits(item.responsibility_id)
    timer_wait = next(wait for wait in waits if wait.kind == TIMER)
    occurrence = runtime.timer_store.get(timer_wait.source_ref)
    assert occurrence is not None
    assert occurrence.state == "SCHEDULED"
    assert occurrence.provider_ref is None
    assert store.get_negotiation(negotiation["negotiation_id"])["followup_cron_status"] == "repair_required"

    cron.fail_ensure = False
    runtime._arm_pending_timers(item.responsibility_id)
    repaired = runtime.timer_store.get(timer_wait.source_ref)
    assert repaired is not None
    assert repaired.timer_id == occurrence.timer_id
    assert repaired.provider_ref == cron.created[-1]["id"]
    assert store.get_negotiation(negotiation["negotiation_id"])["followup_cron_status"] == "active"


def test_duplicate_timer_signal_is_noop_after_first_acceptance(tmp_path):
    store, negotiation = _setup(tmp_path)
    cron = FakeCron()
    feishu = FakeFeishu()
    runtime = MeetingResponsibilityRuntime(
        store=store, cron=cron, feishu_client=feishu, followup_interval_minutes=1
    )
    runtime.run(negotiation["negotiation_id"])
    timer_id = _timer_id(cron)

    first = negotiation_followup_cron_tick(
        {"negotiation_id": negotiation["negotiation_id"], "timer_id": timer_id},
        store=store,
        cron=cron,
        feishu_client=feishu,
    )
    sent_after_first = len(feishu.sent)
    second = negotiation_followup_cron_tick(
        {"negotiation_id": negotiation["negotiation_id"], "timer_id": timer_id},
        store=store,
        cron=cron,
        feishu_client=feishu,
    )

    assert first["wake_accepted"] is True
    assert second["wake_accepted"] is False
    assert len(feishu.sent) == sent_after_first
    assert TimerOccurrenceStore(store.path).get(timer_id).state == ACCEPTED


def test_known_frontier_does_not_rearm_immaterial_followups(tmp_path):
    store, case = _setup(tmp_path)
    slot = store.add_candidate_slot(case['negotiation_id'], proposed_by_user_id='attendee_a', round_number=1,
        start_time='2026-10-06T01:00:00Z', end_time='2026-10-06T01:30:00Z', timezone_name='UTC', source_text=None)
    store.update_attendee_statuses(case['monitor_id'], [{'user_id': 'attendee_a', 'response_status': 'declined'}])
    store.transition_negotiation_state(case['negotiation_id'], expected_state='pending_decliner_input',
        next_state='collecting_votes', patch={'current_round': 1}, actor_id='test')
    cron, feishu = FakeCron(), FakeFeishu()
    runtime = MeetingResponsibilityRuntime(store=store, cron=cron, feishu_client=feishu)
    runtime.run(case['negotiation_id'])
    item = runtime.ensure(case['negotiation_id'])
    assert {wait.kind for wait in runtime.responsibilities.pending_waits(item.responsibility_id)} == {EVENT}
    assert cron.created == []
    frontier = store.latest_decision_frontier(case['negotiation_id'])
    assert frontier['decision_frontier'][0]['slot_id'] == slot['slot_id']
    assert frontier['sufficient_progress_disposition'] == 'PRESENT_FRONTIER'
