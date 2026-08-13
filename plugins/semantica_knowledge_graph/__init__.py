from __future__ import annotations

from . import schemas, tools


def register(ctx) -> None:
    ctx.register_tool(name="semantica_knowledge_deduplicate", toolset=schemas.TOOLSET_NAME, schema=schemas.SCHEMAS["semantica_knowledge_deduplicate"], handler=tools.semantica_knowledge_deduplicate)
    ctx.register_tool(name="semantica_knowledge_extract", toolset=schemas.TOOLSET_NAME, schema=schemas.SCHEMAS["semantica_knowledge_extract"], handler=tools.semantica_knowledge_extract)
    ctx.register_tool(name="semantica_knowledge_ingest", toolset=schemas.TOOLSET_NAME, schema=schemas.SCHEMAS["semantica_knowledge_ingest"], handler=tools.semantica_knowledge_ingest)
    ctx.register_tool(name="semantica_knowledge_provenance", toolset=schemas.TOOLSET_NAME, schema=schemas.SCHEMAS["semantica_knowledge_provenance"], handler=tools.semantica_knowledge_provenance)
    ctx.register_tool(name="semantica_knowledge_query", toolset=schemas.TOOLSET_NAME, schema=schemas.SCHEMAS["semantica_knowledge_query"], handler=tools.semantica_knowledge_query)
    ctx.register_tool(name="semantica_knowledge_validate", toolset=schemas.TOOLSET_NAME, schema=schemas.SCHEMAS["semantica_knowledge_validate"], handler=tools.semantica_knowledge_validate)
    ctx.register_tool(name="semantica_knowledge_visualize", toolset=schemas.TOOLSET_NAME, schema=schemas.SCHEMAS["semantica_knowledge_visualize"], handler=tools.semantica_knowledge_visualize)
