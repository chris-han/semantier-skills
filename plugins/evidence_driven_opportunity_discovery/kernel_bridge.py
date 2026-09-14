from __future__ import annotations

from typing import Any, Protocol


class SemantierKernelBridge(Protocol):
    """Runtime-owned bridge into Semantier's existing five-object kernel.

    This is a core integration seam, not a third runtime adapter. Hermes/Semantier
    injects an implementation backed by canonical core services/stores.
    """

    def promote_observation(self, *, observation: dict[str, Any], runtime_context: dict[str, Any]) -> dict[str, Any]: ...

    def project_opportunity_context(self, *, hypothesis: dict[str, Any], runtime_context: dict[str, Any]) -> dict[str, Any]: ...

    def record_outcome_evidence(self, *, outcome: dict[str, Any], runtime_context: dict[str, Any]) -> dict[str, Any]: ...

    def propose_change_candidate(self, *, assessment: dict[str, Any], policy_change: dict[str, Any], runtime_context: dict[str, Any]) -> dict[str, Any]: ...


def kernel_bridge(kwargs: dict[str, Any]) -> SemantierKernelBridge | None:
    bridge = kwargs.get("semantier_kernel_bridge")
    if bridge is None:
        return None
    required = (
        "promote_observation",
        "project_opportunity_context",
        "record_outcome_evidence",
        "propose_change_candidate",
    )
    if any(not callable(getattr(bridge, name, None)) for name in required):
        raise RuntimeError("SEMANTIER_KERNEL_BRIDGE_INVALID")
    return bridge
