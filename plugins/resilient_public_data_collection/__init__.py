from __future__ import annotations

from pathlib import Path
from typing import Any

from . import schemas, tools


def register(ctx: Any) -> None:
    ctx.register_tool(
        name="public_source_probe",
        toolset=schemas.TOOLSET_NAME,
        schema=schemas.function_schema(schemas.PROBE_PUBLIC_URL_SCHEMA),
        handler=tools.probe_public_url,
        description="Probe one public HTTP(S) path and classify access behavior without authentication.",
    )
    ctx.register_tool(
        name="public_source_inspect_page",
        toolset=schemas.TOOLSET_NAME,
        schema=schemas.function_schema(schemas.INSPECT_PUBLIC_PAGE_SCHEMA),
        handler=tools.inspect_public_page,
        description="Inspect a public HTML page for links, forms, scripts, attachment candidates, and known public download derivations.",
    )
    ctx.register_tool(
        name="public_source_freeze_membership",
        toolset=schemas.TOOLSET_NAME,
        schema=schemas.function_schema(schemas.FREEZE_PUBLIC_MEMBERSHIP_SCHEMA),
        handler=tools.freeze_public_membership,
        description="Freeze a bounded public-source membership list before raw-byte acquisition.",
    )
    ctx.register_tool(
        name="public_source_capture_object",
        toolset=schemas.TOOLSET_NAME,
        schema=schemas.function_schema(schemas.CAPTURE_PUBLIC_OBJECT_SCHEMA),
        handler=tools.capture_public_object,
        description="Capture one public object into workspace-scoped content-addressed storage with an append-oriented receipt and byte fingerprint.",
    )
    ctx.register_tool(
        name="public_source_freeze_collection",
        toolset=schemas.TOOLSET_NAME,
        schema=schemas.function_schema(schemas.FREEZE_PUBLIC_COLLECTION_SCHEMA),
        handler=tools.freeze_public_collection,
        description="Freeze the current capture receipts for one workspace-scoped collection into a deterministic release manifest.",
    )
    ctx.register_tool(
        name="public_source_verify_collection",
        toolset=schemas.TOOLSET_NAME,
        schema=schemas.function_schema(schemas.VERIFY_PUBLIC_COLLECTION_SCHEMA),
        handler=tools.verify_public_collection,
        description="Verify a frozen collection offline from persisted receipts and content-addressed raw objects.",
    )
    ctx.register_skill(
        name="resilient-public-data-collection",
        path=Path(__file__).with_name("SKILL.md"),
        description=(
            "Evidence-first workflow for building reproducible public-source data "
            "collection pipelines when discovery, authentication, or access paths fail."
        ),
    )
