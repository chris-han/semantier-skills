from __future__ import annotations

from dataclasses import asdict
from typing import Any, Protocol

from .schemas import EvalRunManifest, validate_prediction


class EvalExecutor(Protocol):
    def run_case(
        self,
        *,
        case: dict[str, Any],
        manifest: EvalRunManifest,
    ) -> dict[str, Any]: ...


def execute_arm(
    *,
    executor: EvalExecutor,
    cases: list[dict[str, Any]],
    manifest: EvalRunManifest,
) -> dict[str, Any]:
    predictions = []
    for case in cases:
        raw = executor.run_case(case=case, manifest=manifest)
        prediction = validate_prediction(raw)
        if prediction.case_id != str(case["case_id"]):
            raise ValueError("EXECUTOR_CASE_ID_MISMATCH")
        predictions.append(asdict(prediction))
    return {
        "manifest": manifest.to_dict(),
        "predictions": predictions,
    }


def execute_paired_repeat(
    *,
    executor_b2: EvalExecutor,
    executor_b3: EvalExecutor,
    cases: list[dict[str, Any]],
    manifest_b2: EvalRunManifest,
    manifest_b3: EvalRunManifest,
) -> dict[str, Any]:
    if manifest_b2.repeat_index != manifest_b3.repeat_index:
        raise ValueError("PAIRED_REPEAT_INDEX_MISMATCH")
    return {
        "repeat_index": manifest_b2.repeat_index,
        "b2": execute_arm(executor=executor_b2, cases=cases, manifest=manifest_b2),
        "b3": execute_arm(executor=executor_b3, cases=cases, manifest=manifest_b3),
    }
