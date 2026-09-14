from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

from .metrics import binary_precision, binary_recall, unsupported_claim_rate


@dataclass(frozen=True)
class EvalRunPins:
    baseline: str
    model: str | None = None
    runtime: str | None = None
    tool_budget: str | None = None
    prompt_or_skill_hash: str | None = None


def file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _case_by_id(cases: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(case["case_id"]): case for case in cases}


def evaluate_track_a(cases: list[dict[str, Any]], predictions: list[dict[str, Any]]) -> dict[str, float]:
    gold = _case_by_id(cases)
    predicted = _case_by_id(predictions)
    missing = sorted(set(gold) - set(predicted))
    extra = sorted(set(predicted) - set(gold))
    if missing or extra:
        raise ValueError(f"CASE_SET_MISMATCH:missing={missing}:extra={extra}")

    gold_valid = []
    predicted_valid = []
    grounding_gold = []
    grounding_predicted = []
    contradiction_gold = []
    contradiction_predicted = []
    total_claims = 0
    unsupported = 0

    for case_id, case in gold.items():
        prediction = predicted[case_id]
        expected = case["gold"]
        gold_valid.append(bool(expected["valid_opportunity"]))
        predicted_valid.append(bool(prediction.get("valid_opportunity")))

        gold_support = set(expected.get("supporting_refs") or [])
        predicted_support = set(prediction.get("supporting_refs") or [])
        universe = sorted(gold_support | predicted_support)
        grounding_gold.extend(ref in gold_support for ref in universe)
        grounding_predicted.extend(ref in predicted_support for ref in universe)

        gold_contra = set(expected.get("contradicting_refs") or [])
        predicted_contra = set(prediction.get("contradicting_refs") or [])
        contra_universe = sorted(gold_contra | predicted_contra)
        contradiction_gold.extend(ref in gold_contra for ref in contra_universe)
        contradiction_predicted.extend(ref in predicted_contra for ref in contra_universe)

        claims = list(prediction.get("claims") or [])
        total_claims += len(claims)
        unsupported += sum(not bool(claim.get("supported")) for claim in claims if isinstance(claim, dict))

    return {
        "hypothesis_precision": binary_precision(gold_valid, predicted_valid),
        "hypothesis_recall": binary_recall(gold_valid, predicted_valid),
        "evidence_grounding_precision": binary_precision(grounding_gold, grounding_predicted) if grounding_gold or grounding_predicted else 1.0,
        "contradiction_recall": binary_recall(contradiction_gold, contradiction_predicted) if contradiction_gold else 1.0,
        "unsupported_claim_rate": unsupported_claim_rate(total_claims, unsupported),
    }


def deterministic_track_a_baseline(cases: list[dict[str, Any]], baseline: str) -> list[dict[str, Any]]:
    if baseline not in {"B0_random_seed0", "B1_keyword_heuristic"}:
        raise ValueError("UNSUPPORTED_DETERMINISTIC_BASELINE")
    predictions = []
    for index, case in enumerate(cases):
        observations = case.get("observations") or []
        if baseline == "B0_random_seed0":
            valid = index % 2 == 0
            support = [observations[0]["ref"]] if valid and observations else []
        else:
            text = " ".join(str(obs.get("claim") or "").lower() for obs in observations)
            keywords = ("governance", "audit", "regulatory", "damage", "deterioration", "addressable need")
            valid = any(keyword in text for keyword in keywords)
            support = [obs["ref"] for obs in observations if valid]
        predictions.append({
            "case_id": case["case_id"],
            "valid_opportunity": valid,
            "supporting_refs": support,
            "contradicting_refs": [],
            "claims": [{"text": "baseline opportunity classification", "supported": bool(support) or not valid}],
        })
    return predictions


def run_track_a(*, cases_path: Path, pins: EvalRunPins, predictions_path: Path | None = None) -> dict[str, Any]:
    cases = json.loads(cases_path.read_text())
    if predictions_path is None:
        predictions = deterministic_track_a_baseline(cases, pins.baseline)
        prediction_hash = sha256(json.dumps(predictions, sort_keys=True).encode()).hexdigest()
    else:
        predictions = json.loads(predictions_path.read_text())
        prediction_hash = file_sha256(predictions_path)

    return {
        "benchmark": "EOD-Bench",
        "benchmark_version": "1.0.0-draft",
        "track": "A",
        "pins": {
            "baseline": pins.baseline,
            "model": pins.model,
            "runtime": pins.runtime,
            "tool_budget": pins.tool_budget,
            "prompt_or_skill_hash": pins.prompt_or_skill_hash,
        },
        "provenance": {
            "cases_path": str(cases_path),
            "cases_sha256": file_sha256(cases_path),
            "predictions_path": str(predictions_path) if predictions_path else None,
            "predictions_sha256": prediction_hash,
            "case_count": len(cases),
        },
        "metrics": evaluate_track_a(cases, predictions),
    }


def write_report(report: dict[str, Any], output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return output_path
