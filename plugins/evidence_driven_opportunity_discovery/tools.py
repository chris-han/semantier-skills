from __future__ import annotations

import json
from typing import Any

from .adapters.hermes import require_capabilities, trusted_context
from .kernel_bridge import kernel_bridge
from .core import (
    InMemoryOpportunityStore,
    build_counterfactual_request,
    information_gain_requests,
    normalize_action_proposal,
    normalize_assessment,
    normalize_hypothesis,
    normalize_observation,
    normalize_outcome,
    propose_weight_update,
    rank_candidates,
)

_STORE = InMemoryOpportunityStore()


def _ok(result: Any) -> str:
    return json.dumps({"ok": True, "result": result}, sort_keys=True, default=str)


def _error(code: str, message: str | None = None) -> str:
    return json.dumps({"ok": False, "error_code": code, **({"message": message} if message else {})}, sort_keys=True)


def create_opportunity_scope(args, **kwargs):
    try:
        context = trusted_context(kwargs)
        return _ok({
            "record_type": "OpportunityScopeV1",
            "name": str(args["name"]),
            "domain": str(args["domain"]),
            "capabilities": list(args.get("capabilities") or []),
            "organization_id": context["organization_id"],
            "workspace_id": context.get("workspace_id"),
            "actor_id": context["actor_id"],
        })
    except (RuntimeError, KeyError, ValueError) as exc:
        return _error(str(exc))


def record_observation(args, **kwargs):
    try:
        context = trusted_context(kwargs)
        observation = normalize_observation(args["observation"])
        _STORE.append("observations", observation)
        bridge = kernel_bridge(kwargs)
        kernel = bridge.promote_observation(observation=observation, runtime_context=context) if bridge else None
        return _ok({**observation, "kernel": kernel})
    except (RuntimeError, KeyError, TypeError, ValueError) as exc:
        return _error(str(exc))


def form_opportunity_hypothesis(args, **kwargs):
    try:
        context = trusted_context(kwargs)
        hypothesis = normalize_hypothesis(args["hypothesis"])
        _STORE.append("hypotheses", hypothesis)
        bridge = kernel_bridge(kwargs)
        kernel = bridge.project_opportunity_context(hypothesis=hypothesis, runtime_context=context) if bridge else None
        return _ok({**hypothesis, "kernel": kernel})
    except (RuntimeError, KeyError, TypeError, ValueError) as exc:
        return _error(str(exc))


def rank_opportunities(args, **kwargs):
    try:
        trusted_context(kwargs)
        return _ok(rank_candidates(list(args["candidates"]), args.get("weights")))
    except (RuntimeError, KeyError, TypeError, ValueError) as exc:
        return _error(str(exc))


def request_opportunity_investigation(args, **kwargs):
    try:
        trusted_context(kwargs)
        candidate = dict(args["candidate"])
        requests = information_gain_requests(candidate)
        return _ok({
            "record_type": "OpportunityInvestigationRequestV1",
            "candidate_ref": candidate.get("candidate_id") or candidate.get("hypothesis_ref"),
            "requests": requests,
            "highest_value_uncertainty": requests[0] if requests else None,
            "status": "PROPOSED",
        })
    except (RuntimeError, KeyError, TypeError, ValueError) as exc:
        return _error(str(exc))


def create_counterfactual_request(args, **kwargs):
    try:
        trusted_context(kwargs)
        return _ok(build_counterfactual_request(str(args["hypothesis_ref"]), list(args["input_evidence_refs"]), str(args["transformation"])))
    except (RuntimeError, KeyError, TypeError, ValueError) as exc:
        return _error(str(exc))


def propose_opportunity_action(args, **kwargs):
    try:
        context = trusted_context(kwargs)
        proposal = normalize_action_proposal(args["proposal"])
        require_capabilities(context, proposal["required_runtime_capabilities"])
        return _ok(proposal)
    except (RuntimeError, KeyError, TypeError, ValueError) as exc:
        return _error(str(exc))


def record_opportunity_outcome(args, **kwargs):
    try:
        context = trusted_context(kwargs)
        outcome = normalize_outcome(args["outcome"])
        _STORE.append("outcomes", outcome)
        bridge = kernel_bridge(kwargs)
        kernel = bridge.record_outcome_evidence(outcome=outcome, runtime_context=context) if bridge else None
        return _ok({**outcome, "kernel": kernel})
    except (RuntimeError, KeyError, TypeError, ValueError) as exc:
        return _error(str(exc))


def assess_opportunity(args, **kwargs):
    try:
        context = trusted_context(kwargs)
        assessment = _STORE.append("assessments", normalize_assessment(args["assessment"]))
        policy_change = propose_weight_update(args.get("current_weights"), [assessment])
        bridge = kernel_bridge(kwargs)
        kernel = bridge.propose_change_candidate(
            assessment=assessment,
            policy_change=policy_change,
            runtime_context=context,
        ) if bridge else None
        return _ok({
            "assessment": assessment,
            "ranking_policy_change_candidate": policy_change,
            "kernel": kernel,
        })
    except (RuntimeError, KeyError, TypeError, ValueError) as exc:
        return _error(str(exc))


def list_opportunities(args, **kwargs):
    try:
        trusted_context(kwargs)
        return _ok(_STORE.snapshot())
    except RuntimeError as exc:
        return _error(str(exc))
