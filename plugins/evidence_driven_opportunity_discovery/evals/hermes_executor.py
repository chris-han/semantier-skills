from __future__ import annotations

import json
from time import perf_counter
from typing import Any, Callable

from .schemas import EvalRunManifest


HermesRunner = Callable[..., dict[str, Any]]


class HermesEvalExecutor:
    """Thin benchmark adapter over the existing Hermes agent runtime.

    `runner` is injected so this package does not own provider credentials, session
    construction, or the Hermes conversation loop. The runtime wrapper is expected
    to apply the manifest's model/tool/token pins and return the final structured
    model output plus usage/accounting metadata.
    """

    def __init__(self, *, runner: HermesRunner, arm: str, base_instructions: str, eod_skill_text: str | None = None) -> None:
        if arm not in {"B2", "B3"}:
            raise ValueError("HERMES_EVAL_ARM_INVALID")
        if arm == "B3" and not eod_skill_text:
            raise ValueError("B3_EOD_SKILL_REQUIRED")
        self._runner = runner
        self._arm = arm
        self._base_instructions = base_instructions
        self._eod_skill_text = eod_skill_text

    def _instructions(self) -> str:
        if self._arm == "B2":
            return self._base_instructions
        return f"{self._base_instructions}\n\n[EOD SKILL]\n{self._eod_skill_text}"

    def run_case(self, *, case: dict[str, Any], manifest: EvalRunManifest) -> dict[str, Any]:
        if manifest.arm != self._arm:
            raise ValueError("HERMES_EXECUTOR_ARM_MISMATCH")
        started = perf_counter()
        result = self._runner(
            case=case,
            manifest=manifest.to_dict(),
            instructions=self._instructions(),
        )
        elapsed_ms = (perf_counter() - started) * 1000.0
        if not isinstance(result, dict):
            raise ValueError("HERMES_RUNNER_RESULT_INVALID")
        raw_prediction = result.get("prediction")
        if raw_prediction is None:
            final_response = result.get("final_response")
            if not isinstance(final_response, str):
                raise ValueError("HERMES_RUNNER_FINAL_RESPONSE_REQUIRED")
            try:
                raw_prediction = json.loads(final_response)
            except json.JSONDecodeError as exc:
                raise ValueError("HERMES_PREDICTION_NOT_JSON") from exc
        if not isinstance(raw_prediction, dict):
            raise ValueError("HERMES_PREDICTION_INVALID")

        usage = dict(result.get("usage") or raw_prediction.get("usage") or {})
        usage.setdefault("input_tokens", 0)
        usage.setdefault("output_tokens", 0)
        usage.setdefault("tool_calls", int(result.get("tool_calls") or result.get("api_calls") or 0))
        usage.setdefault("reasoning_tokens", result.get("reasoning_tokens") or 0)
        usage.setdefault("wall_clock_ms", elapsed_ms)
        raw_prediction = {**raw_prediction, "usage": usage}
        return raw_prediction


def build_hermes_runner(agent_factory: Callable[..., Any]) -> HermesRunner:
    """Adapt Hermes `AIAgent.run_conversation()` to the benchmark runner contract.

    The factory must enforce the manifest pins when constructing the agent. This
    helper deliberately refuses to infer provider credentials or mutable runtime
    defaults from the plugin.
    """

    def run(*, case: dict[str, Any], manifest: dict[str, Any], instructions: str) -> dict[str, Any]:
        agent = agent_factory(manifest=manifest, instructions=instructions)
        if not callable(getattr(agent, "run_conversation", None)):
            raise ValueError("HERMES_AGENT_RUN_CONVERSATION_REQUIRED")
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
            "decision_context_projection": case.get("context_projection") or case.get("observations") or [],
            "required_output": "Return only one JSON object matching EOD-Bench prediction.schema.json.",
        }
        conversation = agent.run_conversation(json.dumps(task, sort_keys=True))
        if not isinstance(conversation, dict):
            raise ValueError("HERMES_CONVERSATION_RESULT_INVALID")
        return {
            "final_response": conversation.get("final_response"),
            "api_calls": conversation.get("api_calls", 0),
            "usage": conversation.get("usage") or conversation.get("token_usage") or {},
            "reasoning_tokens": conversation.get("reasoning_tokens", 0),
        }

    return run
