from __future__ import annotations

import json
from typing import Any, Callable


def create_scan_schedule(*, schedule: str, name: str, universe_ref: str, max_targets: int = 25, cron_client: Callable[..., str] | None = None) -> dict[str, Any]:
    """Create an agent-backed Hermes schedule using the registered plugin skill."""
    client = cron_client
    if client is None:
        from tools.cronjob_tools import cronjob
        client = cronjob
    raw = client(action="create", schedule=schedule, name=name, skills=["vc_github_opportunity_radar"], enabled_toolsets=["vc_github_opportunity_radar"], deliver="local")
    result = json.loads(raw) if isinstance(raw, str) else dict(raw)
    if result.get("success"):
        result["radar_binding"] = {"universe_ref": universe_ref, "max_targets": max_targets, "ownership": "hermes_cron"}
    return result
