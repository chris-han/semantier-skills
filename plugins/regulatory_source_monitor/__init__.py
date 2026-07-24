from __future__ import annotations

from typing import Any

from . import schemas, tools


def register(ctx: Any) -> None:
    ctx.register_tool(
        name="regulatory_source_monitor_due_sources",
        toolset=schemas.TOOLSET_NAME,
        schema=schemas.LIST_DUE_SOURCES_SCHEMA,
        handler=tools.regulatory_source_monitor_due_sources,
        description="List governed legal sources due for regulatory monitor scanning.",
    )
    ctx.register_tool(
        name="regulatory_source_monitor_run",
        toolset=schemas.TOOLSET_NAME,
        schema=schemas.RUN_MONITOR_SCHEMA,
        handler=tools.regulatory_source_monitor_run,
        description="Create or resume one bounded legal regulatory monitor run.",
    )
    ctx.register_tool(
        name="regulatory_source_monitor_source_status",
        toolset=schemas.TOOLSET_NAME,
        schema=schemas.SOURCE_STATUS_SCHEMA,
        handler=tools.regulatory_source_monitor_source_status,
        description="Read separated source, knowledge, and runtime status for a legal source.",
    )
    ctx.register_tool(
        name="regulatory_source_monitor_acknowledge_alert",
        toolset=schemas.TOOLSET_NAME,
        schema=schemas.ACKNOWLEDGE_ALERT_SCHEMA,
        handler=tools.regulatory_source_monitor_acknowledge_alert,
        description="Acknowledge an existing legal regulatory alert without approving or activating authority.",
    )
