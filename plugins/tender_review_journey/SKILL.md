---
name: tender-review-journey
description: Guide a user through the complete Tender review journey: select or upload policy material, build and review governed context, complete required runtime binding, inspect one or more tender documents, explain findings, open the same evidence in Workbench, and resume later from server-owned journey state.
---

# Tender Review Journey

Use this skill when the user wants to set up Tender review, use a policy document to build review context, inspect a Tender document, continue an existing Tender review, or understand why a Tender finding was produced.

## Workflow ownership

Invariant class: `EXPLAINED_AND_ENFORCED`. Runtime owner: `TenderJourneyService` + `TenderJourneyStore`.

This skill is stateless workflow guidance. The authoritative workflow position, revision, blockers, and exact artifact bindings are resolved from the authenticated server `TenderJourney` projection backed by the workspace SQLite owner. Chat history, local files, Markdown, browser storage, URLs, and skill prose are not accepted by that owner as workflow persistence.

The skill coordinates existing Semantier owners; it does not implement source parsing, GraphIntent, graph construction, certification, runtime authority, inspection semantics, or evidence evaluation itself.

## Journey

Workflow rules below are `WORKFLOW_HEURISTIC` unless a named server owner/receipt is stated; authority-sensitive transitions remain `EXPLAINED_AND_ENFORCED` by the named Semantier owner.

1. Resolve the current authenticated Tender journey before choosing an action. If more than one active journey is genuinely ambiguous, ask the user which journey to continue; otherwise resume the unambiguous server journey without asking them to repeat prior work.
2. When the server next action is `SELECT_OR_UPLOAD_POLICY`, help the user select or upload the policy source through the governed workspace artifact surface. `EXPLAINED_AND_ENFORCED`; runtime owner: `WorkspaceArtifactPreparationService`. Continue from its exact source preparation receipt containing SourceIdentity and CanonicalSourceIR pins.
3. Delegate interpretation and source-first graph construction to the canonical knowledge-graph-building flow. `WORKFLOW_HEURISTIC`; GraphIntent material-unresolved state is supplied by the server GraphIntent owner. Present review when that state requires user judgment; accepted or edited interpretation continues through graph construction automatically.
4. Certification/readiness remains owned by Semantier core. A certified or bounded-complete graph does not itself grant runtime authority. When the server reports `COMPLETE_GOVERNED_RUNTIME_BINDING`, guide the user through the actual governed runtime-binding owner and wait for its exact receipt.
5. At `SELECT_RUNTIME_DOCUMENT`, accept or select the Tender document to inspect. The runtime document must be prepared through the governed runtime-target surface; do not treat an arbitrary chat attachment path as runtime authority.
6. Runtime inspection is delegated to the current Tender runtime owner using the exact journey-selected context and runtime target. Render its findings and evidence; do not manufacture MATCH, NO_MATCH, UNKNOWN, authority, or evidence claims in skill prose.
7. When the user asks why something was flagged, explain the persisted inspection/evidence projection and offer the same journey/episode in Workbench. Chat and Workbench must refer to the same server journey revision and exact artifact pins.
8. After result review, the same policy journey may inspect another runtime document without rebuilding policy context. Each inspection remains a separate immutable episode in journey history.
9. On a new Chat, browser refresh, or backend restart, resolve the journey from the server again and continue from its next-action projection.

## Human interruption rule

runtime-owner: WORKFLOW
invariant-class: WORKFLOW_HEURISTIC

`TenderJourneyService`: follow its blocker/next-action projection. User interaction is appropriate for missing policy/runtime source, material GraphIntent ambiguity, an explicit governed authority action, ambiguous active-journey choice, or a material conflict/risk left unresolved by the owning service. Safe deterministic and idempotent steps continue without a conversational checkpoint.

## Authority boundaries

Invariant class: `EXPLAINED_AND_ENFORCED`. Runtime owners: certification/admission/activation services, `EffectiveRestrictionRuntimeContextService`, and ContextGraph learning/governance owners.

`EXPLAINED_AND_ENFORCED`; journey phase is not semantic authority. Runtime owners named above establish certification, admission, activation, regulatory assurance, and legal-authority states from persisted governed artifacts; journey/UI projections do not establish those states.

`EXPLAINED_AND_ENFORCED`; ContextGraph and runtime-authority mutation remains structurally owned by existing learning/governance/activation services. User feedback may become learning evidence through those owners; this skill has no mutation tool for those authority surfaces.
