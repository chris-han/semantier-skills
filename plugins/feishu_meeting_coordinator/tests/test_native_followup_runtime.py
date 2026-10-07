from __future__ import annotations

# ruff: noqa: E402

import hashlib
import json
import os
import subprocess
import sys

import pytest
from pathlib import Path

import agents

_REPO_ROOT = Path(__file__).resolve().parents[4]
_AUDIT_AGENTS = _REPO_ROOT / ".worktrees" / "hermes-upstream-audit" / "src" / "agents"
if str(_AUDIT_AGENTS) not in agents.__path__:
    agents.__path__.insert(0, str(_AUDIT_AGENTS))

from agents.effect_outbox import AtomicEffectOutbox, COMPLETED, EFFECT_UNKNOWN, READY
from agents.internal_continuation import ContinuationAdmissionStore, PENDING
from agents.timer_occurrence import ACCEPTED, TimerOccurrenceStore
from feishu_meeting_coordinator.gateway import (
    _dispatch_native_followup_effect,
    ensure_negotiation_followup_cron,
    negotiation_followup_cron_tick,
    submit_negotiation_reply,
)
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
        "captured_at": "2026-09-21T00:00:00Z",
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
        "start_time": "2026-09-22T01:00:00Z",
        "end_time": "2026-09-22T01:30:00Z",
        "timezone": "Asia/Shanghai",
        "session_id": "sess_1",
        "attendees": [
            {
                "user_id": "ou_a",
                "message_user_id": "ou_a",
                "display_name": "Amy",
            },
        ],
    }


class FakeCron:
    def __init__(self):
        self.jobs: dict[str, dict] = {}
        self.created: list[dict] = []
        self.deleted: list[str] = []

    def ensure_job(self, **kwargs) -> str:
        job_id = f"job_{len(self.created) + 1}"
        record = {
            "id": job_id,
            "name": kwargs["name"],
            "schedule": {
                "kind": "once",
                "run_at": kwargs["schedule"],
                "display": f"once at {kwargs['schedule']}",
            },
            "schedule_display": kwargs["schedule"],
            "repeat": kwargs["repeat"],
            "no_agent": kwargs["no_agent"],
            "script": kwargs["script"],
            "enabled": True,
        }
        self.created.append(record)
        self.jobs[job_id] = record
        return job_id

    def get_job(self, job_id: str):
        return self.jobs.get(job_id)

    def job_exists(self, job_id: str) -> bool:
        return job_id in self.jobs

    def delete_job(self, job_id: str) -> bool:
        existed = job_id in self.jobs
        self.jobs.pop(job_id, None)
        self.deleted.append(job_id)
        return existed


class CrashAfterAcceptFeishu:
    def __init__(self):
        self.calls: list[dict] = []
        self.messages: dict[str, dict] = {}
        self._crashed_keys: set[str] = set()

    def get_attendee_response_statuses(self, *, calendar_id: str, event_id: str):
        return []

    def send_attendee_message(
        self,
        *,
        attendee_open_ids: list[str],
        message: str,
        idempotency_key: str | None = None,
    ):
        target = attendee_open_ids[0]
        seed = idempotency_key or f"legacy:{len(self.calls) + 1}"
        message_id = "om_" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]
        self.calls.append(
            {
                "target": target,
                "message": message,
                "idempotency_key": idempotency_key,
                "message_id": message_id,
            }
        )
        self.messages[message_id] = {
            "message_id": message_id,
            "deleted": False,
        }
        if idempotency_key and idempotency_key not in self._crashed_keys:
            self._crashed_keys.add(idempotency_key)
            raise RuntimeError("synthetic_crash_after_provider_accept")
        return {
            "delivered": [target],
            "failed": [],
            "message_id": message_id,
            "message_ids": {target: message_id},
        }

    def get_message(self, *, message_id: str):
        message = self.messages.get(message_id)
        return {
            "message_id": message_id,
            "found": message is not None,
            "message": message,
            "items": [message] if message is not None else [],
        }


