from __future__ import annotations

import json
from typing import Any


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _error(error_code: str, message: str) -> str:
    return _json({"ok": False, "error_code": error_code, "message": message})


def regulatory_source_monitor_due_sources(args: dict[str, Any], **_kw: Any) -> str:
    from eos.legal_regulatory_monitor import LegalRegulatoryMonitor

    organization_id = str(args.get("organization_id") or "").strip()
    as_of = str(args.get("as_of") or "").strip()
    if not organization_id or not as_of:
        return _error("ARGUMENT_REQUIRED", "organization_id and as_of are required")
    try:
        due = LegalRegulatoryMonitor().list_due_sources(
            organization_id=organization_id,
            as_of=as_of,
            limit=int(args["limit"]) if args.get("limit") is not None else None,
            offset=int(args.get("offset") or 0),
        )
    except Exception as exc:
        return _error("REGULATORY_MONITOR_DUE_SOURCES_FAILED", str(exc))
    return _json({"ok": True, "due_sources": due})


def regulatory_source_monitor_run(args: dict[str, Any], **_kw: Any) -> str:
    from eos.legal_regulatory_monitor_cron import run_regulatory_monitor_tick

    organization_id = str(args.get("organization_id") or "").strip()
    scheduled_at = str(args.get("scheduled_at") or "").strip()
    if not organization_id or not scheduled_at:
        return _error("ARGUMENT_REQUIRED", "organization_id and scheduled_at are required")
    try:
        result = run_regulatory_monitor_tick(
            organization_id=organization_id,
            workspace_id=str(args.get("workspace_id") or "").strip() or None,
            scheduled_at=scheduled_at,
            trigger=str(args.get("trigger") or "MANUAL").strip().upper(),
            limit=int(args["limit"]) if args.get("limit") is not None else None,
            offset=int(args.get("offset") or 0),
        )
    except Exception as exc:
        return _error("REGULATORY_MONITOR_RUN_FAILED", str(exc))
    return _json({"ok": True, **result})


def regulatory_source_monitor_source_status(args: dict[str, Any], **_kw: Any) -> str:
    from eos.legal_regulatory_monitor import LegalRegulatoryMonitor

    organization_id = str(args.get("organization_id") or "").strip()
    source_id = str(args.get("source_id") or "").strip()
    if not organization_id or not source_id:
        return _error("ARGUMENT_REQUIRED", "organization_id and source_id are required")
    try:
        status = LegalRegulatoryMonitor().get_status(
            organization_id=organization_id,
            source_id=source_id,
            as_of=str(args.get("as_of") or "").strip() or None,
        )
    except Exception as exc:
        return _error("REGULATORY_MONITOR_STATUS_FAILED", str(exc))
    return _json({"ok": True, "status": status})


def regulatory_source_monitor_acknowledge_alert(args: dict[str, Any], **_kw: Any) -> str:
    from eos.legal_corpus_store import LegalCorpusStore

    organization_id = str(args.get("organization_id") or "").strip()
    alert_id = str(args.get("alert_id") or "").strip()
    acknowledged_by = str(args.get("acknowledged_by") or "").strip()
    if not organization_id or not alert_id or not acknowledged_by:
        return _error("ARGUMENT_REQUIRED", "organization_id, alert_id, and acknowledged_by are required")
    try:
        acknowledgement = LegalCorpusStore().acknowledge_regulatory_alert(
            organization_id=organization_id,
            alert_id=alert_id,
            acknowledged_by=acknowledged_by,
            acknowledgement=dict(args.get("acknowledgement") or {}),
        )
    except Exception as exc:
        return _error("REGULATORY_MONITOR_ACK_FAILED", str(exc))
    return _json({"ok": True, "acknowledgement": acknowledgement})
