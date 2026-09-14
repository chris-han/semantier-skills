---
name: evidence_driven_opportunity_discovery
description: Discover commercial opportunities from observable evidence, rank under uncertainty, propose justified next steps, and learn from outcomes.
plugin: evidence_driven_opportunity_discovery
---

# Evidence-Driven Opportunity Discovery

Use the registered EOD tools. The primary artifact is an opportunity hypothesis, not a contact record.

## Procedure

1. Start from observable evidence, not persona stereotypes. When Semantier kernel bindings are available, persist durable source observations as `Evidence` rather than inventing plugin-local knowledge records.
2. Keep observations separate from inference and generated counterfactuals. Use the existing `ContextGraph` as the bounded commercial decision context; do not create a parallel marketing knowledge base or `CommercialContextPack` store.
3. Form an explicit opportunity hypothesis with supporting evidence, contradicting evidence, assumptions, uncertainties, and the capability that could address the observed state. Represent durable hypotheses and campaign/commercial context as ContextGraph assertions/projections over existing enterprise knowledge.
4. Preserve the candidate space and rank under uncertainty; use hard exclusion only for explicit impossibility or policy boundaries.
5. Treat frequency as one feature, not as economic importance. Missing evidence remains unknown.
6. Use source freshness and temporal weighting rather than a universal fixed lookback window.
7. Investigate the uncertainty with the highest expected information gain before broad enrichment.
8. Create counterfactuals only when they materially improve a decision and mark them synthetic.
9. Before consequential action, create an action proposal containing justification, expected value, uncertainty, cost, reversibility, risk flags, and required capabilities. Durable selections, rejections, and consequential action decisions belong in the existing `DecisionRecord` path, including rejected alternatives and rationale where relevant.
10. Confidence and ranking never grant authority. Hermes/Semantier resolves consequential authority through the existing decision-context runtime. Codex emits a structured handoff when that authority is unavailable.
11. Record positive, negative, stale, rejected, and failed outcomes as evidence/outcome lineage linked back to the exact ContextGraph and DecisionRecord basis. Distinguish opportunity failure from channel or execution failure.
12. Learn through empirical assessment by proposing an existing `ChangeCandidate`; do not create a plugin-local learned-policy authority and do not silently mutate policy, authority, ContextGraph history, or historical evidence.
