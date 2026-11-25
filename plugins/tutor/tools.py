"""Native Tutor handlers over the host-granted core interface."""

import json
from .mastery import objective_progress

def tool_handler(ctx, operation):
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
