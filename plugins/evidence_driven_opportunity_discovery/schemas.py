from __future__ import annotations

TOOLSET_NAME = "evidence_driven_opportunity_discovery"


def _schema(properties, required=()):
    return {"parameters": {"type": "object", "properties": properties, "required": list(required), "additionalProperties": False}}


CREATE_SCOPE_SCHEMA = _schema({"name": {"type": "string"}, "domain": {"type": "string"}, "capabilities": {"type": "array", "items": {"type": "string"}}}, ("name", "domain"))
RECORD_OBSERVATION_SCHEMA = _schema({"observation": {"type": "object"}}, ("observation",))
FORM_HYPOTHESIS_SCHEMA = _schema({"hypothesis": {"type": "object"}}, ("hypothesis",))
RANK_SCHEMA = _schema({"candidates": {"type": "array", "items": {"type": "object"}}, "weights": {"type": "object"}}, ("candidates",))
INVESTIGATE_SCHEMA = _schema({"candidate": {"type": "object"}}, ("candidate",))
COUNTERFACTUAL_SCHEMA = _schema({"hypothesis_ref": {"type": "string"}, "input_evidence_refs": {"type": "array", "items": {"type": "string"}}, "transformation": {"type": "string"}}, ("hypothesis_ref", "input_evidence_refs", "transformation"))
PROPOSE_ACTION_SCHEMA = _schema({"proposal": {"type": "object"}}, ("proposal",))
RECORD_OUTCOME_SCHEMA = _schema({"outcome": {"type": "object"}}, ("outcome",))
ASSESS_SCHEMA = _schema({"assessment": {"type": "object"}, "current_weights": {"type": "object"}}, ("assessment",))
LIST_SCHEMA = _schema({"filters": {"type": "object"}})
