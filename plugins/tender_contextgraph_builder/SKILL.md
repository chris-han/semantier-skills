# Tender ContextGraph Builder

Candidate-scoped fixed-DOCX extraction review and graph construction. All writes
remain append-preserving checkpoints under the authenticated workspace session boundary.
Admission, promotion, approval, and certification remain outside this capability.

## Graph-build workflow prerequisite

The user-facing workflow is the canonical `knowledge-graph-building@1.0.0`
journey. Before this plugin is invoked, that journey runs Graph-build preflight
and reaches `READY`: authenticated workspace resolved, active organization
membership present when tenant-member routes require it, governed source access
available, and a usable schema profile resolved. A `NEEDS_ORGANIZATION`,
`ACTIVE_MEMBERSHIP_REQUIRED`, profile, entitlement, or dependency state returns
to the owning recovery surface and re-runs preflight after recovery. This plugin
does not substitute local document handling for missing authenticated authority.

## Structured AI grounding

ContextGraph AI Ground may use the host-owned `PluginLlm` surface under this
plugin identity. It inherits the current agent's active provider, model,
credentials, and trust policy; provider/model/profile/agent overrides are not
part of this plugin surface. Structured output is candidate-scoped and is
validated against canonical evidence anchors before persistence.

AI Ground has no capability to create Human Grounding events, GraphDeltas,
releases, activation snapshots, or semantic authority. Provider failure remains
explicit; extraction-confidence threshold fallback is not a supported path.
Replay and audit verification consume persisted, hashed results without a live
model call.
