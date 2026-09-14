from __future__ import annotations

from dataclasses import asdict

from .schemas import validate_prediction


def execute_adjacent(*, executor_b2, executor_b3, cases, manifest_b2, manifest_b3, repeat_index: int):
    left = []
    right = []
    order_log = []
    for index, case in enumerate(cases):
        order = ("B2", "B3") if (index + repeat_index) % 2 == 0 else ("B3", "B2")
        current = {}
        for arm in order:
            executor = executor_b2 if arm == "B2" else executor_b3
            manifest = manifest_b2 if arm == "B2" else manifest_b3
            current[arm] = asdict(validate_prediction(executor.run_case(case=case, manifest=manifest)))
        left.append(current["B2"])
        right.append(current["B3"])
        order_log.append({"case_id": case["case_id"], "first": order[0], "second": order[1]})
    return {
        "repeat_index": repeat_index,
        "execution_order": order_log,
        "b2": {"predictions": left},
        "b3": {"predictions": right},
    }
