# The host supplies the authenticated learner and workspace to the approved server.
OPERATIONS = {
    "tutor_plan": ("Create or edit a learning path.", ("project_ref", "source_ref", "goal", "request_id"), ("plan_ref", "expected_revision", "language")),
    "tutor_teach": ("Explain an objective or give a requested hint.", ("project_ref", "plan_ref", "objective_ref", "request_id"), ("question", "language")),
    "tutor_practice": ("Prepare a source-grounded exercise.", ("project_ref", "plan_ref", "objective_ref", "expected_revision", "request_id"), ()),
    "tutor_submit": ("Assess a learner submission against its frozen exercise.", ("project_ref", "plan_ref", "exercise_ref", "answer", "expected_revision", "request_id"), ()),
    "tutor_progress": ("Resume an authorized learning plan.", ("project_ref",), ("plan_ref",)),
}


