from __future__ import annotations

from typing import Any

RECOVERED = {"FOUND_OFFICIAL_SOURCE", "FOUND_PUBLIC_ANNOUNCEMENT", "FOUND_PUBLIC_ATTACHMENT"}


def decide_recovery(case: dict[str, Any]) -> str:
    if case.get("alternate_source") in RECOVERED or case.get("same_site_alternate_entry") in RECOVERED:
        return "USE_RECOVERED_ROUTE"

    status = case.get("http_status")
    initial_failure = case.get("initial_failure")
    attempts = int(case.get("blocked_retry_attempts") or 0)

    if status == 401 or initial_failure == "LOGIN_REQUIRED":
        return "STOP_AUTH_REQUIRED"
    if attempts >= 1:
        return "STOP_AFTER_BOUNDED_RETRY"
    if status == 429:
        return "BLOCKED_RETRY_ONCE" if bool(case.get("rate_backoff_respected")) else "WAIT_RATE_LIMIT"
    if status == 403:
        if bool(case.get("public_resource_confirmed")) and case.get("blocked_interpretation") == "SESSION_OR_BOT_BLOCK":
            return "BLOCKED_RETRY_ONCE"
        return "STOP_ACCESS_BOUNDARY"
    if initial_failure == "HOST_NOT_ALLOWLISTED":
        return "STOP_ENVIRONMENT_OR_ALLOWLIST"
    return "STOP_UNRESOLVED"
