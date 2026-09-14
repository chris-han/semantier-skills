from __future__ import annotations


def structured_handoff(action_proposal: dict, reason: str = "SEMANTIER_AUTHORITY_UNAVAILABLE") -> dict:
    return {
        "runtime": "codex",
        "status": "HANDOFF_REQUIRED",
        "reason": reason,
        "action_proposal": action_proposal,
    }
