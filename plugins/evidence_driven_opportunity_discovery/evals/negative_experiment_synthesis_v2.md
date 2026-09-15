# EOD Negative Experiment Synthesis v2

Status: `LEARNING_ARTIFACT`

Scope: three completed frozen Track A live experiments.

This document does not reopen or rescore prior gates. It extends `negative_experiment_synthesis_v1.md` with the completed H2 claim-role experiment.

## 1. Three-experiment pattern

Experiment A — original B3:

- improved Evidence Grounding Precision;
- improved Contradiction Recall;
- preserved Unsafe Action Rate;
- failed Unsupported-Claim Rate non-inferiority;
- slightly regressed Hypothesis Precision.

Experiment B — B3′ evidence-qualified admission:

- improved Evidence Grounding Precision;
- improved Contradiction Recall;
- restored Hypothesis Precision;
- failed Unsupported-Claim Rate non-inferiority;
- severely collapsed Hypothesis Recall and positive admissions.

Experiment C — B3″ claim-role separation:

- reduced Unsupported-Claim Rate to `0.0`;
- reduced `unsupported_claims_count` to `0`;
- preserved Hypothesis Recall versus fresh B2;
- preserved positive-admission anti-collapse and Unsafe Action Rate;
- regressed Evidence Grounding Precision;
- regressed Contradiction Recall sharply;
- regressed Hypothesis Precision.

Frozen H2 release result: FAIL.

Failed checks:

- `evidence_grounding_precision_improved`
- `contradiction_recall_improved`
- `hypothesis_precision_non_inferior`

## 2. What H2 established

H2 was not supported as a complete release hypothesis, but its narrow mechanism was supported.

The prompt-level claim-role intervention changed model output behavior exactly in the intended local dimension:

- fresh B2 produced 58 claims, including 4 unsupported claims;
- B3″ produced 46 claims and 0 unsupported claims;
- mean Unsupported-Claim Rate changed from `0.07018` to `0.0`.

This is strong evidence that semantic role mixing inside `claims` was a real contributor to the earlier Unsupported-Claim Rate failures.

However, the same prompt overlay also perturbed broader reasoning behavior:

- Evidence Grounding Precision: `0.58605 -> 0.56111`;
- Contradiction Recall: `1.00000 -> 0.33333`;
- Hypothesis Precision: `0.83333 -> 0.63690`.

Therefore the problem is no longer simply “should unresolved propositions be routed out of claims?” The answer appears to be yes. The remaining engineering question is how to enforce that role separation without consuming model attention or changing upstream evidence/opportunity reasoning.

## 3. Revised architectural interpretation

The three experiments suggest two concerns should be separated:

1. Reasoning policy: identify opportunity validity, evidence, contradictions, assumptions, uncertainties, and next action.
2. Output-shape enforcement: ensure factual assertions, assumptions, and uncertainties are serialized into the correct fields.

Encoding both concerns as additional natural-language skill instructions creates interference risk. B3″ solved the serialization symptom but degraded reasoning quality.

This points toward the existing Semantier ownership principle: invariant structural constraints should be owned by executable Tool/Policy/schema boundaries rather than accumulated as prompt prose.

Claim-role separation is structurally checkable and therefore should not necessarily live as another routing/workflow heuristic in the skill.

## 4. Constraint on the next experiment

Do not add another paragraph of claim-role prompt instructions to production `SKILL.md`.

Do not tighten opportunity admission again.

Do not change the historical evaluator and behavior intervention in the same experiment.

The next bounded mechanism should test structural output-role enforcement while leaving the original EOD reasoning instructions unchanged.

## 5. Candidate H3 — structural claim-role projection

Candidate, not yet frozen:

> H3 — Structural claim-role projection: keep the production EOD skill/reasoning instructions unchanged, then mechanically project model propositions into `claims`, `assumptions`, and `uncertainties` according to explicit evidence-reference rules before evaluation. This should preserve B3-family grounding/contradiction behavior while eliminating unsupported factual claims without changing opportunity admission.

A valid H3 intervention must be narrowly bounded. Candidate implementation ownership:

- keep the model's reasoning/task prompt unchanged from the original B3 condition;
- introduce an executable post-generation projection/validator rather than additional behavioral prompt text;
- only propositions with a non-empty valid evidence-ref basis may remain factual `claims`;
- propositions lacking that basis are routed to `assumptions` or `uncertainties` according to explicit deterministic rules;
- the projector must not change `valid_opportunity`, supporting/contradicting refs, recommended next step, or action proposal;
- raw pre-projection model output must be persisted so projection effects are auditable;
- projection failures must be retained as negative evidence rather than silently dropped.

## 6. H3 design warning

A structural projector changes the evaluated output representation. Therefore the next protocol must explicitly decide which causal question is being tested.

Recommended comparison:

- B2: fresh foundation-model control;
- B3-control: original EOD skill output without structural projection;
- B3-structural: the exact same raw B3 reasoning output with deterministic role projection applied afterward.

This paired-within-output design could isolate projector value without requiring stochastic model differences between B3-control and B3-structural.

If a simpler two-arm release comparison is required, keep B2 versus structurally projected B3, but also persist and report raw B3 pre-projection metrics as a diagnostic so representation improvement is not confused with reasoning improvement.

## 7. Current disposition

- Original B3: retained negative empirical evidence.
- B3′ admission H1: falsified; retained negative empirical evidence.
- B3″ prompt-level claim-role H2: full hypothesis failed, narrow role-routing mechanism supported.
- Production `SKILL.md`: unchanged by H1/H2 follow-ups.
- EOD plan: remains `implementation_complete_validation_failed` in backlog.
- Next candidate direction: structural claim-role projection under a new predeclared protocol; not yet frozen or authorized.
