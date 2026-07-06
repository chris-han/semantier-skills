from __future__ import annotations

import json
import os
from pathlib import Path
import textwrap
from typing import Any

from agents.auth_session import RequestContext
from agents.gateway_identity import read_workspace_feishu_bot_config
from agents.webapi.job_service import (
    _create_workspace_cron_job,
    _delete_workspace_cron_job,
    _get_workspace_cron_job,
    _list_workspace_cron_jobs,
    _temporary_hermes_home,
    _update_workspace_cron_job,
)
import importlib.util
import sys
import yaml


class MeetingCoordinatorWebApiCronClient:
    def __init__(self, ctx: RequestContext):
        self.ctx = ctx

    def _repeat_times(self, value: Any) -> int | None:
        if isinstance(value, dict):
            raw = value.get("times")
        else:
            raw = value
        if raw is None:
            return None
        try:
            repeat = int(raw)
        except (TypeError, ValueError):
            return None
        return repeat if repeat > 0 else None

    def _workspace_skill_refs(self, skills: list[str]) -> list[str]:
        resolved: list[str] = []
        for skill in skills:
            skill_name = str(skill or "").strip()
            if skill_name != "feishu_meeting_coordinator":
                if skill_name:
                    resolved.append(skill_name)
                continue
            plugin_dir = Path(self.ctx.hermes_home) / "plugins" / skill_name
            if (plugin_dir / "SKILL.md").exists():
                resolved.append(
                    "feishu_meeting_coordinator:feishu-bot-meeting-coordinator"
                )
            else:
                resolved.append(skill_name)
        return resolved

    def _ensure_no_agent_script(self, *, profile: str, script: str, name: str) -> None:
        workspace_home = Path(self.ctx.hermes_home).expanduser().resolve()
        profile_home = workspace_home / "profiles" / profile
        scripts_dir = profile_home / "scripts"
        scripts_dir.mkdir(parents=True, exist_ok=True)
        script_path = (scripts_dir / script).resolve()
        try:
            script_path.relative_to(scripts_dir.resolve())
        except ValueError as exc:
            raise RuntimeError(f"blocked monitor script path outside profile scripts dir: {script!r}") from exc
        state_dir_raw = os.environ.get("SEMANTIER_LOCAL_STATE_DIR")
        if not state_dir_raw:
            raise RuntimeError("SEMANTIER_LOCAL_STATE_DIR is required for no-agent meeting coordinator cron")
        state_dir = Path(state_dir_raw).expanduser().resolve()
        workspace_id = str(self.ctx.workspace_id)
        auth_db_path = Path(os.environ.get("SEMANTIER_AUTH_DB_PATH") or state_dir / "auth.db").expanduser().resolve()
        plugin_dir = workspace_home / "plugins" / "feishu_meeting_coordinator"
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
            retry_workspace_id = name[len(delivery_prefix):].strip()
            if retry_workspace_id != workspace_id:
                raise RuntimeError("delivery retry cron workspace does not match request context")
            invocation = f"""
                result_text = plugin_tools.feishu_meeting_escalation_retry_tick(
                    {{"workspace_id": {workspace_id!r}}}
                )
            """
        elif name.startswith(followup_prefix):
            negotiation_id = name[len(followup_prefix):].strip()
            if not negotiation_id:
                raise RuntimeError("missing negotiation id for no-agent meeting coordinator follow-up job")
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
            "if not payload.get(\"ok\"):\n"
            "    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))\n"
            "    raise SystemExit(1)\n"
            'print(json.dumps({"wakeAgent": False, "result": payload.get("result")}, ensure_ascii=False, sort_keys=True))\n'
        )
        script_path.write_text(script_text, encoding="utf-8")

    def agent_runtime_config(self, *, profile: str) -> dict[str, str | None]:
        if not str(self.ctx.workspace_id or "").strip():
            raise RuntimeError("missing_workspace_authority")
        if read_workspace_feishu_bot_config(str(self.ctx.workspace_id)) is None:
            raise RuntimeError("missing_feishu_bot_config")
        profile_home = Path(self.ctx.hermes_home).expanduser().resolve() / "profiles" / profile
        config_path = profile_home / "config.yaml"
        try:
            loaded = yaml.safe_load(config_path.read_text(encoding="utf-8")) if config_path.exists() else {}
        except Exception as exc:
            raise RuntimeError("invalid_profile_configuration") from exc
        config = loaded if isinstance(loaded, dict) else {}
        model_cfg = config.get("model")
        if isinstance(model_cfg, str):
            model = model_cfg.strip()
            provider = ""
            base_url = None
        elif isinstance(model_cfg, dict):
            model = str(model_cfg.get("default") or model_cfg.get("model") or "").strip()
            provider = str(model_cfg.get("provider") or "").strip()
            base_url = str(model_cfg.get("base_url") or "").strip() or None
        else:
            model = ""
            provider = ""
            base_url = None
        return {"model": model or None, "provider": provider or None, "base_url": base_url}

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
        resolved_skills = self._workspace_skill_refs(skills)
        if no_agent:
            if not script:
                raise RuntimeError("no-agent meeting coordinator cron requires a script")
            self._ensure_no_agent_script(profile=profile, script=script, name=name)
        for job in _list_workspace_cron_jobs(self.ctx, include_disabled=True):
            if str(job.get("name") or "") == name:
                job_id = str(job.get("id") or "")
                updates: dict[str, Any] = {}
                if job.get("enabled") is False:
                    updates["enabled"] = True
                if bool(job.get("no_agent")) is not bool(no_agent):
                    updates["no_agent"] = bool(no_agent)
                if (job.get("script") or None) != script:
                    updates["script"] = script
                if str(job.get("prompt") or "") != prompt:
                    updates["prompt"] = prompt
                if list(job.get("skills") or []) != resolved_skills:
                    updates["skills"] = resolved_skills
                if str(job.get("profile") or "") != profile:
                    updates["profile"] = profile
                if self._repeat_times(job.get("repeat")) != self._repeat_times(repeat):
                    updates["repeat"] = repeat
                existing_schedule = job.get("schedule_display") or job.get("schedule")
                if existing_schedule is not None and str(existing_schedule) != schedule:
                    updates["schedule"] = schedule
                existing_deliver = job.get("deliver")
                if existing_deliver is not None and str(existing_deliver) != deliver:
                    updates["deliver"] = deliver
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
                if updates and "enabled" not in updates:
                    updates["enabled"] = True
                if updates:
                    _update_workspace_cron_job(self.ctx, job_id, updates)
                return job_id
        job = _create_workspace_cron_job(
            self.ctx,
            {
                "name": name,
                "schedule": schedule,
                "profile": profile,
                "prompt": prompt,
                "skills": resolved_skills,
                "deliver": deliver,
                "repeat": repeat,
                "no_agent": bool(no_agent),
                "script": script,
                "model": model,
                "provider": provider,
                "base_url": base_url,
            },
        )
        return str(job["id"])

    def job_exists(self, cron_job_id: str) -> bool:
        return _get_workspace_cron_job(self.ctx, cron_job_id) is not None

    def get_job(self, cron_job_id: str) -> dict[str, Any] | None:
        return _get_workspace_cron_job(self.ctx, cron_job_id)

    def disable_job(self, cron_job_id: str) -> None:
        _update_workspace_cron_job(self.ctx, cron_job_id, {"enabled": False})

    def delete_job(self, cron_job_id: str) -> bool:
        return _delete_workspace_cron_job(self.ctx, cron_job_id)


