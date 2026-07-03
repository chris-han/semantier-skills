from __future__ import annotations

import sys
from types import ModuleType

from feishu_meeting_coordinator.kanban_client import HermesKanbanClient


class _Conn:
    def __init__(self, calls: list[tuple]):
        self.calls = calls

    def close(self) -> None:
        self.calls.append(("close",))


def test_delete_reclaims_active_worker_before_deleting_task(monkeypatch):
    calls: list[tuple] = []
    conn = _Conn(calls)
    fake_hermes_cli = ModuleType("hermes_cli")
    fake_kanban_db = ModuleType("hermes_cli.kanban_db")

    def connect(*, board=None):
        calls.append(("connect", board))
        return conn

    def reclaim_task(received_conn, task_id, *, reason=None):
        calls.append(("reclaim_task", received_conn, task_id, reason))
        return True

    def delete_task(received_conn, task_id):
        calls.append(("delete_task", received_conn, task_id))
        return True

    fake_kanban_db.connect = connect
    fake_kanban_db.reclaim_task = reclaim_task
    fake_kanban_db.delete_task = delete_task
    fake_hermes_cli.kanban_db = fake_kanban_db
    monkeypatch.setitem(sys.modules, "hermes_cli", fake_hermes_cli)
    monkeypatch.setitem(sys.modules, "hermes_cli.kanban_db", fake_kanban_db)

    deleted = HermesKanbanClient(board="ops").delete("task_1")

    assert deleted is True
    assert calls == [
        ("connect", "ops"),
        ("reclaim_task", conn, "task_1", "feishu meeting monitor cleanup"),
        ("delete_task", conn, "task_1"),
        ("close",),
    ]
