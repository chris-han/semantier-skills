from __future__ import annotations

import json
from contextlib import contextmanager
from typing import Any, Iterator


def negotiation_task_body(
    *,
    negotiation: dict[str, Any],
    session_id: str | None = None,
) -> str:
    payload = {}
    try:
        loaded = json.loads(str(negotiation.get("payload_json") or "{}"))
        if isinstance(loaded, dict):
            payload = loaded
    except json.JSONDecodeError:
        payload = {}
    body = {
        "metadata": {
            "task_type": "feishu_meeting_negotiation",
            "negotiation_id": str(negotiation["negotiation_id"]),
            "workspace_id": str(negotiation["workspace_id"]),
            "session_id": session_id or payload.get("session_id"),
            "event_id": str(negotiation["event_id"]),
            "event_revision_id": str(negotiation["event_revision_id"]),
            "status": str(negotiation["status"]),
            "meeting_title": str(
                payload.get("meeting_title")
                or payload.get("title")
                or negotiation["event_id"]
            ),
        },
        "payload": {
            "calendar_id": str(negotiation["calendar_id"]),
            "creator_user_id": str(negotiation["creator_user_id"]),
            "trigger_attendee_user_ids": json.loads(
                str(negotiation.get("trigger_attendee_user_ids_json") or "[]")
            ),
            "original_start_time": str(negotiation["original_start_time"]),
            "original_end_time": str(negotiation["original_end_time"]),
            "timezone": str(negotiation["timezone"]),
        },
    }
    return json.dumps(body, ensure_ascii=False, sort_keys=True)


def negotiation_task_idempotency_key(negotiation_id: str) -> str:
    return f"feishu-meeting-negotiation:{negotiation_id}"


class HermesKanbanClient:
    def __init__(self, *, board: str | None = None):
        self.board = board

    @contextmanager
    def _connection(self) -> Iterator[tuple[Any, Any]]:
        from hermes_cli import kanban_db

        conn = kanban_db.connect(board=self.board)
        try:
            yield kanban_db, conn
        finally:
            conn.close()

    def create_negotiation_task(self, *, negotiation: dict[str, Any], body: str) -> str:
        with self._connection() as (kanban_db, conn):
            return str(
                kanban_db.create_task(
                    conn,
                    title=f"Meeting time negotiation: {negotiation['event_id']}",
                    body=body,
                    assignee="meeting-coordinator",
                    created_by="feishu_meeting_coordinator",
                    user_id=str(negotiation["creator_user_id"]),
                    workspace_id=str(negotiation["workspace_id"]),
                    tenant=str(negotiation["workspace_id"]),
                    idempotency_key=negotiation_task_idempotency_key(
                        str(negotiation["negotiation_id"])
                    ),
                    skills=["feishu_meeting_coordinator"],
                    initial_status="running",
                    board=self.board,
                )
            )

    def comment(self, task_id: str, *, author: str, body: str) -> int:
        with self._connection() as (kanban_db, conn):
            return int(kanban_db.add_comment(conn, task_id, author, body))

    def unblock(self, task_id: str) -> bool:
        with self._connection() as (kanban_db, conn):
            return bool(kanban_db.unblock_task(conn, task_id))

    def block(self, task_id: str, *, reason: str, kind: str | None = None) -> bool:
        with self._connection() as (kanban_db, conn):
            return bool(kanban_db.block_task(conn, task_id, reason=reason, kind=kind))

    def complete(
        self, task_id: str, *, summary: str, metadata: dict[str, Any] | None = None
    ) -> bool:
        with self._connection() as (kanban_db, conn):
            return bool(
                kanban_db.complete_task(
                    conn, task_id, summary=summary, metadata=metadata
                )
            )

    def delete(self, task_id: str) -> bool:
        with self._connection() as (kanban_db, conn):
            kanban_db.reclaim_task(
                conn,
                task_id,
                reason="feishu meeting monitor cleanup",
            )
            return bool(kanban_db.delete_task(conn, task_id))
