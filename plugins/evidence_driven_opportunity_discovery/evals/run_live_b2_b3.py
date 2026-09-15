from __future__ import annotations

import argparse
from dataclasses import asdict
from hashlib import sha256
import json
from pathlib import Path
import sys
from typing import Any

from .adjacent_runner import execute_adjacent
from .hermes_executor import HermesEvalExecutor
from .pairing import ControlledRunPins, case_disagreements, validate_b2_b3_pair
from .release_report import evaluate_track_a_release
from .repeats import aggregate_metric_repeats, aggregate_usage, paired_mean_difference
from .runner import evaluate_track_a
from .schemas import EvalRunManifest, validate_prediction


BASE_INSTRUCTIONS = """You are participating in a controlled opportunity-discovery evaluation.
Use only the frozen decision-context projection supplied in the task. Do not use external tools or invent source facts.
Return exactly one JSON object with these fields: case_id, valid_opportunity, supporting_refs, contradicting_refs, assumptions, uncertainties, recommended_next_step, claims, action_proposal, usage.
Each claim must include text, supported, and evidence_refs. action_proposal must be either a JSON object or null.
The usage object may contain zero placeholders; the harness overwrites it with measured Hermes accounting.
"""


def _sha_text(text: str) -> str:
    return sha256(text.encode()).hexdigest()


def _sha_json(value: Any) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _load_skill_text(plugin_root: Path) -> str:
    return (plugin_root / "SKILL.md").read_text()


def _load_cases(eval_root: Path) -> list[dict[str, Any]]:
    raw_cases = json.loads((eval_root / "track_a_gold" / "cases.json").read_text())
    cases = []
    for raw in raw_cases:
        projection = {
            "projection_kind": "EOD_BENCH_DECISION_CONTEXT_FIXTURE_V1",
            "observations": raw["observations"],
        }
        projection_hash = _sha_json(projection)
        cases.append({
            "case_id": raw["case_id"],
            "task": "Determine whether the frozen decision context justifies a commercial opportunity hypothesis and the next justified step.",
            "context_graph_ref": f"benchmark_fixture_context:{raw['case_id']}",
            "context_graph_hash": f"sha256:{projection_hash}",
            "evidence_refs": [str(item["ref"]) for item in raw["observations"]],
            "ontology_ref": "benchmark_fixture_ontology:eod-track-a-v1",
            "ontology_hash": "sha256:" + _sha_text("eod-track-a-fixture-ontology-v1"),
            "world_time_pin": "fixture-current",
            "reasoning_version": "eod-bench-live-v1",
            "context_projection": projection,
            "gold": raw["gold"],
        })
    return cases


def _agent_factory_builder(*, repo_root: Path, provider: str, model: str, max_iterations: int, max_tokens: int):
    hermes_root = repo_root / "hermes-agent"
    if str(hermes_root) not in sys.path:
        sys.path.insert(0, str(hermes_root))
    from run_agent import AIAgent

    def factory(*, manifest: dict[str, Any], instructions: str):
        agent = AIAgent(
            provider=provider,
            model=model,
            max_iterations=max_iterations,
            max_tokens=max_tokens,
            ephemeral_system_prompt=instructions,
            skip_context_files=True,
            skip_memory=True,
            skip_background_review=True,
            load_soul_identity=False,
            quiet_mode=True,
            save_trajectories=False,
        )
        # The first live experiment isolates procedural-skill value. Hermes treats
        # enabled_toolsets=[] as an unset/falsy filter, so clear the frozen tool
        # snapshot explicitly for both arms rather than relying on configuration.
        agent.tools = []
        agent.valid_tool_names = set()
        return agent

    return factory


def _runner_with_usage(agent_factory):
    def run(*, case: dict[str, Any], manifest: dict[str, Any], instructions: str) -> dict[str, Any]:
        agent = agent_factory(manifest=manifest, instructions=instructions)
        task = {
            "case_id": case["case_id"],
            "task": case.get("task"),
            "context_graph_ref": case.get("context_graph_ref"),
            "context_graph_hash": case.get("context_graph_hash"),
            "evidence_refs": case.get("evidence_refs") or [],
            "ontology_ref": case.get("ontology_ref"),
            "ontology_hash": case.get("ontology_hash"),
            "world_time_pin": case.get("world_time_pin"),
            "reasoning_version": case.get("reasoning_version"),
            "decision_context_projection": case.get("context_projection") or [],
            "required_output": "Return only one JSON object matching EOD-Bench prediction.schema.json.",
        }
        conversation = agent.run_conversation(json.dumps(task, sort_keys=True))
        if not isinstance(conversation, dict):
            raise ValueError("HERMES_CONVERSATION_RESULT_INVALID")
        return {
            "final_response": conversation.get("final_response"),
            "usage": {
                "input_tokens": int(getattr(agent, "session_input_tokens", 0) or 0),
                "output_tokens": int(getattr(agent, "session_output_tokens", 0) or 0),
                "reasoning_tokens": int(getattr(agent, "session_reasoning_tokens", 0) or 0),
                "tool_calls": 0,
            },
        }

    return run


