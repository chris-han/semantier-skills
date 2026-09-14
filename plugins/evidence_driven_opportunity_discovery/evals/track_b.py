from __future__ import annotations

import csv
from hashlib import sha256
import io
import math
from pathlib import Path
from typing import Iterable
import zipfile

from .metrics import precision_at_k, recall_at_k, ndcg_at_k


def file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_float(value: str) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _robust_numeric_score(row: dict[str, str], *, excluded: set[str]) -> float:
    values = []
    for key, raw in row.items():
        if key in excluded:
            continue
        value = _safe_float(raw)
        if value is not None:
            values.append(math.tanh(value / 1000.0))
    return sum(values) / max(len(values), 1)


def _evaluate(labels: list[int], scores: list[float], *, fraction: float = 0.1) -> dict[str, float]:
    if len(labels) != len(scores) or not labels:
        raise ValueError("TRACK_B_ROWS_INVALID")
    k = max(1, int(len(labels) * fraction))
    return {
        "row_count": float(len(labels)),
        "positive_count": float(sum(labels)),
        "k": float(k),
        "precision_at_k": precision_at_k(labels, scores, k),
        "recall_at_k": recall_at_k(labels, scores, k),
        "ndcg_at_k": ndcg_at_k(labels, scores, k),
    }


def evaluate_online_shoppers_zip(path: Path) -> dict:
    with zipfile.ZipFile(path) as outer:
        name = next(name for name in outer.namelist() if name.endswith(".csv"))
        text = io.TextIOWrapper(outer.open(name), encoding="utf-8", newline="")
        rows = list(csv.DictReader(text))
    labels = [1 if str(row.get("Revenue", "")).strip().lower() == "true" else 0 for row in rows]
    scores = [_robust_numeric_score(row, excluded={"Revenue"}) for row in rows]
    return {
        "dataset": "uci_online_shoppers",
        "raw_sha256": file_sha256(path),
        "feature_exclusions": ["Revenue"],
        "metrics": _evaluate(labels, scores),
    }


def _read_nested_bank_csv(path: Path) -> list[dict[str, str]]:
    with zipfile.ZipFile(path) as outer:
        nested_bytes = outer.read("bank.zip")
    with zipfile.ZipFile(io.BytesIO(nested_bytes)) as nested:
        name = next(name for name in nested.namelist() if name.endswith("bank-full.csv"))
        text = io.TextIOWrapper(nested.open(name), encoding="utf-8", newline="")
        return list(csv.DictReader(text, delimiter=";"))


def evaluate_bank_marketing_zip(path: Path) -> dict:
    rows = _read_nested_bank_csv(path)
    labels = [1 if str(row.get("y", "")).strip().lower() == "yes" else 0 for row in rows]
    # `duration` is excluded because it is known only after the marketing contact and
    # would leak post-contact information into a pre-action ranking benchmark.
    exclusions = {"y", "duration"}
    scores = [_robust_numeric_score(row, excluded=exclusions) for row in rows]
    return {
        "dataset": "uci_bank_marketing",
        "raw_sha256": file_sha256(path),
        "feature_exclusions": sorted(exclusions),
        "metrics": _evaluate(labels, scores),
    }


def _read_kdd_matrix(path: Path) -> tuple[list[str], list[list[str]]]:
    with zipfile.ZipFile(path) as archive:
        name = next(name for name in archive.namelist() if name.endswith(".data"))
        text = io.TextIOWrapper(archive.open(name), encoding="utf-8", newline="")
        reader = csv.reader(text, delimiter="\t")
        header = next(reader)
        rows = list(reader)
    return header, rows


def evaluate_kdd_orange_small(path: Path, labels_path: Path) -> dict:
    header, rows = _read_kdd_matrix(path)
    labels_raw = [line.strip() for line in labels_path.read_text().splitlines() if line.strip()]
    if len(rows) != len(labels_raw):
        raise ValueError("KDD_LABEL_ROW_MISMATCH")
    labels = [1 if value == "1" else 0 for value in labels_raw]
    scores = []
    for row in rows:
        values = []
        for raw in row[:190]:  # official small-set split: first 190 variables numeric
            value = _safe_float(raw)
            if value is not None:
                values.append(math.tanh(value / 1000.0))
        scores.append(sum(values) / max(len(values), 1))
    return {
        "dataset": "kdd_cup_2009_orange_small_appetency",
        "raw_sha256": file_sha256(path),
        "labels_sha256": file_sha256(labels_path),
        "feature_count": len(header),
        "metrics": _evaluate(labels, scores),
    }