class FakeFeishu:
    def __init__(self):
        self.calls: list[dict] = []
        self.messages: dict[str, dict] = {}

    def get_attendee_response_statuses(self, *, calendar_id: str, event_id: str):
        return []

    def send_attendee_message(
        self,
        *,
        attendee_open_ids: list[str],
        message: str,
        idempotency_key: str | None = None,
    ):
        target = attendee_open_ids[0]
        seed = idempotency_key or f"legacy:{len(self.calls) + 1}"
        message_id = "om_" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]
        self.calls.append(
            {
                "target": target,
                "message": message,
                "idempotency_key": idempotency_key,
                "message_id": message_id,
            }
        )
        self.messages[message_id] = {
            "message_id": message_id,
            "deleted": False,
        }
        return {
            "delivered": [target],
            "failed": [],
            "message_id": message_id,
            "message_ids": {target: message_id},
        }

    def get_message(self, *, message_id: str):
        message = self.messages.get(message_id)
        return {
            "message_id": message_id,
            "found": message is not None,
            "message": message,
            "items": [message] if message is not None else [],
        }


def _setup(tmp_path):
    store = MeetingCoordinatorStore(tmp_path / "state.db")
    monitor = store.start_monitor(_monitor_payload())
    negotiation = store.create_or_get_negotiation_case(
        monitor_id=monitor["monitor_id"],
        event_revision_id=monitor["event_revision_id"],
        trigger_attendee_user_id="ou_a",
        session_id="sess_1",
    )
    return store, negotiation


def _timer_id_from_job(job: dict) -> str:
    return str(job["name"]).split("::", 1)[1]


def test_production_followup_uses_one_shot_native_primitives_and_stops_at_max(tmp_path):
    store, negotiation = _setup(tmp_path)
    store.update_workspace_settings("ws_1", max_followups=2)
    cron = FakeCron()
    feishu = FakeFeishu()

    first = ensure_negotiation_followup_cron(
        negotiation_id=negotiation["negotiation_id"],
        store=store,
        cron=cron,
        schedule="every 2m",
    )

    assert len(cron.created) == 1
    first_job = cron.created[0]
    assert first_job["schedule"]["kind"] == "once"
    assert first_job["repeat"] == 1
    assert first_job["no_agent"] is True
    assert first_job["script"].endswith(".py")
    first_timer_id = _timer_id_from_job(first_job)
    assert first["next_followup_at"] == first_job["schedule"]["run_at"]

    first_tick = negotiation_followup_cron_tick(
        {
            "negotiation_id": negotiation["negotiation_id"],
            "timer_id": first_timer_id,
            "followup_interval_minutes": 1,
        },
        store=store,
        cron=cron,
        feishu_client=feishu,
    )

    participant = next(
        item
        for item in store.list_negotiation_participants(negotiation["negotiation_id"])
        if item["attendee_user_id"] == "ou_a"
    )
    assert participant["followup_count"] == 1
    assert first_tick["wake_accepted"] is True
    assert "followups_sent" not in first_tick

    first_timer = TimerOccurrenceStore(store.path).get(first_timer_id)
    assert first_timer is not None
    assert first_timer.state == ACCEPTED

    # The reminder send must be the provider call carrying a durable idempotency key.
    native_calls = [call for call in feishu.calls if call["idempotency_key"]]
    assert len(native_calls) == 1

    outbox = AtomicEffectOutbox(store.path)
    with store._connect() as conn:
        effects = conn.execute(
            """
            SELECT effect_id FROM semantier_effect_outbox
            WHERE workflow_id=? AND effect_type=?
            """,
            (
                negotiation["negotiation_id"],
                "FOLLOWUP_REMINDER:ou_a",
            ),
        ).fetchall()
    assert len(effects) == 1
    effect = outbox.get(str(effects[0]["effect_id"]))
    assert effect is not None
    assert effect.state == COMPLETED

    # One unresolved participant remains below max, so exactly one new one-shot exists.
    assert len(cron.created) == 2
    second_job = cron.created[1]
    second_timer_id = _timer_id_from_job(second_job)
    assert second_timer_id != first_timer_id
    assert second_job["repeat"] == 1

    calls_before_duplicate = len(feishu.calls)
    jobs_before_duplicate = len(cron.created)
    duplicate = negotiation_followup_cron_tick(
        {
            "negotiation_id": negotiation["negotiation_id"],
            "timer_id": first_timer_id,
        },
        store=store,
        cron=cron,
        feishu_client=feishu,
    )
    assert duplicate["wake_accepted"] is False
    assert duplicate["wake_reason"] in {"duplicate", "no_matching_wait"}
    assert len(feishu.calls) == calls_before_duplicate
    assert len(cron.created) == jobs_before_duplicate

    second_tick = negotiation_followup_cron_tick(
        {
            "negotiation_id": negotiation["negotiation_id"],
            "timer_id": second_timer_id,
            "followup_interval_minutes": 0,
        },
        store=store,
        cron=cron,
        feishu_client=feishu,
    )

    participant = next(
        item
        for item in store.list_negotiation_participants(negotiation["negotiation_id"])
        if item["attendee_user_id"] == "ou_a"
    )
    assert participant["followup_count"] == 2
    assert second_tick["wake_accepted"] is True
    assert "followups_sent" not in second_tick
    post_second = store.get_negotiation(negotiation["negotiation_id"])
    assert post_second["followup_cron_status"] == "paused"
    assert post_second["next_followup_at"] is None
    assert len(cron.created) == 2


