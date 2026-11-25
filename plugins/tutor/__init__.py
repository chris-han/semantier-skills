"""Hermes registration for the Semantier Tutor package."""

from pathlib import Path

from .schemas import OPERATIONS, parameters_for
from .tools import tool_handler


def register(ctx):
    for name, (description, required, optional) in OPERATIONS.items():
        ctx.register_tool(
            name=name, toolset="tutor", description=description,
            schema={"name": name, "description": description, "parameters": parameters_for(required, optional)},
            handler=tool_handler(ctx, name),
        )
    ctx.register_skill(name="tutor", path=Path(__file__).with_name("SKILL.md"),
                       description="Source-grounded learning, practice and progress.")
