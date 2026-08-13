from __future__ import annotations

import json


def _invoke(operation: str, args: dict, **kwargs) -> str:
    binding = kwargs.get("semantier_knowledge_graph_api")
    if binding is None:
        return json.dumps({"ok": False, "error": {"message": "AUTHENTICATED_REQUEST_CONTEXT_REQUIRED"}}, sort_keys=True)
    try:
        return json.dumps({"ok": True, "result": binding.invoke(operation=operation, payload=args)}, ensure_ascii=False, sort_keys=True)
    except Exception as exc:
        return json.dumps({"ok": False, "error": {"message": str(exc) or exc.__class__.__name__}}, ensure_ascii=False, sort_keys=True)


def semantica_knowledge_ingest(args, **kwargs): return _invoke("ingest", args, **kwargs)
def semantica_knowledge_extract(args, **kwargs): return _invoke("extract", args, **kwargs)
def semantica_knowledge_deduplicate(args, **kwargs): return _invoke("deduplicate", args, **kwargs)
def semantica_knowledge_provenance(args, **kwargs): return _invoke("provenance", args, **kwargs)
def semantica_knowledge_query(args, **kwargs): return _invoke("query", args, **kwargs)
def semantica_knowledge_validate(args, **kwargs): return _invoke("validate", args, **kwargs)
def semantica_knowledge_visualize(args, **kwargs): return _invoke("visualize", args, **kwargs)