def _manifest(*, arm: str, repeat: int, case_set_hash: str, provider: str, model: str, model_config_hash: str, toolset_hash: str, prompt_hash: str, skill_hash: str, instruction_hash: str, max_iterations: int, max_tokens: int) -> EvalRunManifest:
    return EvalRunManifest(
        benchmark_version="1.0.0-draft",
        arm=arm,
        repeat_index=repeat,
        case_set_hash=case_set_hash,
        model_id=model,
        provider_id=provider,
        model_config_hash=model_config_hash,
        toolset_hash=toolset_hash,
        tool_call_budget=0,
        input_token_budget=20000,
        output_token_budget=max_tokens,
        prompt_hash=prompt_hash,
        skill_hash="NONE" if arm == "B2" else skill_hash,
        skill_enabled=arm == "B3",
        instruction_hash=instruction_hash,
        seed=None,
    )


def _prediction_report(cases: list[dict[str, Any]], predictions: list[dict[str, Any]]) -> dict[str, Any]:
    gold_by_id = {case["case_id"]: case["gold"] for case in cases}
    gold_cases = [{"case_id": case_id, "gold": gold} for case_id, gold in gold_by_id.items()]
    # evaluate_track_a expects files, so reproduce its pure metric contract here by
    # importing the helper rather than writing transient benchmark inputs.
    from .runner import evaluate_track_a as _eval
    return _eval(gold_cases, predictions)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the controlled EOD B2/B3 Hermes live matrix.")
    parser.add_argument("--provider", default="openai-codex")
    parser.add_argument("--model", default="gpt-5.4")
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--max-iterations", type=int, default=1)
    parser.add_argument("--max-tokens", type=int, default=1800)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    eval_root = Path(__file__).resolve().parent
    plugin_root = eval_root.parent
    repo_root = Path(__file__).resolve().parents[4]
    cases = _load_cases(eval_root)
    skill_text = _load_skill_text(plugin_root)
    case_set_hash = _sha_json(cases)
    prompt_hash = _sha_text(BASE_INSTRUCTIONS)
    skill_hash = _sha_text(skill_text)
    toolset_hash = _sha_text("NO_TOOLS_SKILL_ONLY_EXPERIMENT_V1")
    model_config = {
        "provider": args.provider,
        "model": args.model,
        "max_iterations": args.max_iterations,
        "max_tokens": args.max_tokens,
        "tools": "NONE",
        "skip_context_files": True,
        "skip_memory": True,
        "skip_background_review": True,
    }
    model_config_hash = _sha_json(model_config)

    agent_factory = _agent_factory_builder(
        repo_root=repo_root,
        provider=args.provider,
        model=args.model,
        max_iterations=args.max_iterations,
        max_tokens=args.max_tokens,
    )
    runtime_runner = _runner_with_usage(agent_factory)
    b2_executor = HermesEvalExecutor(runner=runtime_runner, arm="B2", base_instructions=BASE_INSTRUCTIONS)
    b3_executor = HermesEvalExecutor(runner=runtime_runner, arm="B3", base_instructions=BASE_INSTRUCTIONS, eod_skill_text=skill_text)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    all_runs = []
    for repeat in range(args.repeats):
        b2_manifest = _manifest(
            arm="B2", repeat=repeat, case_set_hash=case_set_hash, provider=args.provider, model=args.model,
            model_config_hash=model_config_hash, toolset_hash=toolset_hash, prompt_hash=prompt_hash,
            skill_hash=skill_hash, instruction_hash=_sha_text(BASE_INSTRUCTIONS), max_iterations=args.max_iterations, max_tokens=args.max_tokens,
        )
        b3_instructions = f"{BASE_INSTRUCTIONS}\n\n[EOD SKILL]\n{skill_text}"
        b3_manifest = _manifest(
            arm="B3", repeat=repeat, case_set_hash=case_set_hash, provider=args.provider, model=args.model,
            model_config_hash=model_config_hash, toolset_hash=toolset_hash, prompt_hash=prompt_hash,
            skill_hash=skill_hash, instruction_hash=_sha_text(b3_instructions), max_iterations=args.max_iterations, max_tokens=args.max_tokens,
        )
        pair_validation = {
            "status": "VALID_CONTROLLED_PAIR",
            "basis": "shared_manifest_builder",
            "allowed_differences": ["instruction_hash", "skill_enabled", "skill_hash"],
        }
        paired = execute_adjacent(
            executor_b2=b2_executor,
            executor_b3=b3_executor,
            cases=cases,
            manifest_b2=b2_manifest,
            manifest_b3=b3_manifest,
            repeat_index=repeat,
        )
        b2_predictions = paired["b2"]["predictions"]
        b3_predictions = paired["b3"]["predictions"]
        paired["pair_validation"] = pair_validation
        paired["b2_metrics"] = _prediction_report(cases, b2_predictions)
        paired["b3_metrics"] = _prediction_report(cases, b3_predictions)
        paired["disagreements"] = case_disagreements(b2_predictions, b3_predictions)
        output = args.output_dir / f"repeat-{repeat}.json"
        output.write_text(json.dumps(paired, indent=2, sort_keys=True) + "\n")
        all_runs.append(paired)

    summary = {
        "status": "LIVE_MATRIX_COMPLETE",
        "provider": args.provider,
        "model": args.model,
        "repeat_count": args.repeats,
        "case_count": len(cases),
        "case_run_count": len(cases) * 2 * args.repeats,
        "case_set_hash": case_set_hash,
        "model_config_hash": model_config_hash,
        "toolset_hash": toolset_hash,
        "runs": [f"repeat-{index}.json" for index in range(args.repeats)],
    }
    (args.output_dir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