class MeetingCoordinatorWebApiDeliveryClient:
    def __init__(self, ctx: RequestContext):
        self.ctx = ctx

    def _hydrate_saved_gateway_env(self) -> None:
        try:
            from agents.hermes_embedded_gateway import _hydrate_saved_feishu_gateway_env
        except Exception:
            return
        _hydrate_saved_feishu_gateway_env()

    def send_creator_escalation(self, task: dict[str, Any]) -> dict[str, Any]:
        delivery_binding = json.loads(str(task.get("delivery_binding_json") or "{}"))
        payload = json.loads(str(task.get("payload_json") or "{}"))
        platform = str(delivery_binding.get("platform") or "feishu").strip()
        chat_id = str(delivery_binding.get("chat_id") or "").strip()
        thread_id = str(delivery_binding.get("thread_id") or "").strip()
        message = str(
            payload.get("message")
            or payload.get("reason")
            or "Meeting RSVP escalation"
        ).strip()
        if not chat_id:
            raise RuntimeError("creator delivery binding missing chat_id")
        target = f"{platform}:{chat_id}:{thread_id}" if thread_id else f"{platform}:{chat_id}"
        with _temporary_hermes_home(str(self.ctx.hermes_home)):
            self._hydrate_saved_gateway_env()
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


def meeting_coordinator_delivery_client_from_context(
    ctx: RequestContext,
) -> MeetingCoordinatorWebApiDeliveryClient:
    return MeetingCoordinatorWebApiDeliveryClient(ctx)


class MeetingCoordinatorWebApiCalendarClient:
    def __init__(self, ctx: RequestContext):
        self.ctx = ctx

    def _helper(self):
        plugin_dir = Path(self.ctx.hermes_home).expanduser().resolve() / "plugins" / "feishu_meeting_coordinator"
        helper_path = plugin_dir / "scripts" / "feishu_bot_api.py"
        spec = importlib.util.spec_from_file_location(
            "semantier_webapi_feishu_meeting_coordinator_feishu_bot_api",
            helper_path,
        )
        if spec is None or spec.loader is None:
            raise RuntimeError(f"failed to load Feishu meeting helper from {helper_path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module

    def _bind_runtime_identity(self) -> None:
        state_dir = os.environ.get("SEMANTIER_LOCAL_STATE_DIR")
        if not state_dir:
            raise RuntimeError("missing_workspace_authority")
        os.environ.setdefault("SEMANTIER_AUTH_DB_PATH", str(Path(state_dir) / "auth.db"))
        os.environ["SEMANTIER_WORKSPACE_ID"] = str(self.ctx.workspace_id)
        os.environ.setdefault("HERMES_SESSION_WORKSPACE_OWNER_ID", str(self.ctx.workspace_id))

    def update_meeting_time(
        self,
        *,
        event_id: str,
        calendar_id: str,
        start_time: str,
        end_time: str,
        timezone: str,
    ) -> dict[str, Any]:
        with _temporary_hermes_home(str(self.ctx.hermes_home)):
            self._bind_runtime_identity()
            return self._helper().update_meeting_time(
                event_id=event_id,
                calendar_id=calendar_id,
                start_time=start_time,
                end_time=end_time,
                timezone=timezone,
            )
