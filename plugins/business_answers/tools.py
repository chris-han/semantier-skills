"""Transport only: identity, checks, arithmetic and artifacts belong to core."""
import json


def _invoke(operation, args):
    from agents import business_answers
    from plugins.governed_graph.tools import _session_context
    ctx = _session_context()
    if ctx is None:
        return json.dumps({"ok": False, "error": "BUSINESS_ANSWERS_AUTHORITY_REQUIRED"})
    try:
        if operation == "create_run":
            value = business_answers.create_run_projection(ctx=ctx, request=args)
            key = "run"
        elif operation == "get_run":
            value = business_answers.get_run_projection(ctx=ctx, run_ref=args["run_ref"])
            key = "run"
        else:
            value = business_answers.get_answer_projection(ctx=ctx, answer_ref=args["answer_ref"])
            key = "answer"
        if value is None:
            raise LookupError("BUSINESS_ANSWER_ARTIFACT_NOT_FOUND")
        return json.dumps(value, ensure_ascii=False)
    except (PermissionError, ValueError, LookupError) as exc:
        return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)


def business_answers_receivables_run(args, **kwargs):
    return _invoke("create_run", args)


def business_answers_receivables_status(args, **kwargs):
    return _invoke("get_run", args)


def business_answers_receivables_read_answer(args, **kwargs):
    return _invoke("get_answer", args)
