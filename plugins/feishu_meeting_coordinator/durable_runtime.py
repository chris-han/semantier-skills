from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from agents.durable_responsibility import (
    EVENT,
    TERMINAL,
    TIMER,
    WAIT_EXTERNAL,
    ContinuationDecision,
    DurableResponsibilityDispatcher,
    DurableResponsibilityStore,
    WaitSpec,
    WakeResult,
)
from agents.timer_occurrence import SCHEDULED, TimerOccurrenceStore

RESPONSIBILITY_KIND = "feishu_meeting_negotiation"
WORKFLOW_ID = "feishu-meeting-coordinator"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _reply_source(negotiation_id: str) -> str:
    return f"feishu:negotiation:{negotiation_id}:reply"


@dataclass
class MeetingTimerProvider:
    negotiation_id: str
    cron: Any

    def arm(self, *, timer_id: str, scheduled_at: str) -> str | None:
        from .gateway import _followup_provider_job_name, _followup_script_name

        return self.cron.ensure_job(
            name=_followup_provider_job_name(self.negotiation_id, timer_id),
            schedule=scheduled_at,
            profile="meeting-coordinator",
            prompt=f"Timer signal only for {self.negotiation_id} / {timer_id}.",
            skills=["feishu_meeting_coordinator"],
            deliver="local",
            repeat=1,
            no_agent=True,
            script=_followup_script_name(self.negotiation_id),
        )


class MeetingContinuationHandler:
    def __init__(
        self,
        *,
        store: Any,
        responsibility_store: DurableResponsibilityStore,
        cron: Any | None,
        feishu_client: Any | None = None,
        kanban: Any | None = None,
        followup_interval_minutes: int = 2,
    ) -> None:
        self.store = store
        self.responsibility_store = responsibility_store
        self.cron = cron
        self.feishu_client = feishu_client
        self.kanban = kanban
        self.followup_interval_minutes = max(0, int(followup_interval_minutes))

    def _latest_wake(self, responsibility_id: str) -> dict[str, Any] | None:
        for event in reversed(self.responsibility_store.events(responsibility_id)):
            if event["event_type"] == "WAKE_ACCEPTED":
                return dict(event["payload"])
        return None

    def __call__(self, record, checkpoint, claim) -> ContinuationDecision:
        from . import gateway

        self.responsibility_store.assert_claim(claim)
        negotiation_id = record.domain_ref
        negotiation = self.store.get_negotiation(negotiation_id)
        if gateway._negotiation_is_terminal(negotiation):
            return ContinuationDecision(disposition=TERMINAL)

        wake = self._latest_wake(record.responsibility_id)
        if wake and wake.get("kind") == TIMER:
            timer_id = str(wake.get("source_ref") or "")
            gateway._run_negotiation_followup_business(
                {
                    "negotiation_id": negotiation_id,
                    "timer_id": timer_id,
                    "responsibility_managed": True,
                    "followup_interval_minutes": self.followup_interval_minutes,
                    "owner": (
                        f"responsibility:{record.responsibility_id}:"
                        f"{claim.lease_epoch}"
                    ),
                },
                store=self.store,
                cron=self.cron,
                kanban=self.kanban,
                feishu_client=self.feishu_client,
                claim_guard=lambda: self.responsibility_store.assert_claim(claim),
                transaction_claim_guard=lambda conn: self.responsibility_store.assert_claim(
                    claim, conn=conn
                ),
            )
        else:
            send_message = None
            if self.feishu_client is not None:
                def _send_message(
                    attendee_open_ids: list[str], message: str
                ) -> str | None:
                    result = self.feishu_client.send_attendee_message(
                        attendee_open_ids=attendee_open_ids,
                        message=message,
                    )
                    if isinstance(result, dict) and result.get("message_id"):
                        return str(result["message_id"])
                    return None

                send_message = _send_message
            gateway.negotiation_case_tick(
                {"negotiation_id": negotiation_id},
                store=self.store,
                cron=None,
                kanban=self.kanban,
                send_message=send_message,
                lock_owner=(
                    f"responsibility:{record.responsibility_id}:"
                    f"{claim.lease_epoch}"
                ),
            )

        self.responsibility_store.assert_claim(claim)
        negotiation = self.store.get_negotiation(negotiation_id)
        if gateway._negotiation_is_terminal(negotiation):
            return ContinuationDecision(disposition=TERMINAL)

        event_wait = WaitSpec(
            kind=EVENT,
            source_ref=_reply_source(negotiation_id),
            correlation_key=negotiation_id,
        )
        max_followups = int(
            self.store.get_workspace_state(str(negotiation["workspace_id"])).get(
                "max_followups"
            )
            or 3
        )
        material_targets = gateway._material_followup_targets(negotiation_id, self.store)
        timer_needed = any(
            (material_targets is None or str(participant['attendee_user_id']) in material_targets)
            and gateway._followup_reminder_needed(participant)
            and int(participant.get("followup_count") or 0) < max_followups
            for participant in self.store.list_negotiation_participants(negotiation_id)
        )
        if not timer_needed:
            self.store.set_negotiation_followup_cron_metadata(
                negotiation_id,
                followup_cron_job_id=None,
                followup_cron_status="paused",
                next_followup_at=None,
            )
            return ContinuationDecision(
                disposition=WAIT_EXTERNAL,
                waits=(event_wait,),
                session_ref=str(negotiation.get("session_id") or "") or None,
            )

        scheduled_at = _iso(
            _utc_now() + timedelta(minutes=self.followup_interval_minutes)
        )
        timer = gateway._register_followup_timer(
            negotiation_id=negotiation_id,
            store=self.store,
            scheduled_at=scheduled_at,
        )
        return ContinuationDecision(
            disposition=WAIT_EXTERNAL,
            waits=(
                event_wait,
                WaitSpec(
                    kind=TIMER,
                    source_ref=timer.timer_id,
                    correlation_key=negotiation_id,
                    deadline_at=timer.scheduled_at,
                ),
            ),
            session_ref=str(negotiation.get("session_id") or "") or None,
        )


