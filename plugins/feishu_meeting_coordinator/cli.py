from __future__ import annotations

import json
from typing import Any


def register_cli(parser) -> None:
    monitors = parser.add_parser("monitors")
    monitors.add_argument("--workspace-id", required=True)
    monitors.add_argument("--limit", type=int, default=20)
    monitors.set_defaults(command="monitors")


def _store_from_args(args: Any):
    injected = getattr(args, "store", None)
    if injected is not None:
        return injected
    from .store import MeetingCoordinatorStore

    return MeetingCoordinatorStore()


def command(args) -> int:
    command_name = getattr(args, "command", None)
    if command_name != "monitors":
        print("supported commands: monitors")
        return 2
    store = _store_from_args(args)
    rows = store.list_operation_monitors(
        workspace_id=str(args.workspace_id),
        limit=int(args.limit),
    )
    print(json.dumps({"monitors": rows}, ensure_ascii=False, sort_keys=True))
    return 0
