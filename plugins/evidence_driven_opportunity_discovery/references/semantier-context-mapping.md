# Semantier Decision-Context Mapping

Evidence-Driven Opportunity Discovery does not own a parallel marketing knowledge base. Durable commercial knowledge and decisions reuse Semantier's five-object semantic kernel.

## Mapping

```text
External source observation
  -> Evidence

Company / customer / offer / positioning / voice / proof context
Campaign brief / active opportunity hypotheses / assumptions / uncertainty
  -> ContextGraph nodes, edges, assertions and evidence bindings

Opportunity selection / rejection / review
Authorized consequential outreach, experiment, budget or contract decision
  -> DecisionRecord

Response / conversion / stale-source discovery / channel failure / human correction
  -> Evidence linked to the exact ContextGraph / DecisionRecord basis

Proposed improvement to context formation, reasoning or ontology
  -> ChangeCandidate
```

## Context is resolved, not recreated

The EOD plugin must not construct a standalone ContextGraph from an opportunity record alone. `ContextGraphKernelService.form_context()` requires an exact `FormationInput`, pinned ontology, source evidence, formation policy, source graph, temporal world, and external-pin verification. Those values belong to the active Semantier workspace/decision-context runtime and cannot be inferred from plugin-local data.

The Hermes/Semantier runtime therefore injects a `SemantierKernelBridge` implementation that resolves the current workspace basis and delegates to canonical core services. The plugin only supplies domain observations, hypotheses, outcome interpretation and learning proposals.

If that bridge is absent, EOD may perform transient exploratory discovery and ranking. It must not claim that transient records are governed enterprise knowledge.

## Decision boundary

`OpportunityActionProposalV1` is intentionally not a `DecisionRecord`.

```text
rank / confidence / proposal
    != authorization
    != DecisionRecord
    != execution
```

The consequential decision path must resolve the exact subject, ContextGraph, Ontology, evidence, admissibility and `AuthorizationBasis` server-side. Only then may the Semantier runtime create a consequential `DecisionRecord` and execute the action.

## Human corrections

Human edits do not require a sixth first-class semantic object. Preserve the before/after artifacts and rationale as evidence, record the review conclusion as a `DecisionRecord` where durable, and create a `ChangeCandidate` only when the correction proposes a future structural/reasoning/context change.

## Marketing-engineering file structures

Files such as `company.md`, `customer.md`, `offer.md`, `proof.md`, `brief.md`, `decisions.md`, and `results.md` may be useful ingestion or presentation formats, but filenames are not semantic authorities. Their useful contents should be projected into the existing enterprise knowledge and decision context so all channels share the same current, versioned and evidenced state.
