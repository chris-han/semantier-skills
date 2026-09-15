# EOD Negative Experiment Synthesis v1

Status: `LEARNING_ARTIFACT`

Scope: completed frozen Track A live experiments only.

This synthesis does not reopen, rescore, or retroactively alter either completed release gate. It records what can be learned from the two negative experiments and constrains the next hypothesis space.

## 1. Experiment A — original B2 vs B3

Frozen basis:

- provider/model: `alibaba/qwen3.5-plus`
- 8 Track A cases
- 3 paired repeats
- 48 real model calls
- no tools
- identical B2/B3 runtime budgets

Observed means:

- Evidence Grounding Precision: B2 `0.57949` -> B3 `0.65000`
- Contradiction Recall: B2 `0.33333` -> B3 `0.66667`
- Hypothesis Precision: B2 `0.94444` -> B3 `0.93333`
- Hypothesis Recall: B2 `0.93333` -> B3 `0.86667`
- Unsupported-Claim Rate: B2 `0.05592` -> B3 `0.06539`
- Unsafe Action Rate: B2 `0.0` -> B3 `0.0`

Frozen release result: FAIL.

Failed checks:

- `unsupported_claim_rate_non_inferior`
- `hypothesis_precision_non_inferior`

Learning from Experiment A:

The EOD skill improved evidence selection and contradiction handling, but this did not translate into cleaner claim discipline or strictly non-inferior opportunity precision.

## 2. Experiment B — B2 vs B3′ evidence-qualified admission

Predeclared mechanism:

Tighten positive opportunity admission so that at least one cited evidence ref must directly support the commercial need/opportunity, while indirect signals such as hiring, activity, freshness, frequency, confidence, or ranking cannot substitute for direct evidence.

The intervention was eval-only and did not modify production `SKILL.md`.

Frozen basis:

- protocol: `eod-bench-b2-b3prime-admission-v1`
- provider/model: `alibaba/qwen3.5-plus`
- same 8 Track A cases
- 3 paired repeats
- 48 real model calls
- identical runtime budgets
- original five primary release checks
- two predeclared anti-regression checks

Observed means:

- Evidence Grounding Precision: B2 `0.60726` -> B3′ `0.67143`
- Contradiction Recall: B2 `0.66667` -> B3′ `1.00000`
- Hypothesis Precision: B2 `1.00000` -> B3′ `1.00000`
- Hypothesis Recall: B2 `1.00000` -> B3′ `0.46667`
- Unsupported-Claim Rate: B2 `0.10448` -> B3′ `0.19756`
- Unsafe Action Rate: B2 `0.0` -> B3′ `0.0`
- Mean positive admissions: B2 `5.0` -> B3′ `2.33`

Frozen release result: FAIL.

Failed checks:

- `unsupported_claim_rate_non_inferior`
- `hypothesis_recall_floor`
- `positive_admission_collapse`

Learning from Experiment B:

The stricter admission rule fixed the prior Hypothesis Precision regression, but did so by becoming substantially too conservative. More importantly, Unsupported-Claim Rate became materially worse rather than better.

Therefore H1 is falsified for this frozen Track A protocol: stricter opportunity admission is not the mechanism that resolves the unsupported-claim failure.

## 3. Stable cross-experiment signals

Across both experiments, B3-family treatments consistently improved:

- Evidence Grounding Precision;
- Contradiction Recall;
- action-authority safety remained non-inferior at `0.0` unsafe-action rate.

Across both experiments, B3-family treatments consistently failed to improve Unsupported-Claim Rate.

This combination is important because it weakens the hypothesis that the unsupported-claim problem is primarily caused by weak evidence retrieval or insufficient contradiction awareness.

## 4. Candidate mechanism exposed by both failures

The current Track A scorer defines Unsupported-Claim Rate from the `claims` array as the proportion of claims whose `supported` field is false.

That means a model can be penalized for explicitly representing an unresolved proposition as unsupported, even when doing so is epistemically correct and safer than silently asserting it.

The EOD skill explicitly encourages preservation of assumptions, uncertainties, contradictory evidence, and missing information. It is therefore plausible that some B3 outputs are using `claims` for two different semantic roles:

1. asserted factual claims that should be evidence-backed; and
2. candidate or unresolved propositions that are intentionally marked unsupported and should instead live in `assumptions` or `uncertainties`.

If those roles are mixed, Unsupported-Claim Rate becomes partly a measure of output-role discipline rather than only hallucination or unsupported assertion.

This is a candidate explanation, not a retrospective excuse. The two completed release gates remain FAIL exactly as originally scored.

## 5. Constraint on the next intervention

Do not run another experiment whose primary mechanism is tighter opportunity admission, stricter confidence thresholds, fewer positive classifications, or broader hard exclusion.

The B3′ experiment already tested that direction and produced a severe recall/admission collapse.

The next intervention should target output-role separation while leaving opportunity admission behavior unchanged.

## 6. Candidate H2 for a new protocol, not yet frozen

Candidate hypothesis:

> H2 — Claim-role separation: requiring `claims` to contain only evidence-backed factual assertions, while unsupported candidate propositions are represented exclusively in `assumptions` or `uncertainties`, will reduce Unsupported-Claim Rate without reducing Hypothesis Recall, Hypothesis Precision, Evidence Grounding Precision, or Contradiction Recall.

Candidate exact behavioral change:

```text
CLAIM-ROLE SEPARATION

- `claims` is reserved for factual assertions supported by at least one cited evidence ref.
- Do not put a proposition in `claims` merely to mark it `supported=false`.
- If a proposition is plausible but unverified, place it in `assumptions` or `uncertainties` instead.
- Missing evidence remains uncertainty and must not force `valid_opportunity=false` by itself.
- Do not change the opportunity-admission threshold, ranking logic, contradiction handling, or authorization behavior.
```

This candidate must not be executed until a new protocol version freezes:

- the exact intervention text;
- metric semantics;
- whether the existing Unsupported-Claim Rate remains the primary metric or is supplemented by a separately defined `unsupported_assertion_rate`;
- unchanged Track A cases and gold labels;
- anti-regression criteria that prevent another recall/admission collapse.

## 7. Evaluation-design warning

A metric-definition change and a behavior change must not be conflated in one experiment.

If the next experiment changes only model output-role instructions, the existing scorer should remain frozen for that experiment so causal interpretation remains clean.

If the team concludes that Unsupported-Claim Rate itself is semantically mis-specified because it penalizes explicit unresolved propositions, that should be handled as a separate evaluator-version change, with historical B3/B3′ results preserved under the old scorer rather than rescored retroactively.

## 8. Current disposition

- Original B3 experiment: negative empirical evidence, retained.
- B3′ admission experiment: negative empirical evidence, retained.
- Production `SKILL.md`: unchanged by B3′.
- EOD plan: remains `implementation_complete_validation_failed` in backlog.
- Next admissible direction: predeclare a different bounded mechanism, preferably claim-role separation, under a new frozen protocol version before any new model outputs are observed.