def test_legacy_recurring_tick_migrates_without_running_reminder_body(tmp_path):
    store, negotiation = _setup(tmp_path)
    cron = FakeCron()
    feishu = FakeFeishu()

    # Simulate a pre-migration recurring job already recorded on the negotiation.
    cron.jobs["legacy"] = {
        "id": "legacy",
        "name": f"meeting-time-negotiator-followup:{negotiation['negotiation_id']}",
        "schedule": {"kind": "interval", "minutes": 2},
        "schedule_display": "every 2m",
        "repeat": {"limit": None, "completed": 0},
        "enabled": True,
    }
    store.set_negotiation_followup_cron_metadata(
        negotiation["negotiation_id"],
        followup_cron_job_id="legacy",
        followup_cron_status="active",
    )

    result = negotiation_followup_cron_tick(
        {"negotiation_id": negotiation["negotiation_id"]},
        store=store,
        cron=cron,
        feishu_client=feishu,
    )

    assert result["migrated_legacy_cron"] is True
    assert "legacy" in cron.deleted
    assert len(cron.created) == 1
    assert cron.created[0]["schedule"]["kind"] == "once"
    assert cron.created[0]["repeat"] == 1
    assert feishu.calls == []




@pytest.mark.parametrize("age", [60, 3599, 3600, 3601, 86400, None])
def test_uncertain_provider_send_remains_unknown_without_duplicate_domain_apply(tmp_path, age):
    store, negotiation = _setup(tmp_path)
    store.update_workspace_settings("ws_1", max_followups=1)
    cron = FakeCron()
    feishu = CrashAfterAcceptFeishu()

    ensure_negotiation_followup_cron(
        negotiation_id=negotiation["negotiation_id"],
        store=store,
        cron=cron,
        schedule="every 2m",
    )
    timer_id = _timer_id_from_job(cron.created[0])

    result = negotiation_followup_cron_tick(
        {
            "negotiation_id": negotiation["negotiation_id"],
            "timer_id": timer_id,
            "followup_interval_minutes": 0,
        },
        store=store,
        cron=cron,
        feishu_client=feishu,
    )

    participant = next(
        item
        for item in store.list_negotiation_participants(negotiation["negotiation_id"])
        if item["attendee_user_id"] == "ou_a"
    )
    assert participant["followup_count"] == 0
    assert result["wake_accepted"] is True
    native_calls = [call for call in feishu.calls if call["idempotency_key"]]
    assert len(native_calls) == 1
    with store._connect() as conn:
        row = conn.execute(
            "SELECT effect_id FROM semantier_effect_outbox WHERE workflow_id=? AND effect_type=?",
            (negotiation["negotiation_id"], "FOLLOWUP_REMINDER:ou_a"),
        ).fetchone()
    outbox = AtomicEffectOutbox(store.path)
    original = outbox.get(row["effect_id"])
    payload = json.loads(original.canonical_payload)
    reserved = store.get_native_followup_message(
        negotiation_id=negotiation["negotiation_id"], attendee_user_id="ou_a", semantic_round=1,
    )
    item = dict(payload, effect_id=original.effect_id, attendee_user_id="ou_a",
                message_event_id=reserved["message_event_id"])

    # If called outside the finite dedupe window, this fake creates a duplicate.
    def expired_send(**kwargs):
        feishu.calls.append(kwargs)
        if age is None or age >= 3600:
            feishu.messages["duplicate"] = kwargs
        return {"delivered": ["ou_a"], "message_id": "duplicate"}
    feishu.send_attendee_message = expired_send
    for recovery_store in [store, MeetingCoordinatorStore(store.path)]:
        for _ in range(2):
            recovered = _dispatch_native_followup_effect(
                negotiation_id=negotiation["negotiation_id"], store=recovery_store,
                client=feishu, item=item,
            )
            assert recovered["state"] == EFFECT_UNKNOWN
            assert recovered["applied"] is False
    from concurrent.futures import ThreadPoolExecutor
    def recover(_):
        return _dispatch_native_followup_effect(
            negotiation_id=negotiation["negotiation_id"], store=MeetingCoordinatorStore(store.path),
            client=feishu, item=item,
        )
    with ThreadPoolExecutor(max_workers=4) as pool:
        concurrent = list(pool.map(recover, range(8)))
    assert all(r["state"] == EFFECT_UNKNOWN and r["applied"] is False for r in concurrent)
    assert len(feishu.calls) == 1
    assert "duplicate" not in feishu.messages
    assert outbox.get(original.effect_id) == original

    script = """
import json, sys
from feishu_meeting_coordinator.gateway import _dispatch_native_followup_effect
from feishu_meeting_coordinator.store import MeetingCoordinatorStore
class ReadOnlyGuard:
    calls = []
    def send_attendee_message(self, **kwargs):
        self.calls.append("send")
        raise AssertionError('fresh process attempted send')
    def get_message(self, **kwargs):
        self.calls.append("get")
        raise AssertionError('missing correlation attempted lookup')
print(json.dumps(_dispatch_native_followup_effect(
    negotiation_id=sys.argv[2], store=MeetingCoordinatorStore(sys.argv[1]),
    client=ReadOnlyGuard(), item=json.loads(sys.argv[3]))))
assert ReadOnlyGuard.calls == []
"""
    process = subprocess.run(
        [sys.executable, "-c", script, str(store.path), negotiation["negotiation_id"], json.dumps(item)],
        capture_output=True, text=True, check=True, env=os.environ.copy(),
    )
    assert json.loads(process.stdout)["state"] == EFFECT_UNKNOWN
    assert json.loads(process.stdout)["applied"] is False
    assert outbox.get(original.effect_id) == original

    # Independent provider correlation permits GET-only completion, once.
    outbox.pin_provider_correlation(effect_id=original.effect_id,
                                    correlation_ref=native_calls[0]["message_id"])
    for _ in range(2):
        recovered = _dispatch_native_followup_effect(
            negotiation_id=negotiation["negotiation_id"], store=store, client=feishu, item=item,
        )
        assert recovered["state"] == COMPLETED
    assert len(feishu.calls) == 1
    participant = next(p for p in store.list_negotiation_participants(negotiation["negotiation_id"]) if p["attendee_user_id"] == "ou_a")
    assert participant["followup_count"] == 1


