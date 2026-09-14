from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any


@dataclass(frozen=True)
class EvalCase:
    case_id: str
    context_graph_ref: str
    context_graph_hash: str
    evidence_refs: tuple[str, ...]
    ontology_ref: str
    ontology_hash: str
    world_time_pin: str
    reasoning_version: str
    task: str
    gold: dict[str, Any]


@dataclass(frozen=True)
class EvalPrediction:
    case_id: str
    valid_opportunity: bool
    supporting_refs: tuple[str, ...]
    contradicting_refs: tuple[str, ...]
    assumptions: tuple[str, ...]
    uncertainties: tuple[str, ...]
    recommended_next_step: str
    claims: tuple[dict[str, Any], ...]
    action_proposal: dict[str, Any] | None
    usage: dict[str, Any]


@dataclass(frozen=True)
class EvalRunManifest:
    benchmark_version: str
    arm: str
    repeat_index: int
    case_set_hash: str
    model_id: str
    provider_id: str
    model_config_hash: str
    toolset_hash: str
    tool_call_budget: int
    input_token_budget: int
    output_token_budget: int
    prompt_hash: str
    skill_hash: str
    skill_enabled: bool
    instruction_hash: str
    seed: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def validate_prediction(value: dict[str, Any]) -> EvalPrediction:
    required = (
        "case_id",
        "valid_opportunity",
        "supporting_refs",
        "contradicting_refs",
        "assumptions",
        "uncertainties",
        "recommended_next_step",
        "claims",
        "action_proposal",
        "usage",
    )
    missing = [key for key in required if key not in value]
    if missing:
        raise ValueError(f"PREDICTION_REQUIRED_FIELDS:{','.join(missing)}")
    usage = dict(value["usage"])
    for key in ("input_tokens", "output_tokens", "tool_calls"):
        if key not in usage:
            raise ValueError(f"USAGE_REQUIRED_FIELD:{key}")
    return EvalPrediction(
        case_id=str(value["case_id"]),
        valid_opportunity=bool(value["valid_opportunity"]),
        supporting_refs=tuple(str(x) for x in value["supporting_refs"]),
        contradicting_refs=tuple(str(x) for x in value["contradicting_refs"]),
        assumptions=tuple(str(x) for x in value["assumptions"]),
        uncertainties=tuple(str(x) for x in value["uncertainties"]),
        recommended_next_step=str(value["recommended_next_step"]),
        claims=tuple(dict(x) for x in value["claims"]),
        action_proposal=None if value["action_proposal"] is None else dict(value["action_proposal"]),
        usage=usage,
    )
