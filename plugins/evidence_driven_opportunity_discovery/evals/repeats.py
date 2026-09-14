from __future__ import annotations

from math import sqrt
from statistics import mean, stdev
from typing import Any


def aggregate_metric_repeats(reports: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    if len(reports) < 2:
        raise ValueError("AT_LEAST_TWO_REPEATS_REQUIRED")
    metric_names = set(reports[0]["metrics"])
    if any(set(report["metrics"]) != metric_names for report in reports):
        raise ValueError("REPEAT_METRIC_SCHEMA_MISMATCH")
    result: dict[str, dict[str, float]] = {}
    for name in sorted(metric_names):
        values = [float(report["metrics"][name]) for report in reports]
        result[name] = {
            "mean": mean(values),
            "stddev": stdev(values),
            "min": min(values),
            "max": max(values),
        }
    return result


def paired_mean_difference(b2_values: list[float], b3_values: list[float]) -> dict[str, float]:
    if len(b2_values) != len(b3_values) or not b2_values:
        raise ValueError("PAIRED_REPEAT_LENGTH_MISMATCH")
    diffs = [b3 - b2 for b2, b3 in zip(b2_values, b3_values)]
    spread = 0.0 if len(diffs) == 1 else stdev(diffs)
    standard_error = spread / sqrt(len(diffs)) if len(diffs) > 1 else 0.0
    return {
        "mean_difference_b3_minus_b2": mean(diffs),
        "stddev_difference": spread,
        "standard_error": standard_error,
        "repeat_count": float(len(diffs)),
    }


def aggregate_usage(predictions: list[dict[str, Any]]) -> dict[str, float]:
    if not predictions:
        return {"input_tokens": 0.0, "output_tokens": 0.0, "reasoning_tokens": 0.0, "tool_calls": 0.0, "wall_clock_ms": 0.0}
    keys = ("input_tokens", "output_tokens", "reasoning_tokens", "tool_calls", "wall_clock_ms")
    totals = {key: 0.0 for key in keys}
    for prediction in predictions:
        usage = prediction.get("usage") or {}
        for key in keys:
            totals[key] += float(usage.get(key) or 0.0)
    return totals
