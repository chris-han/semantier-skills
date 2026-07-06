from __future__ import annotations

import importlib.util
import json
import os
import sys
import textwrap
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import quote

import yaml


def _ok(key: str, value: Any) -> str:
    return json.dumps({"ok": True, key: value}, ensure_ascii=False, sort_keys=True)


def _error(message: str) -> str:
    return json.dumps(
        {"ok": False, "error": message}, ensure_ascii=False, sort_keys=True
    )


def _gateway(kwargs: dict[str, Any]):
    gateway = kwargs.get("gateway")
    if gateway is None:
        gateway = _default_gateway()
    return gateway


def _hydrate_saved_gateway_env() -> None:
    try:
        from agents.hermes_embedded_gateway import _hydrate_saved_feishu_gateway_env
    except Exception:
        return
    _hydrate_saved_feishu_gateway_env()


@lru_cache(maxsize=1)
def _messages_module():
    module_path = Path(__file__).with_name("messages.py")
    spec = importlib.util.spec_from_file_location(
        "semantier_feishu_meeting_coordinator_messages",
        module_path,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(
            f"failed to load meeting coordinator messages from {module_path}"
        )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _meeting_modules():
    try:
        from . import gateway as meeting_coordinator_gateway
        from . import store as meeting_coordinator_store
    except ImportError:
        plugin_parent = Path(__file__).resolve().parent.parent
        if str(plugin_parent) not in sys.path:
            sys.path.insert(0, str(plugin_parent))
        from feishu_meeting_coordinator import gateway as meeting_coordinator_gateway
        from feishu_meeting_coordinator import store as meeting_coordinator_store

    return meeting_coordinator_gateway, meeting_coordinator_store


class _LocalCronClient:
    def __init__(self, hermes_home: str):
        self.hermes_home = Path(hermes_home).expanduser().resolve()

    def _bind(self):
        from runtime_paths import bind_workspace_env

        return bind_workspace_env(self.hermes_home)

    def _workspace_skill_refs(self, skills: list[str]) -> list[str]:
        resolved: list[str] = []
        for skill in skills:
            skill_name = str(skill or "").strip()
            if skill_name != "feishu_meeting_coordinator":
                if skill_name:
                    resolved.append(skill_name)
                continue
            plugin_dir = self.hermes_home / "plugins" / skill_name
            if (plugin_dir / "SKILL.md").exists():
                resolved.append(
                    "feishu_meeting_coordinator:feishu-bot-meeting-coordinator"
                )
            else:
                resolved.append(skill_name)
        return resolved

    def _ensure_no_agent_script(self, *, profile: str, script: str, name: str) -> None:
        try:
            from hermes_cli.profiles import normalize_profile_name, resolve_profile_env

            profile_home = Path(
                resolve_profile_env(normalize_profile_name(profile))
            ).resolve()
        except Exception as exc:
            raise RuntimeError(
                f"failed to resolve meeting coordinator profile {profile!r}: {exc}"
            ) from exc
        scripts_dir = profile_home / "scripts"
        scripts_dir.mkdir(parents=True, exist_ok=True)
        script_path = (scripts_dir / script).resolve()
        try:
            script_path.relative_to(scripts_dir.resolve())
        except ValueError as exc:
            raise RuntimeError(
                f"blocked monitor script path outside profile scripts dir: {script!r}"
            ) from exc
        state_dir_raw = os.environ.get("SEMANTIER_LOCAL_STATE_DIR")
        if not state_dir_raw:
            raise RuntimeError(
                "SEMANTIER_LOCAL_STATE_DIR is required for no-agent meeting coordinator cron"
            )
        state_dir = Path(state_dir_raw).expanduser().resolve()
        workspace_id = self.hermes_home.name
        auth_db_path = (
            Path(os.environ.get("SEMANTIER_AUTH_DB_PATH") or state_dir / "auth.db")
            .expanduser()
            .resolve()
        )
        plugin_dir = self.hermes_home / "plugins" / "feishu_meeting_coordinator"
        plugin_loader = f"""
                plugin_tools_path = Path({str(plugin_dir)!r}) / "tools.py"
                spec = importlib.util.spec_from_file_location(
                    "semantier_feishu_meeting_coordinator_tools",
                    plugin_tools_path,
                )
                if spec is None or spec.loader is None:
                    raise RuntimeError(f"failed to load plugin tools from {{plugin_tools_path}}")
                plugin_tools = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(plugin_tools)
        """
        delivery_prefix = "meeting-rsvp-delivery-retry:"
        followup_prefix = "meeting-time-negotiator-followup:"
        if name.startswith(delivery_prefix):
            retry_workspace_id = name[len(delivery_prefix) :].strip()
            if retry_workspace_id != workspace_id:
                raise RuntimeError(
                    "delivery retry cron workspace does not match Hermes home"
                )
            invocation = f"""
                result_text = plugin_tools.feishu_meeting_escalation_retry_tick(
                    {{"workspace_id": {workspace_id!r}}}
                )
            """
        elif name.startswith(followup_prefix):
            negotiation_id = name[len(followup_prefix) :].strip()
            if not negotiation_id:
                raise RuntimeError(
                    "missing negotiation id for no-agent meeting coordinator follow-up job"
                )
            invocation = f"""
                result_text = plugin_tools.feishu_meeting_followup_cron_tick(
                    {{"negotiation_id": {negotiation_id!r}}}
                )
            """
        else:
            raise RuntimeError(f"unsupported no-agent meeting coordinator job {name!r}")
        script_text = (
            "from __future__ import annotations\n\n"
            "import importlib.util\n"
            "import json\n"
            "import os\n"
            "from pathlib import Path\n\n"
            'profile_home = Path(os.environ["HERMES_HOME"]).resolve()\n'
            f'os.environ["SEMANTIER_LOCAL_STATE_DIR"] = {str(state_dir)!r}\n'
            f'os.environ["SEMANTIER_AUTH_DB_PATH"] = {str(auth_db_path)!r}\n'
            f'os.environ["SEMANTIER_WORKSPACE_ID"] = {workspace_id!r}\n'
            f'os.environ.setdefault("HERMES_SESSION_WORKSPACE_OWNER_ID", {workspace_id!r})\n\n'
            f"{textwrap.dedent(plugin_loader).strip()}\n\n"
            f"{textwrap.dedent(invocation).strip()}\n"
            "try:\n"
            "    payload = json.loads(result_text)\n"
            "except json.JSONDecodeError:\n"
            "    print(result_text)\n"
            "    raise SystemExit(1)\n"
            'if not payload.get("ok"):\n'
            "    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))\n"
            "    raise SystemExit(1)\n"
            'print(json.dumps({"wakeAgent": False, "result": payload.get("result")}, ensure_ascii=False, sort_keys=True))\n'
        )
        script_path.write_text(script_text, encoding="utf-8")

    def agent_runtime_config(self, *, profile: str) -> dict[str, str | None]:
        if not os.environ.get("SEMANTIER_WORKSPACE_ID"):
            raise RuntimeError("missing_workspace_authority")
        try:
            _feishu_helper()._resolve_runtime_feishu_config()
        except Exception as exc:
            raise RuntimeError("missing_feishu_bot_config") from exc
        try:
            from hermes_cli.profiles import normalize_profile_name, resolve_profile_env

            profile_home = Path(
                resolve_profile_env(normalize_profile_name(profile))
            ).resolve()
        except Exception as exc:
            raise RuntimeError("missing_workspace_authority") from exc
        config_path = profile_home / "config.yaml"
        try:
            loaded = (
                yaml.safe_load(config_path.read_text(encoding="utf-8"))
                if config_path.exists()
                else {}
            )
        except Exception as exc:
            raise RuntimeError("invalid_profile_configuration") from exc
        config = loaded if isinstance(loaded, dict) else {}
        model_cfg = config.get("model")
        if isinstance(model_cfg, str):
            model = model_cfg.strip()
            provider = ""
            base_url = None
        elif isinstance(model_cfg, dict):
            model = str(
                model_cfg.get("default") or model_cfg.get("model") or ""
            ).strip()
            provider = str(model_cfg.get("provider") or "").strip()
            base_url = str(model_cfg.get("base_url") or "").strip() or None
        else:
            model = ""
            provider = ""
            base_url = None
        return {
            "model": model or None,
            "provider": provider or None,
            "base_url": base_url,
        }

    def ensure_job(
        self,
        *,
        name: str,
        schedule: str,
        profile: str,
        prompt: str,
        skills: list[str],
        deliver: str,
        repeat: int,
        no_agent: bool = False,
        script: str | None = None,
        model: str | None = None,
        provider: str | None = None,
        base_url: str | None = None,
    ) -> str:
        with self._bind():
            from cron.jobs import create_job, list_jobs, update_job

            resolved_skills = self._workspace_skill_refs(skills)
            if no_agent:
                if not script:
                    raise RuntimeError(
                        "no-agent meeting coordinator cron requires a script"
                    )
                self._ensure_no_agent_script(profile=profile, script=script, name=name)
            for job in list_jobs(include_disabled=True):
                if str(job.get("name") or "") != name:
                    continue
                job_id = str(job.get("id") or "")
                updates: dict[str, Any] = {}
                if job.get("enabled") is False:
                    updates["enabled"] = True
                if list(job.get("skills") or []) != resolved_skills:
                    updates["skills"] = resolved_skills
                if bool(job.get("no_agent")) is not bool(no_agent):
                    updates["no_agent"] = bool(no_agent)
                if (job.get("script") or None) != script:
                    updates["script"] = script
                if no_agent and str(job.get("model") or ""):
                    updates["model"] = None
                if no_agent and str(job.get("provider") or ""):
                    updates["provider"] = None
                if no_agent and str(job.get("base_url") or ""):
                    updates["base_url"] = None
                if not no_agent and (job.get("model") or None) != model:
                    updates["model"] = model
                if not no_agent and (job.get("provider") or None) != provider:
                    updates["provider"] = provider
                if not no_agent and (job.get("base_url") or None) != base_url:
                    updates["base_url"] = base_url
                if updates:
                    update_job(job_id, updates)
                return job_id
            job = create_job(
                prompt=prompt,
                schedule=schedule,
                name=name,
                skills=resolved_skills,
                deliver=deliver,
                repeat=repeat,
                profile=profile,
                no_agent=no_agent,
                script=script,
                model=model,
                provider=provider,
                base_url=base_url,
            )
            return str(job["id"])

    def job_exists(self, cron_job_id: str) -> bool:
        with self._bind():
            from cron.jobs import list_jobs

            return any(
                str(job.get("id") or "") == str(cron_job_id)
                for job in list_jobs(include_disabled=True)
            )

    def get_job(self, cron_job_id: str) -> dict[str, Any] | None:
        with self._bind():
            from cron.jobs import get_job

            return get_job(cron_job_id)

    def disable_job(self, cron_job_id: str) -> None:
        with self._bind():
            from cron.jobs import update_job

            update_job(cron_job_id, {"enabled": False})

    def delete_job(self, cron_job_id: str) -> bool:
        with self._bind():
            from cron.jobs import remove_job

            return bool(remove_job(cron_job_id))


class _DefaultGateway:
    def _cron(self) -> _LocalCronClient:
        hermes_home = _text(_session_metadata().get("hermes_home")) or _session_env(
            "HERMES_SESSION_HERMES_HOME"
        )
        if not hermes_home:
            raise RuntimeError("Semantier gateway binding required")
        return _LocalCronClient(hermes_home)

    def _cron_for_monitor(self, monitor: dict[str, Any] | None) -> _LocalCronClient:
        binding: dict[str, Any] = {}
        if monitor:
            raw_binding = monitor.get("creator_delivery_binding_json")
            if isinstance(raw_binding, str) and raw_binding.strip():
                try:
                    parsed = json.loads(raw_binding)
                except json.JSONDecodeError:
                    parsed = {}
                if isinstance(parsed, dict):
                    binding = parsed
            elif isinstance(raw_binding, dict):
                binding = raw_binding
        hermes_home = (
            _text(binding.get("hermes_home"))
            or _text(_session_metadata().get("hermes_home"))
            or _session_env("HERMES_SESSION_HERMES_HOME")
        )
        if not hermes_home:
            raise RuntimeError("Semantier gateway binding required")
        return _LocalCronClient(hermes_home)

    def escalation_retry_tick(self, payload: dict[str, Any]) -> dict[str, Any]:
        meeting_coordinator_gateway, meeting_coordinator_store = _meeting_modules()

        return meeting_coordinator_gateway.escalation_retry_tick(
            payload,
            store=meeting_coordinator_store.MeetingCoordinatorStore(),
            delivery_client=_CreatorDeliveryClient(),
        )

    def requeue_delivery_task(
        self, *, delivery_task_id: str, reason: str
    ) -> dict[str, Any]:
        meeting_coordinator_gateway, meeting_coordinator_store = _meeting_modules()

        return meeting_coordinator_gateway.requeue_delivery_task(
            delivery_task_id=delivery_task_id,
            reason=reason,
            store=meeting_coordinator_store.MeetingCoordinatorStore(),
            cron=self._cron(),
        )

    def negotiation_case_start(self, payload: dict[str, Any]) -> dict[str, Any]:
        meeting_coordinator_gateway, meeting_coordinator_store = _meeting_modules()

        store = meeting_coordinator_store.MeetingCoordinatorStore()
        negotiation = store.create_or_get_negotiation_case(
            monitor_id=_text(payload.get("monitor_id")),
            event_revision_id=_text(payload.get("event_revision_id")),
            trigger_attendee_user_id=_text(payload.get("trigger_attendee_user_id")),
        )
        if payload.get("ensure_kanban") is not False:
            negotiation = meeting_coordinator_gateway.ensure_negotiation_kanban_task(
                negotiation_id=str(negotiation["negotiation_id"]),
                store=store,
                kanban=None,
            )
        return negotiation

    def negotiation_case_tick(self, payload: dict[str, Any]) -> dict[str, Any]:
        meeting_coordinator_gateway, meeting_coordinator_store = _meeting_modules()
        store = meeting_coordinator_store.MeetingCoordinatorStore()
        negotiation_id = _text(payload.get("negotiation_id"))
        cron = self._cron_for_monitor(store.get_negotiation(negotiation_id)) if negotiation_id else None
        return meeting_coordinator_gateway.negotiation_case_tick(
            payload,
            store=store,
            cron=cron,
        )

    def negotiation_followup_cron_ensure(self, payload: dict[str, Any]) -> dict[str, Any]:
        meeting_coordinator_gateway, meeting_coordinator_store = _meeting_modules()

        negotiation_id = _text(payload.get("negotiation_id"))
        if not negotiation_id:
            raise ValueError("negotiation_id is required")
        schedule = str(payload.get("schedule") or "every 2m")
        owner_profile = str(payload.get("owner_profile") or "").strip() or None
        owner_idempotency_key = (
            str(payload.get("owner_idempotency_key") or "").strip() or None
        )
        return meeting_coordinator_gateway.ensure_negotiation_followup_cron(
            negotiation_id=negotiation_id,
            store=meeting_coordinator_store.MeetingCoordinatorStore(),
            cron=self._cron(),
            schedule=schedule,
            owner_profile=owner_profile,
            owner_idempotency_key=owner_idempotency_key,
        )

    def negotiation_followup_cron_stop(self, payload: dict[str, Any]) -> dict[str, Any]:
        meeting_coordinator_gateway, meeting_coordinator_store = _meeting_modules()

        negotiation_id = _text(payload.get("negotiation_id"))
        if not negotiation_id:
            raise ValueError("negotiation_id is required")
        expected_followup_cron_job_id = payload.get("expected_followup_cron_job_id")
        owner_profile = str(payload.get("owner_profile") or "").strip() or None
        owner_idempotency_key = (
            str(payload.get("owner_idempotency_key") or "").strip() or None
        )
        return meeting_coordinator_gateway.stop_negotiation_followup_cron(
            negotiation_id=negotiation_id,
            store=meeting_coordinator_store.MeetingCoordinatorStore(),
            cron=self._cron(),
            owner_profile=owner_profile,
            owner_idempotency_key=owner_idempotency_key,
            reason=_text(payload.get("reason") or "operator_stop"),
            expected_followup_cron_job_id=(
                str(expected_followup_cron_job_id)
                if expected_followup_cron_job_id is not None
                else None
            ),
        )

    def negotiation_followup_cron_tick(self, payload: dict[str, Any]) -> dict[str, Any]:
        meeting_coordinator_gateway, meeting_coordinator_store = _meeting_modules()

        return meeting_coordinator_gateway.negotiation_followup_cron_tick(
            payload,
            store=meeting_coordinator_store.MeetingCoordinatorStore(),
            cron=self._cron(),
        )

    def negotiation_kanban_worker_tick(self, payload: dict[str, Any]) -> dict[str, Any]:
        meeting_coordinator_gateway, meeting_coordinator_store = _meeting_modules()

        return meeting_coordinator_gateway.negotiation_kanban_worker_tick(
            payload,
            store=meeting_coordinator_store.MeetingCoordinatorStore(),
            kanban=meeting_coordinator_gateway._resolve_kanban_client(None),
        )

    def negotiation_case_submit_reply(self, payload: dict[str, Any]) -> dict[str, Any]:
        meeting_coordinator_gateway, meeting_coordinator_store = _meeting_modules()

        store = meeting_coordinator_store.MeetingCoordinatorStore()
        reply_payload = dict(payload)
        if reply_payload.get("start_time") and reply_payload.get("end_time"):
            _normalize_temporal_window_payload(reply_payload)
        return meeting_coordinator_gateway.submit_negotiation_reply(
            reply_payload,
            store=store,
        )

    def negotiation_case_finalize(self, payload: dict[str, Any]) -> dict[str, Any]:
        meeting_coordinator_gateway, meeting_coordinator_store = _meeting_modules()

        store = meeting_coordinator_store.MeetingCoordinatorStore()
        return meeting_coordinator_gateway.finalize_negotiation_case(
            payload,
            store=store,
            calendar_client=_CalendarUpdateClient(),
            cron=self._cron(),
        )

    def negotiation_requester_decision(self, payload: dict[str, Any]) -> dict[str, Any]:
        meeting_coordinator_gateway, meeting_coordinator_store = _meeting_modules()

        return meeting_coordinator_gateway.apply_requester_decision(
            payload,
            store=meeting_coordinator_store.MeetingCoordinatorStore(),
            cron=self._cron(),
            kanban=meeting_coordinator_gateway._resolve_kanban_client(None),
        )

    def negotiation_case_stop(self, payload: dict[str, Any]) -> dict[str, Any]:
        _, meeting_coordinator_store = _meeting_modules()

        store = meeting_coordinator_store.MeetingCoordinatorStore()
        negotiation_id = _text(payload.get("negotiation_id"))
        owner = f"operator:{_text(payload.get('operator_user_id')) or 'unknown'}"
        negotiation = store.get_negotiation(negotiation_id)
        result = store.transition_negotiation_state(
            negotiation_id,
            expected_state=str(negotiation["status"]),
            next_state="cancelled",
            patch={},
            actor_id=owner,
        )
        if not result["ok"]:
            raise RuntimeError(str(result["reason"]))
        return result["record"]

    def negotiation_resume(self, payload: dict[str, Any]) -> dict[str, Any]:
        _, meeting_coordinator_store = _meeting_modules()

        negotiation_id = _text(payload.get("negotiation_id"))
        if not negotiation_id:
            raise ValueError("negotiation_id is required")
        store = meeting_coordinator_store.MeetingCoordinatorStore()
        return {
            "negotiation": store.get_negotiation(negotiation_id),
            "participants": store.list_negotiation_participants(negotiation_id),
            "candidate_slots": store.list_candidate_slots(negotiation_id),
            "votes": store.list_negotiation_votes(negotiation_id),
            "events": store.list_negotiation_events(negotiation_id),
            "outbound_messages": store.list_outbound_negotiation_messages(negotiation_id),
            "finalize_attempts": store.list_finalize_attempts(negotiation_id),
        }

    def negotiation_rsvp_poll(self, payload: dict[str, Any]) -> dict[str, Any]:
        _, meeting_coordinator_store = _meeting_modules()

        negotiation_id = _text(payload.get("negotiation_id"))
        if not negotiation_id:
            raise ValueError("negotiation_id is required")
        store = meeting_coordinator_store.MeetingCoordinatorStore()
        negotiation = store.get_negotiation(negotiation_id)
        raw_statuses: list[dict[str, Any]] = []
        snapshots: list[dict[str, Any]] = []

        calendar_id = _text(negotiation.get("calendar_id"))
        event_id = _text(negotiation.get("event_id"))
        if calendar_id and event_id:
            attendee_statuses = _FeishuClient().get_attendee_response_statuses(
                calendar_id=calendar_id,
                event_id=event_id,
            )
            if isinstance(attendee_statuses, list):
                raw_statuses = list(attendee_statuses)
                for attendee in raw_statuses:
                    if not isinstance(attendee, dict):
                        continue
                    attendee_user_id = _text(attendee.get("user_id"))
                    if not attendee_user_id:
                        continue
                    normalized = _normalize_feishu_rsvp_status(
                        attendee.get("response_status")
                    )
                    persisted = normalized
                    if normalized == "accepted":
                        persisted = "accepted_slot"
                    elif normalized == "declined":
                        persisted = "declined_slot"
                    else:
                        persisted = "unknown"
                    try:
                        store.update_negotiation_participant_response(
                            negotiation_id=negotiation_id,
                            attendee_user_id=attendee_user_id,
                            latest_response_status=persisted,
                            responded=normalized in {"accepted", "declined"},
                            latest_slot_id=_text(attendee.get("time_slot_id")) or None,
                        )
                    except KeyError:
                        continue
                    snapshots.append(
                        {
                            "attendee_user_id": attendee_user_id,
                            "response_status": normalized,
                        }
                    )

        _record_negotiation_event_safely(
            store=store,
            negotiation_id=negotiation_id,
            event_type="FOLLOWUP_RSVP_POLLED",
            actor_type="system",
            actor_id="meeting-time-negotiator",
            payload={
                "snapshot_count": len(snapshots),
                "snapshot": snapshots,
            },
        )
        return {
            "negotiation_id": negotiation_id,
            "calendar_id": calendar_id,
            "event_id": event_id,
            "response_statuses": raw_statuses,
            "normalized_responses": snapshots,
        }

    def negotiation_due_followups_list(self, payload: dict[str, Any]) -> dict[str, Any]:
        _, meeting_coordinator_store = _meeting_modules()

        negotiation_id = _text(payload.get("negotiation_id"))
        if not negotiation_id:
            raise ValueError("negotiation_id is required")
        store = meeting_coordinator_store.MeetingCoordinatorStore()
        negotiation = store.get_negotiation(negotiation_id)

        workspace_state = store.get_workspace_state(str(negotiation["workspace_id"]))
        interval_minutes = int(
            payload.get("followup_interval_minutes")
            if payload.get("followup_interval_minutes") is not None
            else workspace_state.get("monitor_interval_minutes")
            or 2
        )
        max_followups = int(
            payload.get("max_followups")
            if payload.get("max_followups") is not None
            else workspace_state.get("max_followups")
            or 3
        )

        due_followups: list[dict[str, Any]] = []
        for participant in store.list_negotiation_participants(negotiation_id):
            if not _followup_reminder_needed(participant):
                continue
            if int(participant.get("followup_count") or 0) >= max_followups:
                continue
            if not _followup_due(participant, interval_minutes=interval_minutes):
                continue
            due_followups.append(
                {
                    "attendee_user_id": _text(participant.get("attendee_user_id")),
                    "followup_count": int(participant.get("followup_count") or 0),
                    "last_followup_at": _text(participant.get("last_followup_at")),
                    "latest_response_status": _text(
                        participant.get("latest_response_status")
                    ),
                }
            )
        return {
            "negotiation_id": negotiation_id,
            "due_count": len(due_followups),
            "followup_interval_minutes": interval_minutes,
            "max_followups": max_followups,
            "due_followups": due_followups,
            "status": str(negotiation.get("status") or ""),
        }

    def negotiation_requester_decision_request(
        self, payload: dict[str, Any]
    ) -> dict[str, Any]:
        _, meeting_coordinator_store = _meeting_modules()

        negotiation_id = _text(payload.get("negotiation_id"))
        if not negotiation_id:
            raise ValueError("negotiation_id is required")
        store = meeting_coordinator_store.MeetingCoordinatorStore()
        negotiation = store.get_negotiation(negotiation_id)
        if str(negotiation.get("status") or "") != "awaiting_requester_decision":
            return {
                "negotiation_id": negotiation_id,
                "decision_needed": False,
                "status": str(negotiation.get("status") or ""),
            }
        candidate_slots: list[dict[str, str]] = []
        for slot in store.list_candidate_slots(negotiation_id):
            candidate_slots.append(
                {
                    "slot_id": _text(slot.get("slot_id")),
                    "start_time": _text(slot.get("start_time")),
                    "end_time": _text(slot.get("end_time")),
                    "timezone": _text(slot.get("timezone")),
                }
            )
        return {
            "negotiation_id": negotiation_id,
            "decision_needed": True,
            "status": str(negotiation.get("status") or ""),
            "allowed_actions": [
                "requester_cancel",
                "requester_keep_original",
                "requester_select_slot",
            ],
            "candidate_slots": candidate_slots,
            "original_start_time": _text(negotiation.get("original_start_time")),
            "original_end_time": _text(negotiation.get("original_end_time")),
            "timezone": _text(negotiation.get("timezone")),
        }

    def negotiation_requester_decision_record(self, payload: dict[str, Any]) -> dict[str, Any]:
        _, meeting_coordinator_store = _meeting_modules()

        negotiation_id = _text(payload.get("negotiation_id"))
        requested_by_user_id = _text(
            payload.get("requested_by_user_id") or payload.get("requester_open_id")
        )
        action = _text(payload.get("action") or payload.get("request"))
        if not negotiation_id or not requested_by_user_id or not action:
            raise ValueError("negotiation_id, requested_by_user_id, and action are required")
        store = meeting_coordinator_store.MeetingCoordinatorStore()
        negotiation = store.get_negotiation(negotiation_id)
        if requested_by_user_id != _text(negotiation.get("creator_user_id")):
            raise PermissionError("requester authority mismatch")

        return self.negotiation_requester_decision(
            {
                "negotiation_id": negotiation_id,
                "requested_by_user_id": requested_by_user_id,
                "action": action,
                "slot_id": _text(
                    payload.get("slot_id") or payload.get("selected_slot_id")
                ),
            }
        )


def _default_gateway() -> _DefaultGateway:
    return _DefaultGateway()


class _FeishuClient:
    def get_attendee_response_statuses(
        self, *, calendar_id: str, event_id: str
    ) -> list[dict[str, Any]]:
        result = _feishu_helper().list_attendee_status(
            event_id=event_id,
            calendar_id=calendar_id,
            requester_open_id=_feishu_chat_initiator_open_id() or None,
            page_size=100,
        )
        attendees = result.get("attendees") if isinstance(result, dict) else None
        return list(attendees or [])

    def send_attendee_message(
        self, *, attendee_open_ids: list[str], message: str
    ) -> dict[str, Any]:
        return _feishu_helper().send_attendee_message(
            attendee_open_ids=attendee_open_ids,
            message=message,
        )


class _CreatorDeliveryClient:
    def send_creator_escalation(self, task: dict[str, Any]) -> dict[str, Any]:
        delivery_binding = json.loads(str(task.get("delivery_binding_json") or "{}"))
        payload = json.loads(str(task.get("payload_json") or "{}"))
        hermes_home = _text(delivery_binding.get("hermes_home")) or _session_env(
            "HERMES_SESSION_HERMES_HOME"
        )
        platform = _text(delivery_binding.get("platform")) or "feishu"
        chat_id = _text(delivery_binding.get("chat_id"))
        thread_id = _text(delivery_binding.get("thread_id"))
        message = _text(
            payload.get("message") or payload.get("reason") or "Meeting RSVP escalation"
        )
        if not hermes_home:
            raise RuntimeError("Semantier gateway binding required")
        if not chat_id:
            raise RuntimeError("creator delivery binding missing chat_id")
        target = (
            f"{platform}:{chat_id}:{thread_id}"
            if thread_id
            else f"{platform}:{chat_id}"
        )
        cron = _LocalCronClient(hermes_home)
        with cron._bind():
            _hydrate_saved_gateway_env()
            from tools.send_message_tool import send_message_tool

            raw = send_message_tool(
                {
                    "action": "send",
                    "target": target,
                    "message": message,
                }
            )
        result = json.loads(str(raw or "{}"))
        if result.get("error"):
            raise RuntimeError(str(result["error"]))
        return result


class _CalendarUpdateClient:
    def update_meeting_time(
        self,
        *,
        event_id: str,
        calendar_id: str,
        start_time: str,
        end_time: str,
        timezone: str,
    ) -> dict[str, Any]:
        return _feishu_helper().update_meeting_time(
            event_id=event_id,
            calendar_id=calendar_id,
            start_time=start_time,
            end_time=end_time,
            timezone=timezone,
        )


@lru_cache(maxsize=1)
def _feishu_helper():
    helper_path = Path(__file__).with_name("scripts") / "feishu_bot_api.py"
    spec = importlib.util.spec_from_file_location(
        "feishu_meeting_coordinator_feishu_bot_api",
        helper_path,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load Feishu helper script: {helper_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _helper_call(func_name: str, *args: Any, **kwargs: Any) -> str:
    try:
        result = getattr(_feishu_helper(), func_name)(*args, **kwargs)
    except Exception as exc:
        payload = getattr(exc, "payload", None)
        if isinstance(payload, dict) and payload:
            return json.dumps(
                {"ok": False, "error": str(exc), "payload": payload},
                ensure_ascii=False,
                sort_keys=True,
            )
        return _error(str(exc))
    return _ok("result", result)


def _helper_error(exc: Exception) -> str:
    payload = getattr(exc, "payload", None)
    if isinstance(payload, dict) and payload:
        return json.dumps(
            {"ok": False, "error": str(exc), "payload": payload},
            ensure_ascii=False,
            sort_keys=True,
        )
    return _error(str(exc))


def _payload(args: Any) -> dict[str, Any]:
    if args is None:
        return {}
    if not isinstance(args, dict):
        raise RuntimeError("tool args must be a JSON object")
    return dict(args)


def _list_arg(payload: dict[str, Any], *names: str) -> list[Any]:
    for name in names:
        value = payload.get(name)
        if value is None:
            continue
        if isinstance(value, list):
            return value
        if isinstance(value, str):
            text = value.strip()
            if text.startswith("["):
                try:
                    parsed = json.loads(text)
                except json.JSONDecodeError:
                    parsed = None
                if isinstance(parsed, list):
                    return parsed
        return [value]
    return []


def _search_text(value: Any) -> str:
    if isinstance(value, dict):
        for key in ("query", "name", "display_name", "email", "open_id", "user_id"):
            text = _text(value.get(key))
            if text:
                return text
        return ""
    return _text(value)


def _contact_search_queries(payload: dict[str, Any]) -> list[str]:
    queries: list[str] = []
    seen: set[str] = set()
    try:
        requester_open_id = _text(_requester_open_id(payload))
    except RequesterIdentityError:
        requester_open_id = ""

    for value in [
        _search_text(payload.get("query")),
        *_list_arg(payload, "queries", "query_list"),
    ]:
        query = _search_text(value)
        key = query.casefold()
        if query and query != requester_open_id and key not in seen:
            queries.append(query)
            seen.add(key)

    for value in _list_arg(
        payload, "attendees", "attendee", "participants", "participant"
    ):
        query = _search_text(value)
        key = query.casefold()
        if query and query != requester_open_id and key not in seen:
            queries.append(query)
            seen.add(key)

    return queries


def _text(value: Any) -> str:
    return str(value or "").strip()


def _session_env(name: str) -> str:
    env_value = os.getenv(name, "")
    if env_value:
        return env_value
    try:
        from gateway.session_context import get_session_env
    except Exception:
        return ""
    return get_session_env(name, "")


def _session_metadata() -> dict[str, Any]:
    hermes_home = _session_env("HERMES_SESSION_HERMES_HOME")
    session_id = _session_env("HERMES_SESSION_ID")
    env_language = _session_env("HERMES_LANGUAGE") or _session_env("HERMES_LOCALE")
    metadata: dict[str, Any] = {
        "platform": _session_env("HERMES_SESSION_PLATFORM"),
        "session_id": session_id,
        "session_key": _session_env("HERMES_SESSION_KEY"),
        "chat_id": _session_env("HERMES_SESSION_CHAT_ID"),
        "thread_id": _session_env("HERMES_SESSION_THREAD_ID") or None,
        "origin_user_id": _session_env("HERMES_SESSION_USER_ID"),
        "workspace_id": _session_env("HERMES_SESSION_WORKSPACE_OWNER_ID"),
        "hermes_home": hermes_home,
        "language": env_language,
    }
    if not hermes_home or not session_id:
        return metadata
    session_file = (
        Path(hermes_home) / "sessions" / f"session_{quote(session_id, safe='')}.json"
    )
    try:
        payload = json.loads(session_file.read_text(encoding="utf-8"))
    except Exception:
        return metadata
    if isinstance(payload, dict):
        metadata.update(
            {key: value for key, value in payload.items() if value is not None}
        )
    language = _language_from_metadata(metadata) or env_language
    if language:
        metadata["language"] = language
    return metadata


def _language_from_metadata(metadata: dict[str, Any]) -> str:
    for key in ("language", "locale", "user_language"):
        value = _text(metadata.get(key))
        if value:
            return value
    for container_key in ("settings", "user_settings"):
        container = metadata.get(container_key)
        if not isinstance(container, dict):
            continue
        value = _text(container.get("locale") or container.get("language"))
        if value:
            return value
    return ""


def _requester_display_name_from_metadata(metadata: dict[str, Any]) -> str:
    for key in (
        "requester_display_name",
        "requester_name",
        "origin_display_name",
        "origin_user_display_name",
        "sender_display_name",
    ):
        value = _text(metadata.get(key))
        if value:
            return value
    user = metadata.get("user")
    if isinstance(user, dict):
        return _text(user.get("display_name") or user.get("name"))
    return ""


def _is_generic_organizer_name(value: Any) -> bool:
    normalized = _text(value).casefold()
    return normalized in {"organizer", "组织者", "日程组织者", "会议组织者"}


def _requester_display_name_from_contacts(requester_open_id: str) -> str:
    if not requester_open_id:
        return ""
    try:
        result = _feishu_helper().search_contacts(requester_open_id, limit=1)
    except Exception:
        return ""
    candidates = result.get("candidates") if isinstance(result, dict) else None
    if not isinstance(candidates, list):
        return ""
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        if _text(candidate.get("open_id")) != requester_open_id:
            continue
        display_name = _text(candidate.get("display_name"))
        if display_name:
            return display_name
    return ""


def _current_session_origin_user_id() -> str:
    return _text(_session_metadata().get("origin_user_id"))


def _feishu_chat_initiator_open_id() -> str:
    platform = _session_env("HERMES_SESSION_PLATFORM").casefold()
    if platform != "feishu":
        return ""

    origin_user_id = _current_session_origin_user_id()
    if origin_user_id.startswith("ou_"):
        return origin_user_id

    session_user_id = _text(_session_env("HERMES_SESSION_USER_ID"))
    if session_user_id.startswith("ou_"):
        return session_user_id
    return ""


class RequesterIdentityError(RuntimeError):
    pass


def _requester_open_id(payload: dict[str, Any]) -> Any:
    del payload
    requester_open_id = _feishu_chat_initiator_open_id()
    if requester_open_id:
        return requester_open_id
    raise RequesterIdentityError(
        "requester_open_id must be resolved from a trusted Feishu session"
    )


def _attendees_without_requester(
    attendees: list[Any], requester_open_id: Any
) -> list[Any]:
    requester = _text(requester_open_id)
    if not requester:
        return attendees
    return [attendee for attendee in attendees if _search_text(attendee) != requester]


def _workspace_id_from_session(metadata: dict[str, Any]) -> str:
    workspace_id = _text(
        metadata.get("workspace_id") or metadata.get("workspace_owner_id")
    )
    if workspace_id:
        return workspace_id
    session_id = _text(metadata.get("session_id"))
    if ":" in session_id:
        return session_id.split(":", 1)[0]
    return ""


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _creator_delivery_binding(
    metadata: dict[str, Any], creator_user_id: str
) -> dict[str, Any]:
    workspace_id = _workspace_id_from_session(metadata)
    return {
        "workspace_owner_id": workspace_id,
        "creator_user_id": creator_user_id,
        "platform": _text(metadata.get("platform")) or "feishu",
        "chat_id": _text(metadata.get("chat_id")),
        "thread_id": metadata.get("thread_id") or None,
        "session_id": _text(metadata.get("session_id")),
        "session_key": _text(metadata.get("session_key")),
        "hermes_home": _text(metadata.get("hermes_home")),
        "delivery_adapter_key": metadata.get("delivery_adapter_key"),
        "language": _text(metadata.get("language")),
        "source": "feishu_session",
        "captured_at": _utc_now_iso(),
    }


def feishu_contacts_search(args, **kwargs):
    payload = _payload(args)
    queries = _contact_search_queries(payload)
    if len(queries) > 1:
        limit = int(payload.get("limit") or 10)
        results: list[dict[str, Any]] = []
        errors: list[dict[str, str]] = []
        helper = _feishu_helper()
        for query in queries:
            try:
                result = helper.search_contacts(query, limit=limit)
            except Exception as exc:
                error = {"query": query, "error": str(exc)}
                errors.append(error)
                results.append({"query": query, "ok": False, "error": str(exc)})
                continue
            results.append({"query": query, "ok": True, "result": result})
        return json.dumps(
            {
                "ok": not errors,
                "result": {"queries": queries, "results": results},
                **({"errors": errors} if errors else {}),
            },
            ensure_ascii=False,
            sort_keys=True,
        )

    query = queries[0] if queries else ""
    return _helper_call(
        "search_contacts",
        query,
        limit=int(payload.get("limit") or 10),
    )


def feishu_chats_search(args, **kwargs):
    payload = _payload(args)
    return _helper_call(
        "search_chats",
        str(payload.get("query") or ""),
        limit=int(payload.get("limit") or 10),
    )


def feishu_chat_members_get(args, **kwargs):
    payload = _payload(args)
    return _helper_call(
        "get_chat_members",
        str(payload.get("chat_id") or ""),
        member_id_type=str(payload.get("member_id_type") or "open_id"),
    )


def _normalize_temporal_slots(
    values: list[str],
    *,
    timezone_name: str,
    allow_past: bool = False,
) -> list[str]:
    from agents.temporal_resolution import normalize_calendar_slots

    return normalize_calendar_slots(
        values,
        timezone_name=timezone_name,
        allow_past=allow_past,
    )


def _normalize_temporal_window_payload(payload: dict[str, Any]) -> None:
    from agents.temporal_resolution import (
        normalize_calendar_instant,
        normalize_calendar_window,
        parse_local_datetime,
    )

    timezone_name = str(payload.get("timezone") or "Asia/Shanghai")
    if (
        not str(payload.get("end_time") or "").strip()
        and payload.get("duration_minutes") is not None
    ):
        try:
            duration_minutes = int(payload.get("duration_minutes"))
        except (TypeError, ValueError):
            raise ValueError("duration_minutes must be an integer") from None
        if duration_minutes <= 0:
            raise ValueError("duration_minutes must be greater than zero")
        start_dt = parse_local_datetime(
            normalize_calendar_instant(
                value=str(payload.get("start_time") or ""),
                timezone_name=timezone_name,
                allow_past=bool(payload.get("allow_past")),
            ),
            timezone_name,
        )
        payload["end_time"] = (
            start_dt + timedelta(minutes=duration_minutes)
        ).isoformat()
    window = normalize_calendar_window(
        start_time=str(payload.get("start_time") or ""),
        end_time=str(payload.get("end_time") or ""),
        timezone_name=timezone_name,
        allow_past=bool(payload.get("allow_past")),
    )
    payload["start_time"] = window.start_time
    payload["end_time"] = window.end_time
    payload["timezone"] = window.timezone


def feishu_meeting_create(args, **kwargs):
    payload = _payload(args)
    if payload.get("is_recurrent_meeting") is True:
        return _error(
            "recurrent meetings are not supported"
        )
    try:
        requester_open_id = _requester_open_id(payload)
    except RequesterIdentityError as exc:
        return _error(str(exc))
    attendees = _attendees_without_requester(
        _list_arg(
            payload,
            "attendees",
            "attendee",
            "participants",
            "participant",
            "attendee_open_ids",
            "attendee_open_id",
        ),
        requester_open_id,
    )
    if not attendees:
        return _error("at least one non-requester attendee is required")
    try:
        _normalize_temporal_window_payload(payload)
    except Exception as exc:
        return _error(str(exc))
    try:
        result = _feishu_helper().create_meeting(
            title=str(payload.get("title") or ""),
            start_time=str(payload.get("start_time") or ""),
            end_time=str(payload.get("end_time") or ""),
            attendees=attendees,
            timezone=str(payload.get("timezone") or "Asia/Shanghai"),
            description=payload.get("description"),
            location=payload.get("location"),
            idempotency_key=payload.get("idempotency_key"),
            requester_open_id=requester_open_id,
            requester_calendar_id=payload.get("requester_calendar_id"),
        )
    except Exception as exc:
        return _helper_error(exc)

    if "start_rsvp_monitor" in payload:
        warnings = list(result.get("warnings") or [])
        warnings.append(
            "start_rsvp_monitor is no longer supported; use negotiation follow-up cron flow."
        )
        result["warnings"] = warnings

    return _ok("result", result)


def feishu_meeting_negotiation_start(args, **kwargs):
    payload = _payload(args)
    timezone_name = str(payload.get("timezone") or "Asia/Shanghai")
    try:
        candidate_slots = _normalize_temporal_slots(
            [
                str(item)
                for item in _list_arg(payload, "candidate_slots", "candidate_slot")
            ],
            timezone_name=timezone_name,
            allow_past=bool(payload.get("allow_past")),
        )
    except Exception as exc:
        return _error(str(exc))
    return _helper_call(
        "start_negotiation",
        title=str(payload.get("title") or ""),
        requester_open_id=str(payload.get("requester_open_id") or ""),
        attendee_open_ids=[
            str(item)
            for item in _list_arg(payload, "attendee_open_ids", "attendee_open_id")
        ],
        candidate_slots=candidate_slots,
        duration_minutes=int(payload.get("duration_minutes") or 0),
        timezone=timezone_name,
        max_rounds=int(payload.get("max_rounds") or 3),
    )


def feishu_meeting_negotiation_next_round_prompts(args, **kwargs):
    payload = _payload(args)
    return _helper_call(
        "next_round_prompts",
        payload.get("state") or payload.get("state_payload") or {},
    )


def feishu_meeting_negotiation_submit_response(args, **kwargs):
    payload = _payload(args)
    state_payload = payload.get("state") or payload.get("state_payload") or {}
    timezone_name = str(
        state_payload.get("timezone") or payload.get("timezone") or "Asia/Shanghai"
    )
    try:
        accepted_slots = _normalize_temporal_slots(
            [
                str(item)
                for item in _list_arg(payload, "accepted_slots", "accepted_slot")
            ],
            timezone_name=timezone_name,
            allow_past=True,
        )
        declined_slots = _normalize_temporal_slots(
            [
                str(item)
                for item in _list_arg(payload, "declined_slots", "declined_slot")
            ],
            timezone_name=timezone_name,
            allow_past=True,
        )
    except Exception as exc:
        return _error(str(exc))
    return _helper_call(
        "submit_attendee_response",
        state_payload,
        attendee_open_id=str(payload.get("attendee_open_id") or ""),
        accepted_slots=accepted_slots,
        declined_slots=declined_slots,
        note=payload.get("note"),
    )


def feishu_meeting_negotiation_finalize(args, **kwargs):
    payload = _payload(args)
    return _helper_call(
        "finalize_negotiation_and_create_meeting",
        payload.get("state") or payload.get("state_payload") or {},
        description=payload.get("description"),
        location=payload.get("location"),
    )


def feishu_meeting_attendee_status_list(args, **kwargs):
    payload = _payload(args)
    return _helper_call(
        "list_attendee_status",
        event_id=str(payload.get("event_id") or ""),
        calendar_id=payload.get("calendar_id"),
        requester_open_id=payload.get("requester_open_id"),
        page_size=int(payload.get("page_size") or 50),
    )


def feishu_final_invitations_send(args, **kwargs):
    payload = _payload(args)
    try:
        _normalize_temporal_window_payload(payload)
    except Exception as exc:
        return _error(str(exc))
    return _helper_call(
        "send_final_invitations",
        attendee_open_ids=[
            str(item)
            for item in _list_arg(payload, "attendee_open_ids", "attendee_open_id")
        ],
        title=str(payload.get("title") or ""),
        start_time=str(payload.get("start_time") or ""),
        end_time=str(payload.get("end_time") or ""),
        timezone=str(payload.get("timezone") or "Asia/Shanghai"),
        meeting_link=payload.get("meeting_link"),
    )


def feishu_attendee_message_send(args, **kwargs):
    payload = _payload(args)
    return _helper_call(
        "send_attendee_message",
        attendee_open_ids=[
            str(item)
            for item in _list_arg(payload, "attendee_open_ids", "attendee_open_id")
        ],
        message=str(payload.get("message") or ""),
    )


def feishu_meeting_new_time_propose(args, **kwargs):
    payload = _payload(args)
    timezone_name = str(payload.get("timezone") or "Asia/Shanghai")
    try:
        candidate_slots = _normalize_temporal_slots(
            [
                str(item)
                for item in _list_arg(payload, "candidate_slots", "candidate_slot")
            ],
            timezone_name=timezone_name,
            allow_past=bool(payload.get("allow_past")),
        )
    except Exception as exc:
        return _error(str(exc))
    return _helper_call(
        "propose_new_time",
        attendee_open_ids=[
            str(item)
            for item in _list_arg(payload, "attendee_open_ids", "attendee_open_id")
        ],
        title=str(payload.get("title") or ""),
        candidate_slots=candidate_slots,
        timezone=timezone_name,
        event_id=payload.get("event_id"),
        current_time=payload.get("current_time"),
        note=payload.get("note"),
    )


def feishu_meeting_time_update(args, **kwargs):
    payload = _payload(args)
    try:
        _normalize_temporal_window_payload(payload)
    except Exception as exc:
        return _error(str(exc))
    return _helper_call(
        "update_meeting_time",
        event_id=str(payload.get("event_id") or ""),
        calendar_id=str(payload.get("calendar_id") or ""),
        start_time=str(payload.get("start_time") or ""),
        end_time=str(payload.get("end_time") or ""),
        timezone=str(payload.get("timezone") or "Asia/Shanghai"),
    )


def feishu_meeting_negotiation_case_start(args, **kwargs):
    try:
        result = _gateway(kwargs).negotiation_case_start(dict(args or {}))
    except Exception as exc:
        return _error(str(exc))
    return _ok("negotiation", result)


def feishu_meeting_negotiation_case_tick(args, **kwargs):
    try:
        result = _gateway(kwargs).negotiation_case_tick(dict(args or {}))
    except Exception as exc:
        return _error(str(exc))
    return _ok("result", result)


def feishu_meeting_followup_cron_ensure(args, **kwargs):
    try:
        result = _gateway(kwargs).negotiation_followup_cron_ensure(dict(args or {}))
    except Exception as exc:
        return _error(str(exc))
    return _ok("result", result)


def feishu_meeting_followup_cron_stop(args, **kwargs):
    try:
        result = _gateway(kwargs).negotiation_followup_cron_stop(dict(args or {}))
    except Exception as exc:
        return _error(str(exc))
    return _ok("result", result)


def feishu_meeting_followup_cron_tick(args, **kwargs):
    try:
        result = _gateway(kwargs).negotiation_followup_cron_tick(dict(args or {}))
    except Exception as exc:
        return _error(str(exc))
    return _ok("result", result)


def feishu_meeting_negotiation_kanban_worker_tick(args, **kwargs):
    try:
        result = _gateway(kwargs).negotiation_kanban_worker_tick(dict(args or {}))
    except Exception as exc:
        return _error(str(exc))
    return _ok("result", result)


def feishu_meeting_negotiation_case_submit_reply(args, **kwargs):
    try:
        result = _gateway(kwargs).negotiation_case_submit_reply(dict(args or {}))
    except Exception as exc:
        return _error(str(exc))
    return _ok("result", result)


def feishu_meeting_requester_decision(args, **kwargs):
    try:
        result = _gateway(kwargs).negotiation_requester_decision(dict(args or {}))
    except Exception as exc:
        return _error(str(exc))
    return _ok("result", result)


def feishu_meeting_negotiation_case_finalize(args, **kwargs):
    try:
        result = _gateway(kwargs).negotiation_case_finalize(dict(args or {}))
    except Exception as exc:
        return _error(str(exc))
    return _ok("finalize_attempt", result)


def feishu_meeting_negotiation_case_stop(args, **kwargs):
    try:
        result = _gateway(kwargs).negotiation_case_stop(dict(args or {}))
    except Exception as exc:
        return _error(str(exc))
    return _ok("negotiation", result)


def feishu_meeting_escalation_retry_tick(args, **kwargs):
    try:
        result = _gateway(kwargs).escalation_retry_tick(dict(args or {}))
    except Exception as exc:
        return _error(str(exc))
    return _ok("result", result)


def feishu_meeting_delivery_task_requeue(args, **kwargs):
    payload = dict(args or {})
    delivery_task_id = str(payload.get("delivery_task_id") or "").strip()
    reason = str(payload.get("reason") or "operator requested requeue").strip()
    if not delivery_task_id:
        return _error("delivery_task_id is required")
    try:
        task = _gateway(kwargs).requeue_delivery_task(
            delivery_task_id=delivery_task_id,
            reason=reason,
        )
    except Exception as exc:
        return _error(str(exc))
    return _ok("delivery_task", task)


def feishu_meeting_negotiation_resume(args, **kwargs):
    try:
        result = _gateway(kwargs).negotiation_resume(dict(args or {}))
    except Exception as exc:
        return _error(str(exc))
    return _ok("result", result)


def feishu_meeting_rsvp_poll(args, **kwargs):
    try:
        result = _gateway(kwargs).negotiation_rsvp_poll(dict(args or {}))
    except Exception as exc:
        return _error(str(exc))
    return _ok("result", result)


def feishu_meeting_due_followups_list(args, **kwargs):
    try:
        result = _gateway(kwargs).negotiation_due_followups_list(dict(args or {}))
    except Exception as exc:
        return _error(str(exc))
    return _ok("result", result)


def feishu_meeting_requester_decision_request(args, **kwargs):
    try:
        result = _gateway(kwargs).negotiation_requester_decision_request(
            dict(args or {})
        )
    except Exception as exc:
        return _error(str(exc))
    return _ok("result", result)


def feishu_meeting_requester_decision_record(args, **kwargs):
    try:
        result = _gateway(kwargs).negotiation_requester_decision_record(
            dict(args or {})
        )
    except Exception as exc:
        return _error(str(exc))
    return _ok("result", result)


def feishu_meeting_reply_ingest(args, **kwargs):
    payload = dict(args or {})
    if not payload.get("participant_user_id"):
        payload["participant_user_id"] = str(
            payload.get("sender_user_id") or payload.get("attendee_user_id") or ""
        ).strip() or None
    if (
        not payload.get("message_id")
        and isinstance(payload.get("provider_message_id"), str)
        and str(payload.get("provider_message_id")).strip()
    ):
        payload["message_id"] = str(payload.get("provider_message_id"))
    if not payload.get("reply_text") and isinstance(payload.get("raw_text"), str):
        payload["reply_text"] = str(payload.get("raw_text"))
    try:
        result = _gateway(kwargs).negotiation_case_submit_reply(payload)
    except Exception as exc:
        return _error(str(exc))
    return _ok("result", result)


def feishu_meeting_vote_record(args, **kwargs):
    payload = dict(args or {})
    if not payload.get("message_id") and isinstance(payload.get("provider_message_id"), str):
        candidate = str(payload.get("provider_message_id")).strip()
        if candidate:
            payload["message_id"] = candidate
    if not payload.get("participant_user_id") and payload.get("attendee_user_id"):
        payload["participant_user_id"] = str(payload.get("attendee_user_id"))
    try:
        result = _gateway(kwargs).negotiation_case_submit_reply(payload)
    except Exception as exc:
        return _error(str(exc))
    return _ok("result", result)


def feishu_meeting_slot_normalize(args, **kwargs):
    payload = _payload(args)
    values = [
        str(item)
        for item in _list_arg(payload, "slots", "slot", "candidate_slots", "candidate_slot")
    ]
    if not values:
        return _error("candidate_slots is required")
    timezone_name = str(payload.get("timezone") or "Asia/Shanghai")
    try:
        normalized = _normalize_temporal_slots(
            values,
            timezone_name=timezone_name,
            allow_past=bool(payload.get("allow_past")),
        )
    except Exception as exc:
        return _error(str(exc))
    return _ok("normalized_slots", normalized)


def feishu_meeting_negotiation_cancel(args, **kwargs):
    try:
        payload = dict(args or {})
        payload.setdefault("operator_user_id", payload.get("requested_by_user_id"))
        result = _gateway(kwargs).negotiation_case_stop(payload)
    except Exception as exc:
        return _error(str(exc))
    return _ok("negotiation", result)
