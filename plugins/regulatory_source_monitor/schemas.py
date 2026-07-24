from __future__ import annotations

TOOLSET_NAME = "regulatory-source-monitor"

LIST_DUE_SOURCES_SCHEMA = {
    "type": "object",
    "properties": {
        "organization_id": {"type": "string"},
        "as_of": {"type": "string"},
        "limit": {"type": "integer"},
        "offset": {"type": "integer"},
    },
    "required": ["organization_id", "as_of"],
}

RUN_MONITOR_SCHEMA = {
    "type": "object",
    "properties": {
        "organization_id": {"type": "string"},
        "workspace_id": {"type": "string"},
        "scheduled_at": {"type": "string"},
        "trigger": {"type": "string"},
        "limit": {"type": "integer"},
        "offset": {"type": "integer"},
    },
    "required": ["organization_id", "scheduled_at"],
}

SOURCE_STATUS_SCHEMA = {
    "type": "object",
    "properties": {
        "organization_id": {"type": "string"},
        "source_id": {"type": "string"},
        "as_of": {"type": "string"},
    },
    "required": ["organization_id", "source_id"],
}

ACKNOWLEDGE_ALERT_SCHEMA = {
    "type": "object",
    "properties": {
        "organization_id": {"type": "string"},
        "alert_id": {"type": "string"},
        "acknowledged_by": {"type": "string"},
        "acknowledgement": {"type": "object"},
    },
    "required": ["organization_id", "alert_id", "acknowledged_by"],
}
