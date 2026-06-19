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
        name="screen_resumes",
        toolset=schemas.TOOLSET_NAME,
        schema=schemas.SCREEN_RESUMES_SCHEMA,
        handler=tools.screen_resumes,
        emoji="✅",
    )
