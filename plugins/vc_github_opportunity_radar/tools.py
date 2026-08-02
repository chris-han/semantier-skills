from __future__ import annotations

import json
from typing import Any

from contracts.investment_opportunity import OpportunityCandidateActionDTO, OpportunityCandidateSubmitDTO, RadarUniverseCandidateDTO, RuntimeContextDTO

from .adapters.github import GitHubAdapter
from .entity_resolution import resolve_repository
from .features import calculate_features
from .scoring import score_snapshot
from .store import ObservationStore

_STORE = ObservationStore()

def _ok(result: Any) -> str: return json.dumps({"ok": True, "result": result}, sort_keys=True, default=str)
def _error(code: str, message: str | None = None) -> str: return json.dumps({"ok": False, "error_code": code, **({"message": message} if message else {})}, sort_keys=True)
def _context(kwargs: dict[str, Any]) -> RuntimeContextDTO:
    value = kwargs.get("runtime_context") or kwargs.get("context")
    if isinstance(value, RuntimeContextDTO): return value
    if isinstance(value, dict) and value.get("organization_id") and value.get("actor_id"):
        return RuntimeContextDTO(organization_id=str(value["organization_id"]), workspace_id=value.get("workspace_id"), actor_id=str(value["actor_id"]), actor_role=value.get("actor_role"), channel=value.get("channel"), session_id=value.get("session_id"), capabilities=tuple(value.get("capabilities") or ()))
    raise RuntimeError("TRUSTED_RUNTIME_CONTEXT_REQUIRED")
def _require(context: RuntimeContextDTO, capability: str) -> None:
    if context.capabilities and capability not in context.capabilities:
        raise RuntimeError(f"CAPABILITY_REQUIRED:{capability}")
def _adapter(kwargs):
    token = kwargs.get("github_token")
    if token is not None: raise RuntimeError("SECRET_MUST_USE_GOVERNED_REFERENCE")
    return kwargs.get("github_adapter") or GitHubAdapter()
def _candidate_service(kwargs):
    if kwargs.get("candidate_service") is not None: return kwargs["candidate_service"]
    from services.investment_opportunity_candidate_service import StoreBackedInvestmentOpportunityCandidateService
    return StoreBackedInvestmentOpportunityCandidateService()
def _configuration_service(kwargs):
    if kwargs.get("radar_configuration_service") is not None: return kwargs["radar_configuration_service"]
    from services.investment_radar_configuration_service import StoreBackedInvestmentRadarConfigurationService
    return StoreBackedInvestmentRadarConfigurationService()
def create_universe(args, **kwargs):
    try:
        context = _context(kwargs)
        _require(context, "investment.radar.configuration.propose")
        payload = RadarUniverseCandidateDTO(universe_candidate_id="draft", organization_id=context.organization_id, name=str(args.get("name") or ""), scope="user", owner_ref=context.actor_id, source_filters=dict(args.get("source_filters") or {}), exclusions=dict(args.get("exclusions") or {}), operational_limits={k: int(v) for k, v in dict(args.get("operational_limits") or {}).items()})
        return _ok(_configuration_service(kwargs).propose_universe(payload, context))
    except (RuntimeError, ValueError) as exc: return _error(str(exc))
def inspect_target(args, **kwargs):
    try:
        target = str(args.get("repository") or "").strip()
        if not target: return _error("REPOSITORY_REQUIRED")
        observation = _adapter(kwargs).get_repository(target)
        _STORE.append(observation)
        return _ok(observation)
    except (RuntimeError, ValueError) as exc: return _error(str(exc))
def scan_universe(args, **kwargs):
    targets = []
    universe = args.get("universe") or {}
    targets.extend(universe.get("repositories", []))
    if args.get("repository"): targets.append(args["repository"])
    if not targets and args.get("topic"):
        page = int((args.get("cursor") or {}).get("page", 1))
        query = f"topic:{args['topic']}" + (f" language:{args['language']}" if args.get("language") else "")
        limit = min(int(args.get("max_targets") or 30), 100)
        search = _adapter(kwargs).search_repositories(query, page=page, per_page=limit)
        targets.extend(item["github_observation"]["source_ref"].removeprefix("github:repo:") for item in search.get("items", []))
    if not targets: return _error("BOUNDED_TARGET_REQUIRED")
    limit = min(int(args.get("max_targets") or len(targets)), 100)
    run = _STORE.start_run(universe_ref=str((universe.get("name") or "one_time")), budget=limit)
    results = [json.loads(inspect_target({"repository": target}, **kwargs)) for target in targets[:limit]]
    _STORE.checkpoint(run["run_id"], {"page": int((args.get("cursor") or {}).get("page", 1)) + 1, "completed": True})
    summary = _STORE.finish_run(run["run_id"], status="COMPLETED", processed=len(results))
    return _ok({"status": "COMPLETED", "partial": len(targets) > limit, "run": summary, "observations": results})
