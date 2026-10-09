from pathlib import Path
from . import schemas, tools


def register(ctx):
    ctx.register_tool(name="business_answers_receivables_run", toolset="business_answers",
        schema=schemas.TOOL_SCHEMAS["business_answers_receivables_run"],
        handler=tools.business_answers_receivables_run, description="Prepare a source-bounded receivables run from an authorized import.")
    ctx.register_tool(name="business_answers_receivables_status", toolset="business_answers",
        schema=schemas.TOOL_SCHEMAS["business_answers_receivables_status"],
        handler=tools.business_answers_receivables_status, description="Read the retained native run and its checks.")
    ctx.register_tool(name="business_answers_receivables_read_answer", toolset="business_answers",
        schema=schemas.TOOL_SCHEMAS["business_answers_receivables_read_answer"],
        handler=tools.business_answers_receivables_read_answer, description="Read the saved answer and contributing invoices.")
    ctx.register_skill(name="business_answers", path=Path(__file__).parent / "SKILL.md",
        description="Source-bounded receivables answers.")
