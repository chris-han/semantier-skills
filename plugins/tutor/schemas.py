# The host supplies the authenticated learner and workspace to the approved server.
OPERATIONS = {
    "tutor_plan": ("Create or edit a learning path.", ("project_ref", "artifact", "preparation", "objectives", "goal", "request_id", "expected_revision", "language"), ("plan_ref",)),
    "tutor_teach": ("Explain an objective or give a requested hint.", ("project_ref", "plan_ref", "objective_ref", "request_id"), ("question", "language")),
    "tutor_practice": ("Prepare a source-grounded exercise.", ("project_ref", "plan_ref", "objective_ref", "expected_revision", "request_id"), ()),
    "tutor_submit": ("Assess a learner submission against its frozen exercise.", ("project_ref", "plan_ref", "exercise_ref", "answer", "expected_revision", "request_id"), ()),
    "tutor_progress": ("Resume an authorized learning plan.", ("project_ref", "plan_ref"), ()),
}



def parameters_for(required, optional):
    text = {"type": "string", "minLength": 1}
    pin = {"type": "object", "properties": {
        "artifact_kind": text, "artifact_ref": text,
        "artifact_hash": {"type": "string", "pattern": "^sha256:[0-9a-f]{64}$"},
    }, "required": ["artifact_kind", "artifact_ref", "artifact_hash"], "additionalProperties": False}
    fields = {
        "expected_revision": {"type": "integer", "minimum": 0},
        "artifact": pin, "preparation": pin,
        "objectives": {"type": "array", "minItems": 1, "items": {
            "type": "object", "properties": {
                "title": text, "block_ids": {"type": "array", "minItems": 1, "items": text},
            }, "required": ["title", "block_ids"], "additionalProperties": False,
        }},
    }
    return {"type": "object", "properties": {key: fields.get(key, text) for key in (*required, *optional)},
            "required": list(required), "additionalProperties": False}
