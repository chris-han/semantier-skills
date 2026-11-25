"""Hermes registration for the Semantier Tutor package."""

from pathlib import Path

from .schemas import OPERATIONS
from .tools import tool_handler


def register(ctx):
    for name, (description, required, optional) in OPERATIONS.items():
        properties = {field: {"type": "string", "minLength": 1} for field in (*required, *optional)}
        if "expected_revision" in properties:
            properties["expected_revision"] = {"type": "integer", "minimum": 0}
        parameters = {
            "type": "object",
            "properties": properties,
            "required": list(required),
            "additionalProperties": False,
        }
        ctx.register_tool(
            name=name, toolset="tutor", description=description,
            schema={"name": name, "description": description, "parameters": parameters},
            handler=tool_handler(ctx, name),
        )
    ctx.register_skill(name="tutor", path=Path(__file__).with_name("SKILL.md"),
                       description="Source-grounded learning, practice and progress.")
