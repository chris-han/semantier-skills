from __future__ import annotations

from typing import Any

from . import schemas, tools


def register(ctx: Any) -> None:
    ctx.register_tool(name="vc_github_create_universe", toolset=schemas.TOOLSET_NAME, schema=schemas.CREATE_UNIVERSE_SCHEMA, handler=tools.create_universe)
    ctx.register_tool(name="vc_github_scan_universe", toolset=schemas.TOOLSET_NAME, schema=schemas.SCAN_UNIVERSE_SCHEMA, handler=tools.scan_universe)
    ctx.register_tool(name="vc_github_inspect_target", toolset=schemas.TOOLSET_NAME, schema=schemas.INSPECT_TARGET_SCHEMA, handler=tools.inspect_target)
    ctx.register_tool(name="vc_github_score_target", toolset=schemas.TOOLSET_NAME, schema=schemas.SCORE_TARGET_SCHEMA, handler=tools.score_target)
    ctx.register_tool(name="vc_github_propose_candidate", toolset=schemas.TOOLSET_NAME, schema=schemas.PROPOSE_CANDIDATE_SCHEMA, handler=tools.propose_candidate)
    ctx.register_tool(name="vc_github_list_candidates", toolset=schemas.TOOLSET_NAME, schema=schemas.LIST_CANDIDATES_SCHEMA, handler=tools.list_candidates)
    ctx.register_tool(name="vc_github_request_research", toolset=schemas.TOOLSET_NAME, schema=schemas.REQUEST_RESEARCH_SCHEMA, handler=tools.request_research)
    ctx.register_tool(name="vc_github_schedule_scan", toolset=schemas.TOOLSET_NAME, schema=schemas.SCHEDULE_SCAN_SCHEMA, handler=tools.schedule_scan)
