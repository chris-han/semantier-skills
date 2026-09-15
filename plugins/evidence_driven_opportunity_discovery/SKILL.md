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

## Chat guidance contract

For every substantive opportunity judgment in chat, guide the user to the next justified step. Do not stop at a score, confidence label, or opportunity classification, and do not default to outreach merely because an opportunity appears plausible.

Return enough of the following structure to make the recommendation inspectable:

- `Current judgment` — what the evidence currently supports, including whether the state is plausible, insufficient, contradicted, stale, or outcome-ready.
- `Evidence basis` — the most decision-relevant supporting and contradicting evidence.
- `Key uncertainty` — the unresolved fact with the highest decision impact; omit only when no material uncertainty remains.
- `Recommended next step` — exactly the next justified action in the reasoning process.
- `Why this step now` — explain why this step has higher expected decision value than broader enrichment or premature execution.
- `What would change the judgment` — name the evidence or outcome that would materially strengthen, weaken, reverse, or close the hypothesis.

Choose the next step from the evidence state rather than from a fixed sales funnel:

- Strong evidence plus a material unknown → investigate the highest-information-gain uncertainty.
- Insufficient evidence → request targeted evidence or monitor; do not treat absence as contradiction.
- Stale evidence → refresh the decision-relevant evidence before action.
- Contradictory evidence → resolve the contradiction or narrow the hypothesis before commitment.
- Strong opportunity with sufficient basis for a consequential step → propose the action, but label it `PROPOSED_NOT_AUTHORIZED` until the governed decision path authorizes execution.
- Channel failure → change or investigate the channel; do not mark the underlying opportunity failed unless the evidence supports that conclusion.
- Outcome evidence available → assess the outcome, distinguish hypothesis/ranking/channel/offer/execution error, and propose a `ChangeCandidate` only when warranted.

When suggesting an investigation, prefer one bounded question with the highest expected information gain and state what observation would resolve it. When suggesting an action proposal, include expected value, uncertainty, cost, reversibility, risk, and required capabilities when material. Never imply that confidence, model ranking, user enthusiasm, or chat wording itself grants authority to execute a consequential action.

### Compact chat examples

Strong evidence + material unknown:

`Current judgment: plausible opportunity. Key uncertainty: whether an internal governance capability already exists. Recommended next step: investigate the current governance stack. Why this step now: resolving that uncertainty can change addressability and has more decision value than collecting more generic company facts. What would change the judgment: evidence of a mature internal capability would weaken or narrow the opportunity.`

Insufficient evidence:

`Current judgment: insufficient evidence. Recommended next step: request targeted evidence about a concrete decision-context pain or buying trigger. Why this step now: missing evidence is not contradiction, so outreach would be premature. What would change the judgment: a specific operational pain, trigger, or accountable owner would materially strengthen the hypothesis.`

Stale or contradictory evidence:

`Current judgment: current-world applicability is uncertain. Recommended next step: refresh or resolve the conflicting evidence before action. Why this step now: a stale or contradictory basis can invalidate the action even when the original signal looked strong. What would change the judgment: fresh evidence that confirms the condition would restore the hypothesis; fresh disconfirming evidence would close or weaken it.`

Actionable opportunity:

`Current judgment: evidence is sufficient to justify an action proposal. Recommended next step: prepare the bounded action proposal. Status: PROPOSED_NOT_AUTHORIZED. Why this step now: further broad enrichment has lower decision value than testing the justified action. What would change the judgment: new contradiction, authority constraints, or materially worse cost/risk would stop or reshape the proposal.`

Channel failure:

`Current judgment: opportunity remains plausible; the failed channel is the weakened hypothesis. Recommended next step: investigate or switch the channel. What would change the judgment: evidence that the need no longer exists would weaken the opportunity; another channel failure alone would not.`

Outcome available:

`Current judgment: move from discovery to assessment. Recommended next step: classify the outcome as hypothesis, ranking, channel, offer, or execution evidence and update the learning record. What would change the judgment: repeated comparable outcomes may justify a ChangeCandidate; one outcome alone does not silently rewrite policy.`
