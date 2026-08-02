from __future__ import annotations

from typing import Any
from datetime import datetime, timedelta
from eos.artifact_hashing import content_hash

FEATURE_SPEC_VERSION = "vc_github_features_v1"

def _ratio(a: Any, b: Any) -> float | None:
    if a is None or b in (None, 0): return None
    return float(a) / float(b)


def _window_velocity(history: list[dict[str, Any]], days: int) -> float | None:
    if len(history) < 2:
        return None
    points = sorted(history, key=lambda item: str(item.get("observed_at") or ""))
    latest = points[-1]
    cutoff = datetime.fromisoformat(str(latest["observed_at"]).replace("Z", "+00:00")) - timedelta(days=days)
    prior = [item for item in points[:-1] if datetime.fromisoformat(str(item["observed_at"]).replace("Z", "+00:00")) <= cutoff]
    if not prior:
        return None
    return (float(latest["stars"]) - float(prior[-1]["stars"])) / float(days)

def calculate_features(observation: dict[str, Any], *, window: str = "90d") -> dict[str, Any]:
    data = observation.get("github_observation", observation)
    counters = data.get("counters", {})
    repo = data.get("repository", {})
    activity = data.get("sampled_activity", {})
    history = list(data.get("history", []) or [])
    window_days = int(str(window).removesuffix("d"))
    star_velocity = _window_velocity(history, window_days)
    short_velocity = _window_velocity(history, 30)
    long_velocity = _window_velocity(history, 180)
    features = {
        "star_velocity": star_velocity, "star_acceleration": (short_velocity - long_velocity) if short_velocity is not None and long_velocity is not None else None,
        "contributor_growth": None, "contributor_concentration": _ratio(1, activity.get("distinct_commit_authors")),
        "release_cadence": activity.get("releases"), "issue_response_health": None,
        "fork_conversion_proxy": _ratio(counters.get("forks"), counters.get("stars")),
        "organization_repo_growth": None, "enterprise_contributor_proxy": None,
        "commercial_intent_proxy": None, "dependency_impact": None,
        "maintenance_risk": 1.0 if repo.get("archived") else 0.0,
    }
    missing = [name for name, value in features.items() if value is None]
    completeness = (len(features) - len(missing)) / len(features)
    snapshot = {"feature_snapshot_id": data.get("provenance", {}).get("selected_field_hash", "")[7:23], "target_ref": data.get("source_ref", ""), "feature_spec_version": FEATURE_SPEC_VERSION, "window": window, "features": features, "quality": {"completeness": completeness, "stale": bool(repo.get("archived")), "rate_limited": False, "warnings": missing}}
    snapshot["content_hash"] = content_hash(snapshot)
    return snapshot
