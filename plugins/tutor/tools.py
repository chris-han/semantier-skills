"""Native Tutor handlers over the host-granted core interface."""

import json
from .mastery import objective_progress
from .teaching import teaching_turn
from .practice import ChoiceExercise, passage_recall, supported_recall_key


def grade_frozen_choice(exercise, answer):
    rubric = exercise["rubric"]
    choice = ChoiceExercise(exercise["question"], tuple(tuple(pair) for pair in exercise["choices"]),
                            rubric["key"], rubric["rationale"],
                            tuple(source["evidence"]["artifact_ref"] for source in rubric["sources"]))
    passages = [source["locator"]["selector"].get("exact_quote") for source in rubric["sources"]
                if source.get("locator") and source["locator"].get("selector")]
    supported = supported_recall_key(choice.stem, choice.options, tuple(p for p in passages if p))
    if supported is None or supported != choice.key:
        return {"result": "ungraded", "feedback": "The cited passage does not establish the frozen answer key."}
    result = choice.grade(answer)
    feedback = rubric["rationale"] if result != "ungraded" else "Choose one unambiguous option."
    return {"result": result, "feedback": feedback}


def tool_handler(ctx, operation):
    def invoke(args, *, tutor_core=None, **kwargs):
        # Native dispatch can bind a single authorized operation to this turn.
        # The callable is supplied out of band and cannot be expressed in JSON.
        if tutor_core is None:
            response = ctx.call_mcp("semantier_tutor", operation, args)
        elif operation == "tutor_teach":
            response = {"ok": True, "structuredContent": tutor_core(operation, args, teach=teaching_turn)}
        elif operation == "tutor_practice":
            response = {"ok": True, "structuredContent": tutor_core(operation, args, prepare=passage_recall)}
        elif operation == "tutor_submit":
            response = {"ok": True, "structuredContent": tutor_core(operation, args, grade=grade_frozen_choice)}
        else:
            response = {"ok": True, "structuredContent": tutor_core(operation, args)}
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