def score_target(args, **kwargs):
    try:
        snapshot = calculate_features(args["observation"])
        oso = kwargs.get("oso_adapter")
        if oso is not None:
            enrichment = oso.enrich(snapshot.get("target_ref", ""))
            snapshot["quality"]["warnings"].extend([] if enrichment.get("status") == "OK" else [str(enrichment.get("reason_code", "OSO_UNAVAILABLE"))])
            if enrichment.get("metrics", {}).get("dependency_impact") is not None:
                snapshot["features"]["dependency_impact"] = float(enrichment["metrics"]["dependency_impact"])
        return _ok({"feature_snapshot": snapshot, "scorecard": score_snapshot(snapshot, args.get("profile"))})
    except (KeyError, TypeError, ValueError) as exc: return _error("OBSERVATION_INVALID", str(exc))
def propose_candidate(args, **kwargs):
    try:
        context = _context(kwargs); candidate = dict(args["candidate"])
        _require(context, "investment.radar.candidate.submit")
        payload = OpportunityCandidateSubmitDTO(organization_id=context.organization_id, candidate_type=str(candidate.get("candidate_type", "emerging_project")), target=dict(candidate.get("target") or {}), detected_at=str(candidate.get("detected_at") or ""), observation_refs=tuple(candidate.get("observation_refs") or ()), scorecard_ref=str(candidate.get("scorecard_ref") or ""), signal_claims=tuple(candidate.get("signal_claims") or ()), missing_evidence=tuple(candidate.get("missing_evidence") or ()), proposed_next_actions=tuple(candidate.get("proposed_next_actions") or ()), justification=dict(candidate.get("justification") or {}))
        return _ok(_candidate_service(kwargs).submit_candidate_idempotent(payload, context))
    except (RuntimeError, ValueError, KeyError) as exc: return _error(str(exc))
def list_candidates(args, **kwargs):
    try:
        context = _context(kwargs)
        _require(context, "investment.radar.candidate.read")
        return _ok(_candidate_service(kwargs).list_candidates(context, args.get("filters")))
    except (RuntimeError, ValueError) as exc: return _error(str(exc))
def request_research(args, **kwargs):
    try:
        context = _context(kwargs)
        _require(context, "investment.radar.action.propose")
        action = OpportunityCandidateActionDTO(candidate_id=str(args["candidate_id"]), action_scope="OPPORTUNITY_ENRICHMENT_REQUEST", reason=str(args["reason"]), trigger={"research_type": str(args["research_type"])})
        proposal = _candidate_service(kwargs).propose_follow_up_action(action, context)
        dispatcher = kwargs.get("research_dispatcher")
        if dispatcher is not None:
            handoff = dispatcher(action=action, context=context)
            if not isinstance(handoff, dict) or "institutional_findings" in handoff:
                raise RuntimeError("RESEARCH_HANDOFF_MUST_RETURN_EVIDENCE_CANDIDATES")
            evidence = handoff.get("evidence_candidates", [])
            if not isinstance(evidence, list) or any(
                not isinstance(item, dict) or item.get("status") != "EVIDENCE_CANDIDATE"
                for item in evidence
            ):
                raise RuntimeError("RESEARCH_EVIDENCE_CANDIDATE_INVALID")
            proposal["handoff"] = {"status": "EVIDENCE_CANDIDATES_RETURNED", "evidence_candidates": evidence}
        else:
            proposal["handoff"] = {
                "status": "AWAITING_RESEARCH_DISPATCH",
                "evidence_candidates": proposal.pop("evidence_candidates", []),
                "institutional_findings": [],
            }
        return _ok(proposal)
    except (RuntimeError, ValueError, KeyError) as exc: return _error(str(exc))
def schedule_scan(args, **kwargs):
    try:
        context = _context(kwargs)
        _require(context, "investment.radar.schedule.create")
        from .scheduler import create_scan_schedule
        return _ok(create_scan_schedule(schedule=str(args.get("schedule") or ""), name=str(args.get("name") or "GitHub opportunity radar"), universe_ref=str(args.get("universe_ref") or ""), max_targets=int(args.get("max_targets") or 25), cron_client=kwargs.get("cron_client")))
    except (RuntimeError, ValueError, KeyError) as exc: return _error(str(exc))
