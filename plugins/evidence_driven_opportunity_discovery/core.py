from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json

DEFAULT_WEIGHTS = {
    "need_evidence_strength": 1.0,
    "severity": 1.0,
    "purchase_or_action_intent": 0.8,
    "addressability": 1.0,
    "expected_economic_value": 1.2,
    "freshness": 0.8,
    "source_quality": 0.8,
    "channel_reachability": 0.3,
    "contradiction_penalty": -1.0,
    "uncertainty_penalty": -0.7,
    "frequency": 0.2,
}

ASSESSMENT_DISPOSITIONS = {
    "hypothesis_supported", "hypothesis_weakened", "insufficient_evidence", "source_stale",
    "ranking_error", "channel_error", "offer_mismatch", "execution_error",
}

LEARNING_DELTAS = {
    "hypothesis_supported": {"need_evidence_strength": 0.05, "uncertainty_penalty": 0.02},
    "hypothesis_weakened": {"need_evidence_strength": -0.05, "uncertainty_penalty": -0.03},
    "insufficient_evidence": {"uncertainty_penalty": -0.05},
    "source_stale": {"freshness": -0.08},
    "ranking_error": {"expected_economic_value": -0.03, "severity": -0.02},
    "channel_error": {"channel_reachability": -0.08},
    "offer_mismatch": {"addressability": -0.05},
    "execution_error": {},
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_observation(value: dict) -> dict:
    if not isinstance(value, dict):
        raise ValueError("OBSERVATION_INVALID")
    subject_ref = str(value.get("subject_ref") or "").strip()
    source_ref = str(value.get("source_ref") or "").strip()
    source_type = str(value.get("source_type") or "").strip()
    if not subject_ref or not source_ref or not source_type:
        raise ValueError("OBSERVATION_REQUIRED_FIELDS")
    payload = value.get("structured_payload")
    content_ref = value.get("content_ref")
    if payload is None and not content_ref:
        raise ValueError("OBSERVATION_CONTENT_REQUIRED")
    captured_at = str(value.get("captured_at") or _utc_now())
    basis = json.dumps({"subject_ref": subject_ref, "source_ref": source_ref, "captured_at": captured_at, "payload": payload, "content_ref": content_ref}, sort_keys=True, default=str)
    return {
        "record_type": "ObservationV1",
        "observation_id": str(value.get("observation_id") or f"obs_{sha256(basis.encode()).hexdigest()[:16]}"),
        "subject_ref": subject_ref,
        "source_ref": source_ref,
        "source_type": source_type,
        "captured_at": captured_at,
        "observed_at": value.get("observed_at"),
        "content_ref": content_ref,
        "structured_payload": payload,
        "freshness": dict(value.get("freshness") or {}),
        "provenance": dict(value.get("provenance") or {}),
        "quality_flags": list(value.get("quality_flags") or []),
    }


def normalize_hypothesis(value: dict) -> dict:
    if not isinstance(value, dict):
        raise ValueError("HYPOTHESIS_INVALID")
    subject_ref = str(value.get("subject_ref") or "").strip()
    problem = str(value.get("problem_or_state_change") or "").strip()
    capability = str(value.get("commercial_capability_ref") or "").strip()
    supporting = [str(x) for x in value.get("supporting_observation_refs") or [] if str(x)]
    if not subject_ref or not problem or not capability or not supporting:
        raise ValueError("HYPOTHESIS_REQUIRED_FIELDS")
    normalized = {
        "record_type": "OpportunityHypothesisV1",
        "subject_ref": subject_ref,
        "problem_or_state_change": problem,
        "commercial_capability_ref": capability,
        "supporting_observation_refs": supporting,
        "contradicting_observation_refs": [str(x) for x in value.get("contradicting_observation_refs") or [] if str(x)],
        "assumptions": list(value.get("assumptions") or []),
        "uncertainties": list(value.get("uncertainties") or []),
        "expected_value_model": dict(value.get("expected_value_model") or {}),
        "status": str(value.get("status") or "PROPOSED"),
    }
    basis = json.dumps(normalized, sort_keys=True, default=str)
    normalized["hypothesis_id"] = str(value.get("hypothesis_id") or f"hyp_{sha256(basis.encode()).hexdigest()[:16]}")
    return normalized


def rank_candidates(candidates: list[dict], weights: dict | None = None) -> list[dict]:
    effective = {**DEFAULT_WEIGHTS, **(weights or {})}
    scored = []
    for candidate in candidates:
        features = dict(candidate.get("rank_features") or {})
        components = {}
        score = 0.0
        for key, weight in effective.items():
            if features.get(key) is None:
                continue
            value = float(features[key])
            contribution = value * float(weight)
            components[key] = {"value": value, "weight": float(weight), "contribution": contribution}
            score += contribution
        scored.append({**candidate, "score": score, "score_components": components, "record_type": "OpportunityCandidateV1"})
    scored.sort(key=lambda item: item["score"], reverse=True)
    return [{**item, "rank": index + 1} for index, item in enumerate(scored)]


def information_gain_requests(candidate: dict) -> list[dict]:
    uncertainties = candidate.get("uncertainties") or candidate.get("hypothesis", {}).get("uncertainties") or []
    normalized = []
    for item in uncertainties:
        if isinstance(item, str):
            normalized.append({"question": item, "impact": 0.5, "resolution_cost": 0.5})
        elif isinstance(item, dict) and item.get("question"):
            normalized.append({
                "question": str(item["question"]),
                "impact": float(item.get("impact", 0.5)),
                "resolution_cost": max(float(item.get("resolution_cost", 0.5)), 0.01),
                "source_hint": item.get("source_hint"),
            })
    for item in normalized:
        item["information_gain_score"] = item["impact"] / item["resolution_cost"]
    return sorted(normalized, key=lambda x: x["information_gain_score"], reverse=True)


def build_counterfactual_request(hypothesis_ref: str, evidence_refs: list[str], transformation: str) -> dict:
    return {"record_type": "CounterfactualArtifactRequestV1", "hypothesis_ref": hypothesis_ref, "input_evidence_refs": list(evidence_refs), "transformation": transformation, "synthetic": True, "status": "REQUESTED"}


def normalize_action_proposal(value: dict) -> dict:
    if not isinstance(value, dict) or any(not value.get(key) for key in ("action_type", "hypothesis_ref", "justification")):
        raise ValueError("ACTION_PROPOSAL_REQUIRED_FIELDS")
    return {
        "record_type": "OpportunityActionProposalV1",
        "action_type": str(value["action_type"]),
        "hypothesis_ref": str(value["hypothesis_ref"]),
        "justification": value["justification"],
        "expected_value": value.get("expected_value"),
        "uncertainty": value.get("uncertainty"),
        "estimated_cost": value.get("estimated_cost"),
        "reversibility": str(value.get("reversibility") or "UNKNOWN"),
        "risk_flags": list(value.get("risk_flags") or []),
        "required_runtime_capabilities": list(value.get("required_runtime_capabilities") or []),
        "authorization_status": "PROPOSED_NOT_AUTHORIZED",
    }


def normalize_outcome(value: dict) -> dict:
    if not isinstance(value, dict) or not value.get("hypothesis_ref") or not value.get("outcome_type"):
        raise ValueError("OUTCOME_REQUIRED_FIELDS")
    return {"record_type": "OpportunityOutcomeV1", "hypothesis_ref": str(value["hypothesis_ref"]), "action_ref": value.get("action_ref"), "outcome_type": str(value["outcome_type"]), "details": dict(value.get("details") or {}), "basis_refs": list(value.get("basis_refs") or [])}


def normalize_assessment(value: dict) -> dict:
    disposition = str(value.get("disposition") or "")
    if not value.get("hypothesis_ref") or disposition not in ASSESSMENT_DISPOSITIONS:
        raise ValueError("ASSESSMENT_INVALID")
    return {"record_type": "OpportunityAssessmentV1", "hypothesis_ref": str(value["hypothesis_ref"]), "outcome_ref": value.get("outcome_ref"), "disposition": disposition, "evidence_refs": list(value.get("evidence_refs") or []), "learning_proposal": dict(value.get("learning_proposal") or {}), "authority_effect": "NONE"}


def propose_weight_update(current_weights: dict | None, assessments: list[dict]) -> dict:
    proposed = {**DEFAULT_WEIGHTS, **(current_weights or {})}
    applied = []
    for assessment in assessments:
        disposition = str(assessment.get("disposition") or "")
        delta = LEARNING_DELTAS.get(disposition, {})
        for key, amount in delta.items():
            proposed[key] = round(float(proposed.get(key, 0.0)) + amount, 6)
        if delta:
            applied.append({"disposition": disposition, "delta": delta})
    return {
        "record_type": "OpportunityRankingPolicyChangeCandidateV1",
        "status": "PROPOSED_NOT_ACTIVATED",
        "current_weights": {**DEFAULT_WEIGHTS, **(current_weights or {})},
        "proposed_weights": proposed,
        "applied_assessments": applied,
        "historical_rewrite": False,
    }


class InMemoryOpportunityStore:
    def __init__(self) -> None:
        self.records = {"observations": [], "hypotheses": [], "outcomes": [], "assessments": []}

    def append(self, bucket: str, record: dict) -> dict:
        self.records[bucket].append(record)
        return record

    def snapshot(self) -> dict:
        return {key: list(value) for key, value in self.records.items()}