class MeetingResponsibilityRuntime:
    def __init__(
        self,
        *,
        store: Any,
        cron: Any | None,
        feishu_client: Any | None = None,
        kanban: Any | None = None,
        followup_interval_minutes: int = 2,
        owner_id: str = "meeting-responsibility-worker",
    ) -> None:
        self.store = store
        self.cron = cron
        self.feishu_client = feishu_client
        self.kanban = kanban
        self.responsibilities = DurableResponsibilityStore(store.path)
        self.timer_store = TimerOccurrenceStore(store.path)
        self.handler = MeetingContinuationHandler(
            store=store,
            responsibility_store=self.responsibilities,
            cron=cron,
            feishu_client=feishu_client,
            kanban=kanban,
            followup_interval_minutes=followup_interval_minutes,
        )
        self.dispatcher = DurableResponsibilityDispatcher(
            self.responsibilities,
            handlers={RESPONSIBILITY_KIND: self.handler},
            owner_id=owner_id,
        )

    def ensure(self, negotiation_id: str):
        negotiation = self.store.get_negotiation(negotiation_id)
        record = self.responsibilities.ensure(
            responsibility_kind=RESPONSIBILITY_KIND,
            workspace_id=str(negotiation["workspace_id"]),
            domain_ref=negotiation_id,
            workflow_id=WORKFLOW_ID,
            workflow_instance_id=negotiation_id,
            session_ref=str(negotiation.get("session_id") or "") or None,
        )
        self.responsibilities.bind_execution(record.responsibility_id)
        return record

    def existing(self, negotiation_id: str):
        negotiation = self.store.get_negotiation(negotiation_id)
        responsibility_id = self.responsibilities.derive_id(
            responsibility_kind=RESPONSIBILITY_KIND,
            workspace_id=str(negotiation["workspace_id"]),
            domain_ref=negotiation_id,
            workflow_id=WORKFLOW_ID,
            workflow_instance_id=negotiation_id,
        )
        return self.responsibilities.get(responsibility_id)

    def _arm_pending_timers(self, responsibility_id: str) -> None:
        if self.cron is None:
            return
        item = self.responsibilities.get(responsibility_id)
        if item is None:
            raise KeyError(responsibility_id)
        for wait in self.responsibilities.pending_waits(responsibility_id):
            if wait.kind != TIMER:
                continue
            occurrence = self.timer_store.get(wait.source_ref)
            if occurrence is None or occurrence.state != SCHEDULED:
                continue
            if occurrence.provider_ref:
                continue
            provider = MeetingTimerProvider(
                negotiation_id=item.domain_ref,
                cron=self.cron,
            )
            try:
                armed = self.timer_store.arm(
                    timer_id=occurrence.timer_id,
                    provider=provider,
                )
            except Exception as exc:
                self.store.set_negotiation_followup_cron_metadata(
                    item.domain_ref,
                    followup_cron_job_id=None,
                    followup_cron_status="repair_required",
                    next_followup_at=occurrence.scheduled_at,
                )
                self.store.record_negotiation_event(
                    negotiation_id=item.domain_ref,
                    event_type="FOLLOWUP_TIMER_ARM_DEFERRED",
                    actor_type="system",
                    actor_id="durable-responsibility-runtime",
                    payload={
                        "timer_id": occurrence.timer_id,
                        "scheduled_at": occurrence.scheduled_at,
                        "error_type": type(exc).__name__,
                    },
                )
                continue
            self.store.set_negotiation_followup_cron_metadata(
                item.domain_ref,
                followup_cron_job_id=armed.provider_ref,
                followup_cron_status="active",
                next_followup_at=armed.scheduled_at,
            )

    def _record_waiting(self, *, negotiation_id: str, responsibility_id: str) -> None:
        current = self.responsibilities.get(responsibility_id)
        if current is None or current.lifecycle_state not in {
            WAIT_EXTERNAL,
            "WAIT_TIMER",
            "REQUIRE_USER",
            "RECONCILE",
        }:
            return
        waits = self.responsibilities.pending_waits(responsibility_id)
        self.store.record_negotiation_event(
            negotiation_id=negotiation_id,
            event_type="RESPONSIBILITY_WAITING",
            actor_type="system",
            actor_id="durable-responsibility-runtime",
            payload={
                "responsibility_id": responsibility_id,
                "checkpoint_version": current.checkpoint_version,
                "waits": [
                    {
                        "wait_id": wait.wait_id,
                        "kind": wait.kind,
                        "source_ref": wait.source_ref,
                        "correlation_key": wait.correlation_key,
                        "deadline_at": wait.deadline_at,
                    }
                    for wait in waits
                ],
            },
        )

    def _record_wake(
        self,
        *,
        negotiation_id: str,
        responsibility_id: str,
        kind: str,
        source_ref: str,
        wake_id: str | None,
    ) -> None:
        self.store.record_negotiation_event(
            negotiation_id=negotiation_id,
            event_type="RESPONSIBILITY_WAKE_ACCEPTED",
            actor_type="system",
            actor_id="durable-responsibility-runtime",
            payload={
                "responsibility_id": responsibility_id,
                "wake_kind": kind,
                "wake_source_ref": source_ref,
                "wake_id": wake_id,
            },
        )

    def run(self, negotiation_id: str):
        item = self.ensure(negotiation_id)
        result = self.dispatcher.run_one(
            responsibility_id=item.responsibility_id,
        )
        self._arm_pending_timers(item.responsibility_id)
        self._record_waiting(
            negotiation_id=negotiation_id,
            responsibility_id=item.responsibility_id,
        )
        return result

    def wake_reply(self, *, negotiation_id: str, message_id: str):
        item = self.existing(negotiation_id)
        if item is None:
            return WakeResult(False, "responsibility_missing")
        pending_before = list(self.responsibilities.pending_waits(item.responsibility_id))
        result = self.responsibilities.accept_wake(
            responsibility_id=item.responsibility_id,
            kind=EVENT,
            source_ref=_reply_source(negotiation_id),
            correlation_key=negotiation_id,
            dedupe_key=f"feishu-reply:{message_id}",
            expected_checkpoint_version=item.checkpoint_version,
        )
        if not result.accepted:
            return result
        self._record_wake(
            negotiation_id=negotiation_id,
            responsibility_id=item.responsibility_id,
            kind=EVENT,
            source_ref=_reply_source(negotiation_id),
            wake_id=result.wake_id,
        )
        for wait in pending_before:
            if wait.kind != TIMER:
                continue
            occurrence = self.timer_store.get(wait.source_ref)
            if occurrence is None or occurrence.state != SCHEDULED:
                continue
            cancelled = self.timer_store.cancel(timer_id=occurrence.timer_id)
            if self.cron is not None and cancelled.provider_ref:
                try:
                    self.cron.delete_job(cancelled.provider_ref)
                except Exception:
                    pass
        self.dispatcher.run_one(responsibility_id=item.responsibility_id)
        self._arm_pending_timers(item.responsibility_id)
        self._record_waiting(
            negotiation_id=negotiation_id,
            responsibility_id=item.responsibility_id,
        )
        return result

    def timer_signal(self, *, negotiation_id: str, timer_id: str):
        item = self.existing(negotiation_id)
        if item is None:
            return WakeResult(False, "responsibility_missing")
        occurrence = self.timer_store.delivery_event(timer_id=timer_id)
        if (
            occurrence.workflow_type != "meeting_negotiation"
            or occurrence.workflow_id != negotiation_id
            or occurrence.purpose != "followup_reminder"
        ):
            raise ValueError("invalid_timer_occurrence")
        if self.cron is not None and occurrence.provider_ref:
            try:
                self.cron.delete_job(occurrence.provider_ref)
            except Exception:
                pass
        result = self.responsibilities.accept_wake(
            responsibility_id=item.responsibility_id,
            kind=TIMER,
            source_ref=timer_id,
            correlation_key=negotiation_id,
            dedupe_key=occurrence.dedupe_key,
            expected_checkpoint_version=item.checkpoint_version,
        )
        if not result.accepted:
            return result
        self._record_wake(
            negotiation_id=negotiation_id,
            responsibility_id=item.responsibility_id,
            kind=TIMER,
            source_ref=timer_id,
            wake_id=result.wake_id,
        )
        self.dispatcher.run_one(responsibility_id=item.responsibility_id)
        self._arm_pending_timers(item.responsibility_id)
        self._record_waiting(
            negotiation_id=negotiation_id,
            responsibility_id=item.responsibility_id,
        )
        return result


