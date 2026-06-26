from __future__ import annotations

from typing import Any

from . import schemas, tools


def register(ctx: Any) -> None:
    ctx.register_tool(
        name="extract_resume_text",
        toolset=schemas.TOOLSET_NAME,
        schema=schemas.EXTRACT_RESUME_TEXT_SCHEMA,
        handler=tools.extract_resume_text,
        emoji="📄",
    )
    ctx.register_tool(
        name="rank_resume_candidates",
        toolset=schemas.TOOLSET_NAME,
        schema=schemas.RANK_RESUME_CANDIDATES_SCHEMA,
        handler=tools.rank_resume_candidates,
        emoji="📊",
    )
    ctx.register_tool(
        name="list_session_uploads",
        toolset=schemas.TOOLSET_NAME,
        schema=schemas.LIST_SESSION_UPLOADS_SCHEMA,
        handler=tools.list_session_uploads,
        emoji="📁",
    )
    ctx.register_tool(
        name="resolve_uploaded_resume",
        toolset=schemas.TOOLSET_NAME,
        schema=schemas.RESOLVE_UPLOADED_RESUME_SCHEMA,
        handler=tools.resolve_uploaded_resume,
        emoji="🔎",
    )
    ctx.register_tool(
        name="screen_resumes",
        toolset=schemas.TOOLSET_NAME,
        schema=schemas.SCREEN_RESUMES_SCHEMA,
        handler=tools.screen_resumes,
        emoji="✅",
    )
    ctx.register_tool(
        name="extract_role_terms",
        toolset=schemas.TOOLSET_NAME,
        schema=schemas.EXTRACT_ROLE_TERMS_SCHEMA,
        handler=tools.extract_role_terms,
        emoji="🏷️",
    )
