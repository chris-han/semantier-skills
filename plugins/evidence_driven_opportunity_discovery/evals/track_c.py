from __future__ import annotations

import csv
import gzip
from hashlib import sha256
from pathlib import Path
from typing import Iterable


def file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _curve(rows: list[dict], *, score_key: str) -> list[tuple[float, float]]:
    ranked = sorted(rows, key=lambda row: float(row[score_key]), reverse=True)
    total = len(ranked)
    treated_y = control_y = treated_n = control_n = 0.0
    points = [(0.0, 0.0)]
    for index, row in enumerate(ranked, start=1):
        treatment = int(row["treatment"])
        outcome = int(row["outcome"])
        if treatment:
            treated_y += outcome
            treated_n += 1
        else:
            control_y += outcome
            control_n += 1
        if index == total or index % max(1, total // 100) == 0:
            expected_control = 0.0 if control_n == 0 else (control_y / control_n) * treated_n
            gain = treated_y - expected_control
            points.append((index / total, gain))
    return points


def _area(points: list[tuple[float, float]]) -> float:
    return sum((x2 - x1) * (y1 + y2) / 2.0 for (x1, y1), (x2, y2) in zip(points, points[1:]))


def qini_coefficient(rows: list[dict], *, score_key: str = "score") -> float:
    curve = _curve(rows, score_key=score_key)
    actual = _area(curve)
    end_x, end_y = curve[-1]
    random_area = end_x * end_y / 2.0
    return actual - random_area


def auuc(rows: list[dict], *, score_key: str = "score") -> float:
    return _area(_curve(rows, score_key=score_key))


def policy_value_at_fraction(rows: list[dict], *, fraction: float = 0.1, score_key: str = "score") -> float:
    if not rows:
        return 0.0
    k = max(1, int(len(rows) * fraction))
    selected = sorted(rows, key=lambda row: float(row[score_key]), reverse=True)[:k]
    treated = [int(row["outcome"]) for row in selected if int(row["treatment"]) == 1]
    control = [int(row["outcome"]) for row in selected if int(row["treatment"]) == 0]
    if not treated or not control:
        return 0.0
    return sum(treated) / len(treated) - sum(control) / len(control)


def _iter_criteo(path: Path, *, limit: int | None = None) -> Iterable[dict]:
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for index, row in enumerate(reader):
            if limit is not None and index >= limit:
                break
            features = [float(row[f"f{i}"]) for i in range(12)]
            # Deterministic, model-free baseline score. It is intentionally simple:
            # the benchmark harness measures uplift metrics, not this score's merit.
            score = sum(features[:4]) / 4.0
            yield {
                "row_id": str(index),
                "treatment": int(row["treatment"]),
                "outcome": int(row["conversion"]),
                "exposure": int(row.get("exposure", 0) or 0),
                "score": score,
            }


def evaluate_criteo(path: Path, *, limit: int | None = None) -> dict:
    rows = list(_iter_criteo(path, limit=limit))
    if not rows:
        raise ValueError("CRITEO_ROWS_REQUIRED")
    return {
        "dataset": "criteo_uplift_unbiased",
        "raw_sha256": file_sha256(path),
        "sampled_rows": len(rows),
        "metrics": {
            "auuc": auuc(rows),
            "qini": qini_coefficient(rows),
            "policy_value_at_10pct": policy_value_at_fraction(rows, fraction=0.1),
        },
    }
