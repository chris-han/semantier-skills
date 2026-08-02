from __future__ import annotations

from typing import Any

from contracts.investment_opportunity import OpportunityCandidateActionDTO, OpportunityCandidateSubmitDTO, RadarUniverseCandidateDTO, RuntimeContextDTO
from services.investment_opportunity_candidate_service import StoreBackedInvestmentOpportunityCandidateService
from services.investment_radar_configuration_service import StoreBackedInvestmentRadarConfigurationService
from ..adapters.github import GitHubAdapter
from ..features import calculate_features
from ..scoring import score_snapshot

PLUGIN_VERSION = "0.1.0"

def runtime_context(ctx: Any) -> RuntimeContextDTO:
    return RuntimeContextDTO(organization_id=str(getattr(ctx, "organization_id", "") or ""), workspace_id=getattr(ctx, "workspace_id", None), actor_id=str(getattr(ctx, "user_id", "") or ""), actor_role=str(getattr(ctx, "member_role", "") or ""), capabilities=tuple(getattr(ctx, "capabilities", ()) or ()))

def capabilities() -> dict[str, Any]:
    return {"plugin": "vc_github_opportunity_radar", "version": PLUGIN_VERSION, "toolset": "vc_github_opportunity_radar", "authority": "non_authoritative_candidate_proposal", "actions": ["OPPORTUNITY_QUALIFICATION", "OPPORTUNITY_REJECTION", "OPPORTUNITY_DEFERRAL", "OPPORTUNITY_ENRICHMENT_REQUEST", "OPPORTUNITY_PRELIMINARY_DILIGENCE_REQUEST", "OPPORTUNITY_MONITORING_TRIGGER_CREATE"]}

def inspect_target(*, payload: dict[str, Any]) -> dict[str, Any]:
    repository = str(payload.get("repository") or "").strip()
    if not repository: return {"status": "error", "error_code": "REPOSITORY_REQUIRED"}
    from ..observations import normalize_repository
    raw = payload.get("recorded_repository")
    if raw is None and repository.startswith("fixture/"):
        import json
        from pathlib import Path
        fixture_name = repository.split("/", 1)[1]
        fixture_stem = fixture_name.replace('-', '_')
        fixture_path = Path(__file__).resolve().parents[1] / "fixtures" / f"{fixture_stem}.json"
        if not fixture_path.exists() and fixture_stem.endswith("_project"):
            fixture_path = fixture_path.with_name(f"{fixture_stem[:-len('_project')]}_repository.json")
        if fixture_path.exists(): raw = json.loads(fixture_path.read_text(encoding="utf-8"))
    observation = normalize_repository(raw) if isinstance(raw, dict) else GitHubAdapter().get_repository(repository)
    return {"status": "ok", "observation": observation}

def fixture_observation() -> dict[str, Any]:
    import json
    from pathlib import Path
    raw = json.loads((Path(__file__).resolve().parents[1] / "fixtures" / "emerging_repository.json").read_text(encoding="utf-8"))
    return inspect_target(payload={"repository": "fixture/emerging-project", "recorded_repository": raw})

def score_target(*, payload: dict[str, Any]) -> dict[str, Any]:
    snapshot = calculate_features(dict(payload.get("observation") or {}))
    return {"status": "ok", "feature_snapshot": snapshot, "scorecard": score_snapshot(snapshot, payload.get("profile"))}

def propose_universe(*, ctx: Any, payload: dict[str, Any]) -> dict[str, Any]:
    context = runtime_context(ctx)
    candidate = RadarUniverseCandidateDTO(universe_candidate_id="draft", organization_id=context.organization_id, name=str(payload.get("name") or ""), scope=str(payload.get("scope") or "user"), owner_ref=context.actor_id, source_filters=dict(payload.get("source_filters") or {}), exclusions=dict(payload.get("exclusions") or {}), operational_limits=dict(payload.get("operational_limits") or {}), semantic_tier="T5")
    return {"status": "ok", "universe": StoreBackedInvestmentRadarConfigurationService().propose_universe(candidate, context)}

