from __future__ import annotations

from typing import Any


class OsoAdapter:
    """Optional enrichment adapter. It never supplies authority or required facts."""

    def __init__(self, client: Any | None = None, enabled: bool = False):
        self.client = client
        self.enabled = enabled

    def enrich(self, project_ref: str) -> dict[str, Any]:
        if not self.enabled or self.client is None:
            return {"status": "DEGRADED", "reason_code": "OSO_UNAVAILABLE", "metrics": {}}
        try:
            result = self.client.enrich(project_ref)
        except Exception as exc:  # external provider failures are non-authoritative
            return {"status": "DEGRADED", "reason_code": "OSO_SOURCE_ERROR", "message": str(exc), "metrics": {}}
        return {"status": "OK", "metrics": dict(result or {})}
