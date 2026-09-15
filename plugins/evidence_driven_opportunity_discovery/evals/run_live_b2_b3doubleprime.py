from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

from .adjacent_runner import execute_adjacent
from .hermes_executor import HermesEvalExecutor
from .pairing import case_disagreements
from .release_report import evaluate_track_a_release, unsafe_action_rate
from .repeats import aggregate_metric_repeats, aggregate_usage, paired_mean_difference
from .run_live_b2_b3 import (
    BASE_INSTRUCTIONS,
    _agent_factory_builder,
    _load_cases,
    _load_skill_text,
    _manifest,
    _prediction_report,
    _runner_with_usage,
    _sha_json,
    _sha_text,
    _write_json,
)


def _file_sha(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _manifest_self_hash(manifest: dict[str, Any]) -> str:
    copy = json.loads(json.dumps(manifest))
    copy["hashes"]["protocol_manifest_sha256"] = "SELF_OMITTED"
    return sha256(
        json.dumps(copy, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


def validate_frozen_protocol(*, eval_root: Path, plugin_root: Path, protocol_path: Path) -> dict[str, Any]:
    protocol = json.loads(protocol_path.read_text())
    expected = protocol["hashes"]
    cases = _load_cases(eval_root)
    actual = {
        "protocol_markdown_sha256": _file_sha(eval_root / "b2_b3doubleprime_frozen_protocol.md"),
        "protocol_manifest_sha256": _manifest_self_hash(protocol),
        "intervention_sha256": _sha_text(str(protocol["intervention"])),
        "base_skill_sha256": _file_sha(plugin_root / "SKILL.md"),
        "case_source_sha256": _file_sha(eval_root / "track_a_gold" / "cases.json"),
        "case_set_hash": _sha_json(cases),
        "prediction_schema_sha256": _file_sha(eval_root / "prediction.schema.json"),
        "track_a_scorer_sha256": _file_sha(eval_root / "runner.py"),
        "release_gate_sha256": _file_sha(eval_root / "release_report.py"),
        "negative_synthesis_sha256": _file_sha(eval_root / "negative_experiment_synthesis_v1.md"),
        "original_live_summary_sha256": _file_sha(eval_root / "live_runs" / "summary.json"),
        "b3prime_live_summary_sha256": _file_sha(eval_root / "live_runs_b3prime_v1" / "summary.json"),
    }
    mismatches = {
        key: {"expected": expected.get(key), "actual": value}
        for key, value in actual.items()
        if expected.get(key) != value
    }
    if mismatches:
        raise ValueError(f"FROZEN_PROTOCOL_HASH_MISMATCH:{json.dumps(mismatches, sort_keys=True)}")
    if [str(case["case_id"]) for case in cases] != list(protocol["cases"]):
        raise ValueError("FROZEN_PROTOCOL_CASE_ORDER_MISMATCH")
    if int(protocol["repeats"]) != 3 or int(protocol["required_model_calls"]) != 48:
        raise ValueError("FROZEN_PROTOCOL_RUN_COUNT_INVALID")
    return protocol


def _positive_count(predictions: list[dict[str, Any]]) -> int:
    return sum(bool(prediction.get("valid_opportunity")) for prediction in predictions)


def _claim_role_diagnostics(predictions: list[dict[str, Any]]) -> dict[str, int]:
    claims = [claim for prediction in predictions for claim in (prediction.get("claims") or []) if isinstance(claim, dict)]
    return {
        "claims_count": len(claims),
        "unsupported_claims_count": sum(not bool(claim.get("supported")) for claim in claims),
        "assumptions_count": sum(len(prediction.get("assumptions") or []) for prediction in predictions),
        "uncertainties_count": sum(len(prediction.get("uncertainties") or []) for prediction in predictions),
    }


def _aggregate_followup(all_runs: list[dict[str, Any]]) -> dict[str, Any]:
    b2_reports = [{"metrics": run["b2_metrics"]} for run in all_runs]
    b3_reports = [{"metrics": run["b3doubleprime_metrics"]} for run in all_runs]
    b2_aggregate = aggregate_metric_repeats(b2_reports)
    b3_aggregate = aggregate_metric_repeats(b3_reports)
    b2_mean = {name: summary["mean"] for name, summary in b2_aggregate.items()}
    b3_mean = {name: summary["mean"] for name, summary in b3_aggregate.items()}
    b2_predictions = [prediction for run in all_runs for prediction in run["b2"]["predictions"]]
    b3_predictions = [prediction for run in all_runs for prediction in run["b3doubleprime"]["predictions"]]
    unsafe_b2 = unsafe_action_rate(b2_predictions)
    unsafe_b3 = unsafe_action_rate(b3_predictions)
    primary = evaluate_track_a_release(b2=b2_mean, b3=b3_mean, unsafe_b2=unsafe_b2, unsafe_b3=unsafe_b3)
    b2_positive_counts = [_positive_count(run["b2"]["predictions"]) for run in all_runs]
    b3_positive_counts = [_positive_count(run["b3doubleprime"]["predictions"]) for run in all_runs]
    mean_b2_positive = sum(b2_positive_counts) / len(b2_positive_counts)
    mean_b3_positive = sum(b3_positive_counts) / len(b3_positive_counts)
    anti_regression = {
        "hypothesis_recall_floor": b3_mean["hypothesis_recall"] >= b2_mean["hypothesis_recall"] - 0.05,
        "positive_admission_collapse": mean_b3_positive >= mean_b2_positive - 1.0,
    }
    all_checks = {**primary.checks, **anti_regression}
    failed = [name for name, passed in all_checks.items() if not passed]
    paired_differences = {
        name: paired_mean_difference(
            [float(report["metrics"][name]) for report in b2_reports],
            [float(report["metrics"][name]) for report in b3_reports],
        )
        for name in sorted(b2_mean)
    }
    return {
        "release_gate": {
            "passed": not failed,
            "checks": all_checks,
            "failed_checks": failed,
            "primary_checks": primary.checks,
            "anti_regression_checks": anti_regression,
        },
        "metrics": {"b2": b2_aggregate, "b3doubleprime": b3_aggregate},
        "paired_differences": paired_differences,
        "unsafe_action_rate": {"b2": unsafe_b2, "b3doubleprime": unsafe_b3},
        "positive_admission_counts": {
            "b2_by_repeat": b2_positive_counts,
            "b3doubleprime_by_repeat": b3_positive_counts,
            "b2_mean": mean_b2_positive,
            "b3doubleprime_mean": mean_b3_positive,
        },
        "claim_role_diagnostics": {
            "b2": _claim_role_diagnostics(b2_predictions),
            "b3doubleprime": _claim_role_diagnostics(b3_predictions),
        },
        "usage": {"b2": aggregate_usage(b2_predictions), "b3doubleprime": aggregate_usage(b3_predictions)},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run frozen EOD B2/B3-double-prime claim-role follow-up.")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--max-new-cases", type=int, default=0)
    parser.add_argument("--parallel-pairs", type=int, default=1)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()

    eval_root = Path(__file__).resolve().parent
    plugin_root = eval_root.parent
    repo_root = Path(__file__).resolve().parents[4]
    protocol = validate_frozen_protocol(
        eval_root=eval_root,
        plugin_root=plugin_root,
        protocol_path=eval_root / "b2_b3doubleprime_frozen_protocol.json",
    )
    if args.validate_only:
        print(json.dumps({
            "status": "FROZEN_PROTOCOL_VALID",
            "protocol_id": protocol["protocol_id"],
            "protocol_manifest_sha256": protocol["hashes"]["protocol_manifest_sha256"],
        }, indent=2, sort_keys=True))
        return

    cases = _load_cases(eval_root)
    base_skill_text = _load_skill_text(plugin_root)
    intervention = str(protocol["intervention"])
    treated_skill_text = f"{base_skill_text}\n\n[FROZEN FOLLOW-UP INTERVENTION]\n{intervention}"
    provider = str(protocol["provider"])
    model = str(protocol["model"])
    repeats = int(protocol["repeats"])
    pins = protocol["runtime_pins"]
    max_iterations = int(pins["max_iterations"])
    max_tokens = int(pins["output_token_budget"])
    case_set_hash = _sha_json(cases)
    prompt_hash = _sha_text(BASE_INSTRUCTIONS)
    base_skill_hash = _sha_text(base_skill_text)
    treated_skill_hash = _sha_text(treated_skill_text)
    toolset_hash = _sha_text("NO_TOOLS_SKILL_ONLY_EXPERIMENT_V1")
    model_config = {
        "provider": provider,
        "model": model,
        "max_iterations": max_iterations,
        "max_tokens": max_tokens,
        "tools": "NONE",
        "skip_context_files": True,
        "skip_memory": True,
        "skip_background_review": True,
    }
    model_config_hash = _sha_json(model_config)
    agent_factory = _agent_factory_builder(
        repo_root=repo_root,
        provider=provider,
        model=model,
        max_iterations=max_iterations,
        max_tokens=max_tokens,
    )
    runtime_runner = _runner_with_usage(agent_factory)
    b2_executor = HermesEvalExecutor(runner=runtime_runner, arm="B2", base_instructions=BASE_INSTRUCTIONS)
    treated_executor = HermesEvalExecutor(
        runner=runtime_runner,
        arm="B3",
        base_instructions=BASE_INSTRUCTIONS,
        eod_skill_text=treated_skill_text,
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    _write_json(args.output_dir / "protocol-snapshot.json", {
        "protocol_id": protocol["protocol_id"],
        "protocol_manifest_sha256": protocol["hashes"]["protocol_manifest_sha256"],
        "base_skill_hash": base_skill_hash,
        "b3doubleprime_skill_hash": treated_skill_hash,
        "intervention_sha256": protocol["hashes"]["intervention_sha256"],
        "case_set_hash": case_set_hash,
        "model_config_hash": model_config_hash,
        "toolset_hash": toolset_hash,
    })

    all_runs: list[dict[str, Any]] = []
    remaining_budget = None if args.max_new_cases <= 0 else args.max_new_cases
    for repeat in range(repeats):
        b2_manifest = _manifest(
            arm="B2", repeat=repeat, case_set_hash=case_set_hash, provider=provider, model=model,
            model_config_hash=model_config_hash, toolset_hash=toolset_hash, prompt_hash=prompt_hash,
            skill_hash=base_skill_hash, instruction_hash=_sha_text(BASE_INSTRUCTIONS),
            max_iterations=max_iterations, max_tokens=max_tokens,
        )
        treated_instructions = f"{BASE_INSTRUCTIONS}\n\n[EOD SKILL]\n{treated_skill_text}"
        treated_manifest = _manifest(
            arm="B3", repeat=repeat, case_set_hash=case_set_hash, provider=provider, model=model,
            model_config_hash=model_config_hash, toolset_hash=toolset_hash, prompt_hash=prompt_hash,
            skill_hash=treated_skill_hash, instruction_hash=_sha_text(treated_instructions),
            max_iterations=max_iterations, max_tokens=max_tokens,
        )
        pair_validation = {
            "status": "VALID_CONTROLLED_PAIR",
            "basis": "frozen_b3doubleprime_protocol",
            "allowed_differences": list(protocol["allowed_pair_differences"]),
            "protocol_manifest_sha256": protocol["hashes"]["protocol_manifest_sha256"],
        }
        output = args.output_dir / f"repeat-{repeat}.json"
        progress = args.output_dir / f"repeat-{repeat}.progress.json"
        if output.exists():
            all_runs.append(json.loads(output.read_text()))
            continue
        existing = json.loads(progress.read_text()) if progress.exists() else None
        before = len(((existing or {}).get("execution_order") or []))
        paired = execute_adjacent(
            executor_b2=b2_executor,
            executor_b3=treated_executor,
            cases=cases,
            manifest_b2=b2_manifest,
            manifest_b3=treated_manifest,
            repeat_index=repeat,
            existing=existing,
            max_new_cases=remaining_budget,
            parallel_pairs=args.parallel_pairs,
            checkpoint=lambda value, path=progress: _write_json(path, value),
        )
        completed = len(paired["execution_order"])
        if remaining_budget is not None:
            remaining_budget -= completed - before
        if completed < len(cases):
            partial = {
                "status": "LIVE_B3DOUBLEPRIME_MATRIX_PARTIAL",
                "protocol_id": protocol["protocol_id"],
                "provider": provider,
                "model": model,
                "repeat_count": repeats,
                "current_repeat": repeat,
                "completed_case_pairs_in_repeat": completed,
                "case_pairs_per_repeat": len(cases),
                "remaining_case_pairs_total": (len(cases) - completed) + (repeats - repeat - 1) * len(cases),
            }
            _write_json(args.output_dir / "summary.json", partial)
            print(json.dumps(partial, indent=2, sort_keys=True))
            return
        b2_predictions = paired["b2"]["predictions"]
        treated_predictions = paired["b3"]["predictions"]
        run = {
            "repeat_index": repeat,
            "execution_order": paired["execution_order"],
            "b2": paired["b2"],
            "b3doubleprime": paired["b3"],
            "pair_validation": pair_validation,
            "b2_metrics": _prediction_report(cases, b2_predictions),
            "b3doubleprime_metrics": _prediction_report(cases, treated_predictions),
            "claim_role_diagnostics": {
                "b2": _claim_role_diagnostics(b2_predictions),
                "b3doubleprime": _claim_role_diagnostics(treated_predictions),
            },
            "disagreements": case_disagreements(b2_predictions, treated_predictions),
        }
        _write_json(output, run)
        progress.unlink(missing_ok=True)
        all_runs.append(run)
        if remaining_budget == 0 and repeat + 1 < repeats:
            partial = {
                "status": "LIVE_B3DOUBLEPRIME_MATRIX_PARTIAL",
                "protocol_id": protocol["protocol_id"],
                "provider": provider,
                "model": model,
                "repeat_count": repeats,
                "current_repeat": repeat + 1,
                "completed_case_pairs_in_repeat": 0,
                "case_pairs_per_repeat": len(cases),
                "remaining_case_pairs_total": (repeats - repeat - 1) * len(cases),
            }
            _write_json(args.output_dir / "summary.json", partial)
            print(json.dumps(partial, indent=2, sort_keys=True))
            return

    summary = {
        "status": "LIVE_B3DOUBLEPRIME_MATRIX_COMPLETE",
        "protocol_id": protocol["protocol_id"],
        "protocol_manifest_sha256": protocol["hashes"]["protocol_manifest_sha256"],
        "provider": provider,
        "model": model,
        "repeat_count": repeats,
        "case_count": len(cases),
        "case_run_count": len(cases) * 2 * repeats,
        "case_set_hash": case_set_hash,
        "model_config_hash": model_config_hash,
        "toolset_hash": toolset_hash,
        "base_skill_hash": base_skill_hash,
        "b3doubleprime_skill_hash": treated_skill_hash,
        "intervention_sha256": protocol["hashes"]["intervention_sha256"],
        "runs": [f"repeat-{index}.json" for index in range(repeats)],
        **_aggregate_followup(all_runs),
    }
    _write_json(args.output_dir / "summary.json", summary)
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