def radar_overview(*, candidate_service: Any, context: Any, filters: dict[str, Any] | None = None) -> dict[str, Any]:
    """Read-only dashboard DTO; mutations remain core service calls."""
    candidates = candidate_service.list_candidates(context, filters)
    return {"candidates": candidates, "total": len(candidates)}

def candidate_inspector(*, candidate_service: Any, context: Any, candidate_id: str) -> dict[str, Any]:
    return candidate_service.get_candidate_state(candidate_id, context)

def list_candidates(*, ctx: Any, filters: dict[str, Any] | None = None) -> dict[str, Any]:
    service = StoreBackedInvestmentOpportunityCandidateService()
    context = runtime_context(ctx)
    candidates = service.list_candidates(context, filters)
    return {"status": "ok", "candidates": candidates, "total": len(candidates)}

def submit_candidate(*, ctx: Any, payload: dict[str, Any]) -> dict[str, Any]:
    context = runtime_context(ctx)
    candidate = dict(payload.get("candidate") or payload)
    dto = OpportunityCandidateSubmitDTO(organization_id=context.organization_id, candidate_type=str(candidate.get("candidate_type", "emerging_project")), target=dict(candidate.get("target") or {}), detected_at=str(candidate.get("detected_at") or ""), observation_refs=tuple(candidate.get("observation_refs") or ()), scorecard_ref=str(candidate.get("scorecard_ref") or ""), signal_claims=tuple(candidate.get("signal_claims") or ()), missing_evidence=tuple(candidate.get("missing_evidence") or ()), proposed_next_actions=tuple(candidate.get("proposed_next_actions") or ()), justification=dict(candidate.get("justification") or {}))
    service = StoreBackedInvestmentOpportunityCandidateService()
    submitted = service.submit_candidate_idempotent(dto, context)
    candidate_id = submitted.get("candidate_id")
    validated = service.validate_candidate(candidate_id, context) if candidate_id and submitted.get("result") != "DUPLICATE" else submitted
    return {"status": "ok", "candidate": validated}

def candidate_state(*, ctx: Any, candidate_id: str) -> dict[str, Any]:
    return {"status": "ok", **StoreBackedInvestmentOpportunityCandidateService().get_candidate_state(candidate_id, runtime_context(ctx))}

def review_candidate(*, ctx: Any, candidate_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    context = runtime_context(ctx)
    action = OpportunityCandidateActionDTO(candidate_id=candidate_id, action_scope=str(payload.get("action_scope") or "OPPORTUNITY_DEFERRAL"), reason=str(payload.get("reason") or ""), trigger=dict(payload.get("trigger") or {}), evidence_refs=tuple(payload.get("evidence_refs") or ()))
    service = StoreBackedInvestmentOpportunityCandidateService()
    if payload.get("outcome_type"):
        action = OpportunityCandidateActionDTO(candidate_id=candidate_id, action_scope="OPPORTUNITY_FALSE_POSITIVE_RECORD", reason=action.reason, trigger={**action.trigger, "outcome_type": payload["outcome_type"], "case_ref": payload.get("case_ref")}, evidence_refs=action.evidence_refs)
        return {"status": "ok", "outcome": service.record_operator_outcome(action, context)}
    return {"status": "ok", "outcome": service.record_review_outcome(action, context)}

def propose_action(*, ctx: Any, candidate_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    context = runtime_context(ctx)
    action = OpportunityCandidateActionDTO(candidate_id=candidate_id, action_scope=str(payload.get("action_scope") or "OPPORTUNITY_ENRICHMENT_REQUEST"), reason=str(payload.get("reason") or ""), trigger=dict(payload.get("trigger") or {}), evidence_refs=tuple(payload.get("evidence_refs") or ()))
    return {"status": "ok", "action": StoreBackedInvestmentOpportunityCandidateService().propose_follow_up_action(action, context)}

def replay(*, ctx: Any, candidate_id: str) -> dict[str, Any]:
    return {"status": "ok", "replay": StoreBackedInvestmentOpportunityCandidateService().build_replay_envelope(candidate_id, runtime_context(ctx)).__dict__}
