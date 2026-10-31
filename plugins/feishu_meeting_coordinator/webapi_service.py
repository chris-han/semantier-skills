from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from agents.auth_session import RequestContext
import importlib.util
import sys








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
        from agents.webapi.job_service import _temporary_hermes_home
        with _temporary_hermes_home(str(self.ctx.hermes_home)):
            self._bind_runtime_identity()
            return self._helper().update_meeting_time(
                event_id=event_id,
                calendar_id=calendar_id,
                start_time=start_time,
                end_time=end_time,
                timezone=timezone,
            )
