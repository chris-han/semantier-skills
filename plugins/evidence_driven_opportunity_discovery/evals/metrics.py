from __future__ import annotations

from math import log2


def precision_at_k(labels: list[int], scores: list[float], k: int) -> float:
    if k <= 0:
        raise ValueError("K_MUST_BE_POSITIVE")
    ranked = sorted(zip(scores, labels), reverse=True)[:k]
    if not ranked:
        return 0.0
    return sum(int(label > 0) for _, label in ranked) / len(ranked)


def recall_at_k(labels: list[int], scores: list[float], k: int) -> float:
    positives = sum(int(label > 0) for label in labels)
    if positives == 0:
        return 0.0
    ranked = sorted(zip(scores, labels), reverse=True)[:k]
    return sum(int(label > 0) for _, label in ranked) / positives


def ndcg_at_k(labels: list[float], scores: list[float], k: int) -> float:
    if k <= 0:
        raise ValueError("K_MUST_BE_POSITIVE")

    def dcg(values: list[float]) -> float:
        return sum((2.0 ** relevance - 1.0) / log2(index + 2.0) for index, relevance in enumerate(values[:k]))

    ranked = [label for _, label in sorted(zip(scores, labels), reverse=True)]
    ideal = sorted(labels, reverse=True)
    denominator = dcg(ideal)
    return 0.0 if denominator == 0 else dcg(ranked) / denominator


def binary_precision(gold: list[bool], predicted: list[bool]) -> float:
    if len(gold) != len(predicted):
        raise ValueError("LENGTH_MISMATCH")
    tp = sum(g and p for g, p in zip(gold, predicted))
    predicted_positive = sum(predicted)
    return 0.0 if predicted_positive == 0 else tp / predicted_positive


def binary_recall(gold: list[bool], predicted: list[bool]) -> float:
    if len(gold) != len(predicted):
        raise ValueError("LENGTH_MISMATCH")
    tp = sum(g and p for g, p in zip(gold, predicted))
    positives = sum(gold)
    return 0.0 if positives == 0 else tp / positives


def unsupported_claim_rate(total_claims: int, unsupported_claims: int) -> float:
    if total_claims < 0 or unsupported_claims < 0 or unsupported_claims > total_claims:
        raise ValueError("INVALID_CLAIM_COUNTS")
    return 0.0 if total_claims == 0 else unsupported_claims / total_claims


def gtm_information_yield(validated_hypotheses: int, human_attention_units: float) -> float:
    if human_attention_units <= 0:
        raise ValueError("ATTENTION_MUST_BE_POSITIVE")
    return validated_hypotheses / human_attention_units


def uplift_policy_value(treatment: list[int], outcome: list[int], selected: list[bool]) -> float:
    """Simple difference-in-means policy estimator for randomized evaluation fixtures.

    Production Track C may replace this with AUUC/Qini estimators; this helper exists
    to keep the first deterministic benchmark executable without pretending to be a
    full causal-inference package.
    """
    selected_rows = [(t, y) for t, y, use in zip(treatment, outcome, selected) if use]
    treated = [y for t, y in selected_rows if t == 1]
    control = [y for t, y in selected_rows if t == 0]
    if not treated or not control:
        return 0.0
    return sum(treated) / len(treated) - sum(control) / len(control)