def test_ambiguous_reply_admits_one_durable_internal_continuation(tmp_path):
    store, negotiation = _setup(tmp_path)

    payload = {
        "negotiation_id": negotiation["negotiation_id"],
        "participant_user_id": "ou_a",
        "message_id": "om_vague_1",
        "reply_text": "maybe sometime tomorrow",
        "intent": "propose_slots",
    }

    first = submit_negotiation_reply(payload, store=store)
    second = submit_negotiation_reply(payload, store=store)

    assert first["accepted"] is True
    assert first["clarification_required"] is True
    assert first["reason"] == "missing_normalized_slot"
    assert first["continuation_admitted"] is True
    assert first["continuation_scheduled"] is False

    assert second["accepted"] is True
    assert second["clarification_required"] is True
    assert second["continuation_admitted"] is False
    assert second["continuation_reason"] == "duplicate_or_terminal"

    continuations = ContinuationAdmissionStore(store.path).pending()
    assert len(continuations) == 1
    continuation = continuations[0]
    assert continuation.state == PENDING
    assert continuation.workspace_id == "ws_1"
    assert continuation.workflow_id == negotiation["negotiation_id"]
    assert continuation.session_key == "key_1"

    with store._connect() as conn:
        inbound_count = conn.execute(
            """
            SELECT COUNT(*) FROM meeting_time_negotiation_messages
            WHERE negotiation_id=? AND direction='inbound' AND message_id=?
            """,
            (negotiation["negotiation_id"], "om_vague_1"),
        ).fetchone()[0]
        clarification_events = conn.execute(
            """
            SELECT COUNT(*) FROM semantier_durable_events
            WHERE workflow_type='meeting_negotiation'
              AND workflow_id=?
              AND event_type='AMBIGUOUS_AVAILABILITY'
            """,
            (negotiation["negotiation_id"],),
        ).fetchone()[0]
    assert inbound_count == 1
    assert clarification_events == 1


