from __future__ import annotations

TOOLSET_NAME = "semantica_knowledge_graph"
TOOL_NAMES = [
    "semantica_knowledge_deduplicate",
    "semantica_knowledge_extract",
    "semantica_knowledge_ingest",
    "semantica_knowledge_provenance",
    "semantica_knowledge_query",
    "semantica_knowledge_validate",
    "semantica_knowledge_visualize",
]

SOURCE_REF = {"oneOf": [{"required": ["upload_id"]}, {"required": ["artifact_id"]}, {"required": ["source_registry_id"]}]}
BASE = {"type": "object", "additionalProperties": False}
EXTRACT_SCHEMA = {"type": "object", "additionalProperties": False, "properties": {
    "source": SOURCE_REF, "knowledge_scope_id": {"type": "string"},
    "discovery_run_id": {"type": "string"}, "document_id": {"type": "string"},
    "provider": {"type": "string", "enum": ["semantica", "semantica_service", "langextract", "legacy"]},
}}
SCHEMAS = {name: (EXTRACT_SCHEMA if name.endswith("extract") else BASE) for name in TOOL_NAMES}
