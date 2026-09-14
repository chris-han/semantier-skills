from __future__ import annotations

from dataclasses import dataclass, asdict
from hashlib import sha256
import json
from typing import Any


_ALLOWED_DIFFERENCES = {"skill_hash", "skill_enabled", "instruction_hash"}


@dataclass(frozen=True)
class ControlledRunPins:
    case_set_hash: str
    model_id: str
    provider_id: str
    model_config_hash: str
    toolset_hash: str
    tool_call_budget: int
    input_token_budget: int
    output_token_budget: int
    context_graph_ref: str
    context_graph_hash: str
    evidence_hash: str
    ontology_ref: str
    ontology_hash: str
    world_time_pin: str
    reasoning_version: str
    prompt_hash: str
    skill_hash: str
    skill_enabled: bool
    instruction_hash: str
    seed: str | None = None

    def canonical_hash(self) -> str:
        raw = json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))
        return sha256(raw.encode()).hexdigest()


def validate_b2_b3_pair(b2: ControlledRunPins, b3: ControlledRunPins) -> dict[str, Any]:
    left = asdict(b2)
    right = asdict(b3)
    differing = {key: (left[key], right[key]) for key in left if left[key] != right[key]}
    invalid = {key: value for key, value in differing.items() if key not in _ALLOWED_DIFFERENCES}
    if invalid:
        raise ValueError(f"B2_B3_PIN_MISMATCH:{sorted(invalid)}")
    if b2.skill_enabled:
        raise ValueError("B2_SKILL_MUST_BE_DISABLED")
    if not b3.skill_enabled:
        raise ValueError("B3_SKILL_MUST_BE_ENABLED")
    if b2.skill_hash not in {"NONE", "none", ""}:
        raise ValueError("B2_SKILL_HASH_MUST_BE_NONE")
    if b3.skill_hash in {"NONE", "none", ""}:
        raise ValueError("B3_SKILL_HASH_REQUIRED")
    return {
        "status": "VALID_CONTROLLED_PAIR",
        "b2_hash": b2.canonical_hash(),
        "b3_hash": b3.canonical_hash(),
        "allowed_differences": sorted(differing),
    }


def case_disagreements(b2_predictions: list[dict[str, Any]], b3_predictions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def keyed(values: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        return {str(item["case_id"]): item for item in values}

    left = keyed(b2_predictions)
    right = keyed(b3_predictions)
    if set(left) != set(right):
        raise ValueError("B2_B3_CASE_SET_MISMATCH")

    fields = (
        "valid_opportunity",
        "supporting_refs",
        "contradicting_refs",
        "uncertainties",
        "recommended_next_step",
        "action_proposal",
    )
    result = []
    for case_id in sorted(left):
        changed = {
            field: {"b2": left[case_id].get(field), "b3": right[case_id].get(field)}
            for field in fields
            if left[case_id].get(field) != right[case_id].get(field)
        }
        if changed:
            result.append({"case_id": case_id, "differences": changed})
    return result