@pytest.mark.parametrize("evidence, expected", [
    ({"found": False}, EFFECT_UNKNOWN),
    ({"found": False, "confirmed_not_applied": True}, READY),
    ({"found": True, "message": {"deleted": True}}, COMPLETED),
    ({}, EFFECT_UNKNOWN),
])
def test_known_correlation_gateway_reads_only(tmp_path, evidence, expected):
    store, negotiation = _setup(tmp_path)
    payload = {"target_id": "ou_a", "message": "reminder"}
    with store._connect() as conn:
        reserved = store.reserve_native_followup_effect(
            conn, negotiation_id=negotiation["negotiation_id"], attendee_user_id="ou_a",
            target_id="ou_a", message="reminder", semantic_round=1,
        )
        effect = AtomicEffectOutbox.enqueue_ready(
            conn, workflow_id=negotiation["negotiation_id"], effect_type="FOLLOWUP_REMINDER:ou_a",
            semantic_round=1, canonical_payload=json.dumps(payload).encode(),
        )
    outbox = AtomicEffectOutbox(store.path)
    assert outbox.claim_dispatch(effect_id=effect.effect_id, attempt_id="accepted")
    outbox.pin_provider_correlation(effect_id=effect.effect_id, correlation_ref="om_known")
    outbox.mark_effect_unknown(effect_id=effect.effect_id, attempt_id="accepted", failure_detail="lost_response")
    class Provider:
        sends = 0
        gets = []
        def send_attendee_message(self, **kwargs):
            self.sends += 1
            raise AssertionError("reconciliation must not send")
        def get_message(self, *, message_id):
            self.gets.append(message_id)
            return evidence
    client = Provider()
    item = dict(payload, effect_id=effect.effect_id, attendee_user_id="ou_a",
                message_event_id=reserved["message"]["message_event_id"])
    result = _dispatch_native_followup_effect(
        negotiation_id=negotiation["negotiation_id"], store=store, client=client, item=item,
    )
    assert result["state"] == expected
    assert result["applied"] is (expected == COMPLETED)
    assert client.sends == 0
    assert client.gets == ["om_known"]