def deliver_followup_timer_signal(
    payload: dict[str, Any],
    *,
    store: Any,
    cron: Any | None,
    feishu_client: Any | None = None,
    kanban: Any | None = None,
) -> dict[str, Any]:
    negotiation_id = str(payload.get("negotiation_id") or "").strip()
    timer_id = str(payload.get("timer_id") or "").strip()
    if not negotiation_id:
        raise ValueError("negotiation_id is required")
    if not timer_id:
        # Compatibility-only migration for pre-durable recurring cron jobs.
        # The legacy occurrence may retire its old scheduler record and arm
        # the first exact one-shot timer, but it must not execute reminder
        # business logic itself.
        from .gateway import _run_negotiation_followup_business

        return _run_negotiation_followup_business(
            {"negotiation_id": negotiation_id},
            store=store,
            cron=cron,
            feishu_client=None,
            kanban=kanban,
        )
    runtime = MeetingResponsibilityRuntime(
        store=store,
        cron=cron,
        feishu_client=feishu_client,
        kanban=kanban,
        followup_interval_minutes=(
            int(payload["followup_interval_minutes"])
            if payload.get("followup_interval_minutes") is not None
            else 2
        ),
    )
    wake = runtime.timer_signal(
        negotiation_id=negotiation_id,
        timer_id=timer_id,
    )
    item = runtime.ensure(negotiation_id)
    current = runtime.responsibilities.get(item.responsibility_id)
    return {
        "ok": True,
        "negotiation_id": negotiation_id,
        "timer_id": timer_id,
        "wake_accepted": wake.accepted,
        "wake_reason": wake.reason,
        "responsibility_id": item.responsibility_id,
        "responsibility_state": current.lifecycle_state if current else None,
        "checkpoint_version": current.checkpoint_version if current else None,
    }
