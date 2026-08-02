from __future__ import annotations

from collections import Counter
from typing import Any

from eos.artifact_hashing import content_hash


def evaluate_cases(cases: list[dict[str, Any]], *, review_budget: int) -> dict[str, Any]:
    """Offline case-scoped evaluation; it never mutates an active profile."""
    reviewed = cases[: max(0, review_budget)]
    positives = sum(1 for case in reviewed if case.get("outcome") == "qualified")
    duplicates = sum(1 for case in cases if case.get("duplicate"))
    replay_stable = all(case.get("replay_hash") == case.get("reconstructed_hash") for case in cases if case.get("replay_hash") is not None)
    return {
        "evaluation_version": "vc_github_evaluation_v1",
        "review_budget": review_budget,
        "precision_at_review_budget": positives / len(reviewed) if reviewed else None,
        "candidate_freshness": sum(1 for case in cases if case.get("fresh")) / len(cases) if cases else None,
        "duplicate_rate": duplicates / len(cases) if cases else 0.0,
        "entity_resolution_accuracy": sum(1 for case in cases if case.get("entity_resolution_correct")) / len(cases) if cases else None,
        "missing_data_honesty": all(case.get("missing_data_honest", False) for case in cases),
        "replay_determinism": replay_stable,
        "outcome_counts": dict(Counter(str(case.get("outcome", "unreviewed")) for case in cases)),
        "content_hash": content_hash({"cases": cases, "review_budget": review_budget}),
    }


def score_drift(before: dict[str, Any], after: dict[str, Any], *, material_change_threshold: float = 0.1) -> dict[str, Any]:
    deltas = {}
    for target_ref in sorted(set(before) | set(after)):
        old = before.get(target_ref)
        new = after.get(target_ref)
        if isinstance(old, (int, float)) and isinstance(new, (int, float)):
            deltas[target_ref] = {"before": old, "after": new, "delta": new - old, "material": abs(new - old) >= material_change_threshold}
    return {"status": "MATERIAL_DRIFT" if any(item["material"] for item in deltas.values()) else "NO_MATERIAL_DRIFT", "threshold": material_change_threshold, "deltas": deltas, "content_hash": content_hash(deltas)}


def derive_change_candidates(cases: list[dict[str, Any]], *, min_repetitions: int = 2) -> list[dict[str, Any]]:
    """Emit non-authoritative T6 change candidates from repeated outcomes."""
    patterns: Counter[tuple[str, str]] = Counter(
        (str(case.get("outcome")), str(case.get("pattern")))
        for case in cases
        if case.get("outcome") and case.get("pattern")
    )
    result = []
    for (outcome, pattern), count in sorted(patterns.items()):
        if count < min_repetitions:
            continue
        payload = {
            "candidate_type": "investment_radar_change_candidate",
            "semantic_tier": "T6",
            "governance_state": "proposed",
            "outcome": outcome,
            "pattern": pattern,
            "repeat_count": count,
            "case_refs": sorted(str(case.get("case_ref")) for case in cases if case.get("outcome") == outcome and case.get("pattern") == pattern and case.get("case_ref")),
            "institutional_mutation": False,
        }
        result.append({**payload, "content_hash": content_hash(payload)})
    return result
