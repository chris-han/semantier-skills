from pathlib import Path
from agents.plugin_capability_contract import validate_registered_tools
from . import schemas, tools

def register(ctx):
    validate_registered_tools(Path(__file__).with_name("plugin.yaml"), schemas.SCHEMAS, capability_to_tools={
        "inspect_requirements":{"requirements_change_compare","requirements_change_impact","requirements_change_baseline"},
        "propose_change":{"requirements_change_propose"},
        "submit_review":{"requirements_change_submit_review"},
        "publish_baseline":{"requirements_change_publish"},
        "approve":set(),"admit":set(),"activate":set(),"change_authority_binding":set(),
    })
    for name in schemas.SCHEMAS:
        ctx.register_tool(name=name,toolset="requirements_change_management",schema=schemas.SCHEMAS[name],handler=getattr(tools,name),is_async=False)
