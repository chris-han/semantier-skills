"""Hermes registration for the Semantier Tutor package."""

import json
from pathlib import Path

from .mastery import objective_progress


# The host supplies the authenticated learner and workspace to the approved server.
_OPERATIONS = {
    "tutor_plan": ("Create or edit a learning path.", ("project_ref", "source_ref", "goal", "request_id"), ("plan_ref", "expected_revision", "language")),
    "tutor_teach": ("Explain an objective or give a requested hint.", ("project_ref", "plan_ref", "objective_ref", "request_id"), ("question", "language")),
    "tutor_practice": ("Prepare a source-grounded exercise.", ("project_ref", "plan_ref", "objective_ref", "expected_revision", "request_id"), ()),
    "tutor_submit": ("Assess a learner submission against its frozen exercise.", ("project_ref", "plan_ref", "exercise_ref", "answer", "expected_revision", "request_id"), ()),
    "tutor_progress": ("Resume an authorized learning plan.", ("project_ref",), ("plan_ref",)),
}


def _handler(ctx, operation):
    def invoke(args, **kwargs):
        response = ctx.call_mcp("semantier_tutor", operation, args)
        if response.get("truncated"):
            return json.dumps({"error": "TUTOR_RESULT_TRUNCATED"})
        if operation == "tutor_progress" and response.get("ok"):
            result = response.get("structuredContent", response.get("result"))
            if not isinstance(result, dict) or not isinstance(result.get("objectives"), list):
                return json.dumps({"error": "TUTOR_PROGRESS_RESPONSE_INVALID"})
            for objective in result["objectives"]:
                objective["mastery"] = objective_progress(objective)
            return json.dumps(result, ensure_ascii=False)
        return json.dumps(response, ensure_ascii=False)
    return invoke


def register(ctx):
    for name, (description, required, optional) in _OPERATIONS.items():
        properties = {field: {"type": "string", "minLength": 1} for field in (*required, *optional)}
        if "expected_revision" in properties:
            properties["expected_revision"] = {"type": "integer", "minimum": 0}
        parameters = {
            "type": "object",
            "properties": properties,
            "required": list(required),
            "additionalProperties": False,
        }
        ctx.register_tool(
            name=name, toolset="tutor", description=description,
            schema={"name": name, "description": description, "parameters": parameters},
            handler=_handler(ctx, name),
        )
    ctx.register_skill(name="tutor", path=Path(__file__).with_name("SKILL.md"),
                       description="Source-grounded learning, practice and progress.")
