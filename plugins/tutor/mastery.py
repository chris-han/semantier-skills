"""Recency-weighted estimate for eligible, chronologically ordered assessments."""
from __future__ import annotations

from datetime import datetime

from .practice import next_review

# Recency weights for the most recent attempts (oldest -> newest). Newer
# attempts count more, so recovery after early mistakes is rewarded.
_RECENCY_WEIGHTS: tuple[float, ...] = (0.5, 0.7, 0.85, 0.95, 1.0)

# Mastery cannot exceed this until enough attempts accumulate, so one or two
# correct answers cannot declare a point "mastered".
_CONFIDENCE_CAP: dict[int, float] = {1: 0.5, 2: 0.8}


def compute_mastery(correctness: list[bool | float]) -> float:
    """Return a 0..1 mastery score from a knowledge point's attempt outcomes.

    Args:
        correctness: per-attempt correctness or bounded partial credit, chronologically.
    """
    for value in correctness:
        if not isinstance(value, (int, float)) or not 0 <= value <= 1:
            raise ValueError("assessment credit must be within [0, 1]")
    if not correctness:
        return 0.0
    recent = correctness[-len(_RECENCY_WEIGHTS) :]
    weights = _RECENCY_WEIGHTS[-len(recent) :]
    score = sum(
        w * float(c) for c, w in zip(recent, weights, strict=True)
    ) / sum(weights)
    return min(score, _CONFIDENCE_CAP.get(len(recent), 1.0))


__all__ = ["compute_mastery"]


def objective_progress(objective):
    """Project only current, independently graded attempts into the estimate."""
    if objective["status"] != "current":
        return {"estimate": None, "status": "evidence_unavailable", "contributing_assessments": []}
    assessments = objective["assessments"]
    eligible = [item for item in assessments if item["result"] in {"correct", "incorrect"}
                and item["assistance"] == "independent"]
    recent = eligible[-len(_RECENCY_WEIGHTS):]
    next_review_at = None
    if eligible:
        last = eligible[-1]
        # An incorrect independent answer returns the objective to its initial interval.
        streak = 0
        for item in reversed(eligible):
            if item["result"] != "correct":
                break
            streak += 1
        due = next_review(datetime.fromisoformat(last["submitted_at"]), objective["knowledge_type"],
                          max(streak - 1, 0))
        next_review_at = due.isoformat()
    return {
        "next_review_at": next_review_at,
        "status": "estimated" if recent else "not_demonstrated",
        "estimate": compute_mastery([item["result"] == "correct" for item in recent]) if recent else None,
        "independent_evidence_count": len(eligible),
        "assisted_attempt_count": sum(item["assistance"] == "hinted" for item in assessments),
        "contributing_assessments": [item["assessment"] for item in recent],
    }
