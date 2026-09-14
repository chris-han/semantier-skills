from __future__ import annotations

import http.cookiejar
import json
from typing import Any
import urllib.request

from .schemas import EvalRunManifest


class SemantierGatewayEvalExecutor:
    """EOD-Bench executor over Semantier's real password-login gateway path."""

    def __init__(self, *, base_url: str, login: str, password: str, arm: str, base_instructions: str, eod_skill_text: str | None = None, model: str | None = None) -> None:
        if arm not in {"B2", "B3"}:
            raise ValueError("GATEWAY_EVAL_ARM_INVALID")
        if arm == "B3" and not eod_skill_text:
            raise ValueError("B3_EOD_SKILL_REQUIRED")
        self._base_url = base_url.rstrip("/")
        self._arm = arm
        self._base_instructions = base_instructions
        self._eod_skill_text = eod_skill_text
        self._model = model
        jar = http.cookiejar.CookieJar()
        self._opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
        status, body = self._post("/auth/password/login", {"login": login, "password": password})
        if status != 200 or not body.get("authenticated"):
            raise RuntimeError("SEMANTIER_DB_PASSWORD_LOGIN_FAILED")

    def _post(self, path: str, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        request = urllib.request.Request(
            f"{self._base_url}{path}",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with self._opener.open(request, timeout=60) as response:
            return int(response.status), json.loads(response.read().decode() or "{}")

    def _instructions(self) -> str:
        if self._arm == "B2":
            return self._base_instructions
        return f"{self._base_instructions}\n\n[EOD SKILL]\n{self._eod_skill_text}"

    def run_case(self, *, case: dict[str, Any], manifest: EvalRunManifest) -> dict[str, Any]:
        if manifest.arm != self._arm:
            raise ValueError("GATEWAY_EXECUTOR_ARM_MISMATCH")
        session_id = f"eod-bench-{self._arm.lower()}-{manifest.repeat_index}-{case['case_id']}"
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
        status, body = self._post(
            f"/api/sessions/{session_id}/chat",
            {
                "message": json.dumps(task, sort_keys=True),
                "system_message": self._instructions(),
                **({"model": self._model} if self._model else {}),
            },
        )
        if status != 200 or not body.get("ok"):
            raise RuntimeError("SEMANTIER_GATEWAY_CHAT_FAILED")
        message = body.get("message")
        if not isinstance(message, str):
            raise ValueError("SEMANTIER_GATEWAY_PREDICTION_REQUIRED")
        try:
            prediction = json.loads(message)
        except json.JSONDecodeError as exc:
            raise ValueError("SEMANTIER_GATEWAY_PREDICTION_NOT_JSON") from exc
        usage = dict(body.get("usage") or {})
        usage.setdefault("input_tokens", usage.get("prompt_tokens", 0) or 0)
        usage.setdefault("output_tokens", usage.get("completion_tokens", 0) or 0)
        usage.setdefault("reasoning_tokens", usage.get("reasoning_tokens", 0) or 0)
        usage.setdefault("tool_calls", 0)
        return {**prediction, "usage": usage}
