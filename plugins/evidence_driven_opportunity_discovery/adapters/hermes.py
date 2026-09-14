from __future__ import annotations


def trusted_context(kwargs: dict) -> dict:
    value = kwargs.get("runtime_context") or kwargs.get("context")
    if not isinstance(value, dict) or not value.get("organization_id") or not value.get("actor_id"):
        raise RuntimeError("TRUSTED_RUNTIME_CONTEXT_REQUIRED")
    return value


def require_capabilities(context: dict, capabilities: list[str]) -> None:
    present = set(context.get("capabilities") or [])
    if not present:
        return
    missing = [cap for cap in capabilities if cap not in present]
    if missing:
        raise RuntimeError(f"CAPABILITY_REQUIRED:{','.join(missing)}")
