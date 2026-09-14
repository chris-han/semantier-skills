from __future__ import annotations

from typing import Any

from . import schemas, tools


def register(ctx: Any) -> None:
    ctx.register_tool(name="eod_create_opportunity_scope", toolset=schemas.TOOLSET_NAME, schema=schemas.CREATE_SCOPE_SCHEMA, handler=tools.create_opportunity_scope)
    ctx.register_tool(name="eod_record_observation", toolset=schemas.TOOLSET_NAME, schema=schemas.RECORD_OBSERVATION_SCHEMA, handler=tools.record_observation)
    ctx.register_tool(name="eod_form_opportunity_hypothesis", toolset=schemas.TOOLSET_NAME, schema=schemas.FORM_HYPOTHESIS_SCHEMA, handler=tools.form_opportunity_hypothesis)
    ctx.register_tool(name="eod_rank_opportunities", toolset=schemas.TOOLSET_NAME, schema=schemas.RANK_SCHEMA, handler=tools.rank_opportunities)
    ctx.register_tool(name="eod_request_opportunity_investigation", toolset=schemas.TOOLSET_NAME, schema=schemas.INVESTIGATE_SCHEMA, handler=tools.request_opportunity_investigation)
    ctx.register_tool(name="eod_create_counterfactual_request", toolset=schemas.TOOLSET_NAME, schema=schemas.COUNTERFACTUAL_SCHEMA, handler=tools.create_counterfactual_request)
    ctx.register_tool(name="eod_propose_opportunity_action", toolset=schemas.TOOLSET_NAME, schema=schemas.PROPOSE_ACTION_SCHEMA, handler=tools.propose_opportunity_action)
    ctx.register_tool(name="eod_record_opportunity_outcome", toolset=schemas.TOOLSET_NAME, schema=schemas.RECORD_OUTCOME_SCHEMA, handler=tools.record_opportunity_outcome)
    ctx.register_tool(name="eod_assess_opportunity", toolset=schemas.TOOLSET_NAME, schema=schemas.ASSESS_SCHEMA, handler=tools.assess_opportunity)
    ctx.register_tool(name="eod_list_opportunities", toolset=schemas.TOOLSET_NAME, schema=schemas.LIST_SCHEMA, handler=tools.list_opportunities)
