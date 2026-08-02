from __future__ import annotations

from eos.artifact_hashing import content_hash

DEFAULT_PROFILE = {"version": "vc_github_profile_v1", "dimension_weights": {"momentum": .30, "community_quality": .20, "technical_delivery": .20, "commercial_intent": .20, "diligence_risk": .10}, "thresholds": {"minimum_completeness": .60, "candidate_review_threshold": .55}}

def score_snapshot(snapshot: dict, profile: dict | None = None) -> dict:
    profile = profile or DEFAULT_PROFILE
    features = snapshot.get("features", {})
    quality = snapshot.get("quality", {})
    reasons = {}
    momentum = features.get("star_velocity")
    community = features.get("contributor_growth")
    technical = features.get("release_cadence")
    commercial = features.get("commercial_intent_proxy")
    risk = features.get("maintenance_risk")
    dimensions = {"momentum": momentum, "community_quality": community, "technical_delivery": technical, "commercial_intent": commercial, "diligence_risk": risk}
    for name, value in dimensions.items(): reasons[name] = ["value_missing"] if value is None else ["derived_from_feature_snapshot"]
    coverage = float(quality.get("completeness", 0))
    scores = {name: float(value) if isinstance(value, (int, float)) else None for name, value in dimensions.items()}
    composite = None
    if coverage >= float(profile.get("thresholds", {}).get("minimum_completeness", 1.0)):
        known = [(name, value, float(profile.get("dimension_weights", {}).get(name, 0))) for name, value in scores.items() if value is not None]
        if known: composite = sum(value * weight for _, value, weight in known) / sum(weight for _, _, weight in known)
    result = {"scorecard_id": content_hash({"snapshot": snapshot, "profile": profile}), "target_ref": snapshot.get("target_ref"), "scoring_profile_ref": profile.get("name", "exploratory"), "scoring_profile_version": profile.get("version", "exploratory"), "feature_snapshot_ref": snapshot.get("feature_snapshot_id"), "dimensions": {name: {"score": scores[name], "reasons": reasons[name]} for name in scores}, "composite_score": composite, "confidence": coverage, "missing_evidence": list(quality.get("warnings", [])), "disqualifiers": ["archived_repository"] if features.get("maintenance_risk") == 1 else [], "calculation_hash": ""}
    result["calculation_hash"] = content_hash(result)
    return result
