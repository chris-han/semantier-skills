from __future__ import annotations

TOOLSET_NAME = "vc_github_opportunity_radar"

def _schema(properties, required=()):
    return {"parameters": {"type": "object", "properties": properties, "required": list(required), "additionalProperties": False}}

CREATE_UNIVERSE_SCHEMA = _schema({"name": {"type": "string"}, "source_filters": {"type": "object"}, "exclusions": {"type": "object"}, "operational_limits": {"type": "object"}}, ("name", "source_filters"))
SCAN_UNIVERSE_SCHEMA = _schema({"universe": {"type": "object"}, "repository": {"type": "string"}, "organization": {"type": "string"}, "topic": {"type": "string"}, "language": {"type": "string"}, "max_targets": {"type": "integer"}})
INSPECT_TARGET_SCHEMA = _schema({"repository": {"type": "string"}, "organization": {"type": "string"}})
SCORE_TARGET_SCHEMA = _schema({"observation": {"type": "object"}, "profile": {"type": "object"}}, ("observation",))
PROPOSE_CANDIDATE_SCHEMA = _schema({"candidate": {"type": "object"}}, ("candidate",))
LIST_CANDIDATES_SCHEMA = _schema({"filters": {"type": "object"}})
REQUEST_RESEARCH_SCHEMA = _schema({"candidate_id": {"type": "string"}, "research_type": {"type": "string"}, "reason": {"type": "string"}}, ("candidate_id", "research_type", "reason"))
SCHEDULE_SCAN_SCHEMA = _schema({"schedule": {"type": "string"}, "name": {"type": "string"}, "universe_ref": {"type": "string"}, "max_targets": {"type": "integer"}}, ("schedule", "name", "universe_ref"))
