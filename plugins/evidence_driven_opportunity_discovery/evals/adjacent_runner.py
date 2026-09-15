from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from typing import Any, Callable

from .schemas import validate_prediction


def execute_adjacent(
    *,
    executor_b2,
    executor_b3,
    cases,
    manifest_b2,
    manifest_b3,
    repeat_index: int,
    existing: dict[str, Any] | None = None,
    max_new_cases: int | None = None,
    parallel_pairs: int = 1,
    checkpoint: Callable[[dict[str, Any]], None] | None = None,
):
    case_order = {str(case["case_id"]): index for index, case in enumerate(cases)}
    b2_by_id = {
        str(item["case_id"]): item
        for item in list(((existing or {}).get("b2") or {}).get("predictions") or [])
    }
    b3_by_id = {
        str(item["case_id"]): item
        for item in list(((existing or {}).get("b3") or {}).get("predictions") or [])
    }
    order_by_id = {
        str(item["case_id"]): item
        for item in list((existing or {}).get("execution_order") or [])
    }
    completed = set(order_by_id)

    pending: list[tuple[int, dict[str, Any], tuple[str, str]]] = []
    for index, case in enumerate(cases):
        case_id = str(case["case_id"])
        if case_id in completed:
            continue
        if max_new_cases is not None and len(pending) >= max_new_cases:
            break
        order = ("B2", "B3") if (index + repeat_index) % 2 == 0 else ("B3", "B2")
        pending.append((index, case, order))

    def snapshot() -> dict[str, Any]:
        ordered_ids = sorted(order_by_id, key=lambda case_id: case_order[case_id])
        return {
            "repeat_index": repeat_index,
            "execution_order": [order_by_id[case_id] for case_id in ordered_ids],
            "b2": {"predictions": [b2_by_id[case_id] for case_id in ordered_ids]},
            "b3": {"predictions": [b3_by_id[case_id] for case_id in ordered_ids]},
        }

    def run_pair(item: tuple[int, dict[str, Any], tuple[str, str]]):
        index, case, order = item
        current = {}
        for arm in order:
            executor = executor_b2 if arm == "B2" else executor_b3
            manifest = manifest_b2 if arm == "B2" else manifest_b3
            current[arm] = asdict(
                validate_prediction(executor.run_case(case=case, manifest=manifest))
            )
        return index, str(case["case_id"]), order, current

    workers = max(1, int(parallel_pairs))
    if workers == 1:
        results = [run_pair(item) for item in pending]
        for index, case_id, order, current in results:
            b2_by_id[case_id] = current["B2"]
            b3_by_id[case_id] = current["B3"]
            order_by_id[case_id] = {"case_id": case_id, "first": order[0], "second": order[1]}
            if checkpoint is not None:
                checkpoint(snapshot())
    else:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(run_pair, item) for item in pending]
            for future in as_completed(futures):
                index, case_id, order, current = future.result()
                b2_by_id[case_id] = current["B2"]
                b3_by_id[case_id] = current["B3"]
                order_by_id[case_id] = {"case_id": case_id, "first": order[0], "second": order[1]}
                if checkpoint is not None:
                    checkpoint(snapshot())

    return snapshot()
