TOOLSET_NAME = "business_answers"


def _schema(properties, required):
    return {"parameters": {"type": "object", "properties": properties,
        "required": required, "additionalProperties": False}}


_STRING = {"type": "string", "minLength": 1}
TOOL_SCHEMAS = {
    "business_answers_receivables_run": _schema({
        "import_id": _STRING, "file_id": _STRING,
        "mapping": {"type": "object", "additionalProperties": {"type": "string"}},
        "snapshot_date": {"type": "string", "format": "date"},
        "confirmation": {"oneOf": [{"type": "boolean"}, {"type": "object"}]},
        "predecessor_build_ref": _STRING}, ["import_id"]),
    "business_answers_receivables_status": _schema({"run_ref": _STRING}, ["run_ref"]),
    "business_answers_receivables_read_answer": _schema({"answer_ref": _STRING}, ["answer_ref"]),
}
